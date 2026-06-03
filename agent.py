"""Orchestrator — the autonomous decision loop.

Flow per tick:
  1. Gather current state (ops_status)
  2. Send state to LLM → LLM decides next action (tool call)
  3. Execute tool, send result back to LLM
  4. Repeat 2-3 until LLM says WAIT or max iterations reached
  5. Send summary to Telegram (if configured)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from fanpage_agent.adapters.llm_client import build_llm_client

from fanpage_agent.config import Settings
from config import AgentConfig
from tools import (
    TOOL_REGISTRY,
    dispatch_tool,
    get_tool_definitions,
    tool_ops_status,
)


SYSTEM_PROMPT = """Bạn là Fanpage Agent — agent tự động vận hành fanpage Facebook.

## Nhiệm vụ của bạn
Mỗi cycle, bạn kiểm tra trạng thái pipeline và quyết định action nào cần làm.
Mục tiêu: đảm bảo fanpage hoạt động trơn tru — có nội dung mới đều đặn, 
comments được xử lý kịp thời, và không có pending items tồn đọng.

## Quy tắc quyết định
1. Kiểm tra ops_status ĐẦU TIÊN — gọi ops_status() để biết overall state
2. Dựa trên kết quả, ưu tiên xử lý theo thứ tự:
   - 🔴 *Publish*: items đã approved + đến hạn → scheduled_publish
   - 🟡 *Approval*: pending calendar items → review, approve/reject
   - 🟢 *Community*: new comments → fetch_fb_comments → triage_community → review/reply
   - 🔵 *Calendar gaps*: sắp hết nội dung → fill_calendar_gaps / run_daily / write_caption
   - ⚪ *Metrics*: đã publish → auto_fetch_metrics / record_post_metrics
   - ⏳ *Không có gì cần làm*: trả về WAIT
3. Không làm quá {max_actions} actions trong 1 cycle
4. Sau mỗi action, gọi lại ops_status() để cập nhật state trước khi quyết định tiếp
5. Nếu một action trả về lỗi, hãy báo cáo lỗi và chuyển sang action khác — không retry vô hạn

## Báo cáo
Khi kết thúc cycle, gọi send_telegram_message() để gửi báo cáo ngắn gọn:
📋 *Báo cáo cycle*
→ Actions đã làm: ...
→ Kết quả: ...
→ Trạng thái hiện tại: ...
"""


class Orchestrator:
    """Autonomous agent orchestrator.

    Usage::

        orchestrator = Orchestrator(settings, agent_config)
        result = orchestrator.run_tick()   # one cycle
        # or
        result = orchestrator.run_daemon() # infinite loop
    """

    def __init__(
        self,
        settings: Settings,
        agent_config: AgentConfig | None = None,
    ) -> None:
        self.settings = settings
        self.config = agent_config or AgentConfig()
        self.client = build_llm_client(settings)
        self.tools = get_tool_definitions()
        self.tick_calls = 0  # total tool calls across all iterations

    # ── public API ─────────────────────────────────────────────

    def run_tick(self) -> dict:
        """Run one autonomous cycle.

        Returns a summary dict describing what was done.
        """
        self.tick_calls = 0
        history: list[dict] = []
        errors: list[str] = []
        start = time.time()

        # --- Step 1: gather initial state ---
        initial_state = tool_ops_status({"reason": "cycle start"})

        # --- Step 2: build messages ---
        messages = self._build_messages(initial_state)

        # --- Step 3: decision loop ---
        for iteration in range(self.config.max_actions_per_tick):
            if self.tick_calls >= self.config.max_tick_calls:
                break

            try:
                response = self.client.chat_with_tools(
                    messages=messages,
                    tools=self.tools,
                )
            except Exception as exc:
                err_msg = f"LLM call failed: {exc}"
                errors.append(err_msg)
                break

            tool_calls = response.get("tool_calls")
            content = response.get("content", "")

            # LLM says WAIT — text response, no tool calls
            if not tool_calls:
                history.append({"type": "llm_response", "content": content})
                break

            # Append the assistant message with tool_calls to message history
            assistant_msg = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": json.dumps(tc.get("function", {}).get("arguments", {}), ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Execute each tool call
            for tc in tool_calls:
                fn_def = tc.get("function", {})
                name = fn_def.get("name", "")
                args = fn_def.get("arguments", {})

                if self.config.allowed_actions and name not in self.config.allowed_actions:
                    err_msg = f"Action {name} not in allowed_actions"
                    errors.append(err_msg)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps({"error": err_msg}, ensure_ascii=False),
                    })
                    continue

                self.tick_calls += 1
                call_start = time.time()

                # Dispatch
                try:
                    result = dispatch_tool(name, args)
                except Exception as exc:
                    result = {"error": f"dispatch failed: {exc}"}

                elapsed = time.time() - call_start
                result["_exec_time_ms"] = int(elapsed * 1000)

                # Log
                history.append({
                    "type": "tool_call",
                    "tool": name,
                    "args": args,
                    "result": result,
                    "elapsed_ms": int(elapsed * 1000),
                })

                # Feed result back to LLM
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(
                        self._sanitize_for_json(result),
                        ensure_ascii=False,
                    ),
                })

        # --- Step 4: build summary ---
        elapsed = time.time() - start
        summary = self._build_summary(initial_state, history, errors, elapsed)

        # --- Step 5: send Telegram report ---
        if self.config.deliver_telegram:
            try:
                self._send_telegram(summary)
            except Exception as exc:
                summary["telegram_error"] = str(exc)

        return summary

    def run_daemon(self) -> None:
        """Infinite loop — run_tick every tick_interval_seconds."""
        tick = 0
        while True:
            tick += 1
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"\n{'='*60}")
            print(f"  Tick #{tick}  |  {now}")
            print(f"{'='*60}")

            try:
                result = self.run_tick()
                actions = len([h for h in result.get("history", []) if h.get("type") == "tool_call"])
                errors = result.get("errors", [])
                print(f"  Actions: {actions}  |  Errors: {len(errors)}")
                if errors:
                    for e in errors[:3]:
                        print(f"  ⚠ {e}")
            except Exception as exc:
                print(f"  ❌ Tick failed: {exc}")

            print(f"  Sleeping {self.config.tick_interval_seconds}s...")
            time.sleep(self.config.tick_interval_seconds)

    # ── internals ──────────────────────────────────────────────

    def _build_messages(self, initial_state: dict) -> list[dict]:
        system = SYSTEM_PROMPT.format(
            max_actions=self.config.max_actions_per_tick,
        )
        if self.config.system_prompt_prefix:
            system = self.config.system_prompt_prefix + "\n\n" + system

        return [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Bắt đầu cycle. Đây là trạng thái hiện tại của fanpage pipeline:\n\n"
                    + json.dumps(initial_state, ensure_ascii=False, indent=2)
                    + "\n\n"
                    "Hãy kiểm tra trạng thái và quyết định hành động. "
                    "Gọi tool cần thiết hoặc trả lời WAIT nếu không có gì cần làm."
                ),
            },
        ]

    def _build_summary(
        self,
        initial_state: dict,
        history: list[dict],
        errors: list[str],
        elapsed: float,
    ) -> dict:
        tool_calls = [h for h in history if h.get("type") == "tool_call"]
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "total_tool_calls": len(tool_calls),
            "errors": errors,
            "history": history,
            "initial_state": initial_state,
        }

    def _send_telegram(self, summary: dict) -> None:
        """Send brief summary to Telegram operator."""
        tool_calls = [
            h for h in summary.get("history", []) if h.get("type") == "tool_call"
        ]
        errors = summary.get("errors", [])
        initial = summary.get("initial_state", {})

        lines = [
            "🤖 *Fanpage Agent — Báo cáo cycle*",
            f"⏱️ `{summary.get('elapsed_seconds', 0)}s` • {len(tool_calls)} action(s)",
        ]
        if tool_calls:
            lines.append("")
            lines.append("*Actions:*")
            for tc in tool_calls:
                name = tc.get("tool", "?")
                result = tc.get("result", {})
                preview = json.dumps(
                    {k: v for k, v in result.items() if not k.startswith("_")},
                    ensure_ascii=False,
                )[:120]
                lines.append(f"  • `{name}` → {preview}")

        if errors:
            lines.append("")
            lines.append(f"⚠️ *Lỗi:* {len(errors)}")
            for e in errors[:3]:
                lines.append(f"  • {e}")

        # Calendar state
        cal = initial.get("calendar", {})
        com = initial.get("community", {})
        lines.append("")
        lines.append("*Trạng thái:*")
        lines.append(f"  📅 Pending: {cal.get('pending_approval', '?')} • Sẵn sàng: {cal.get('approved_ready', '?')} • Đã pub: {cal.get('published', '?')}")
        lines.append(f"  💬 Triage pending: {com.get('pending_triage', '?')}")

        text = "\n".join(lines)

        from fanpage_agent.adapters.telegram_client import TelegramClient

        client = TelegramClient(self.settings)
        client.send_message(
            text=text,
            chat_id=self.settings.telegram_chat_id,
            parse_mode="Markdown",
        )

    @staticmethod
    def _sanitize_for_json(obj: Any) -> Any:
        """Remove non-serializable values for JSON output."""
        if isinstance(obj, dict):
            return {k: Orchestrator._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [Orchestrator._sanitize_for_json(v) for v in obj]
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        return str(obj)
