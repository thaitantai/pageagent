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

from config import AgentConfig
from fanpage_agent.adapters.llm import build_llm_client
from fanpage_agent.config import Settings
from tools import (
    dispatch_tool,
    get_tool_definitions,
    tool_ops_status,
)

SYSTEM_PROMPT = """Bạn là Fanpage Agent — agent tự động vận hành fanpage Facebook.

## Nhiệm vụ của bạn
Mỗi cycle, bạn kiểm tra pipeline và quyết định action cần làm.
Mục tiêu: fanpage hoạt động trơn tru — nội dung mới đều đặn,
comments xử lý kịp thời, không có pending items tồn đọng, và
dữ liệu metrics được thu thập đầy đủ.

## Tool reference (gọi những tool này)

`ops_status` — Lấy snapshot trạng thái, GỌI ĐẦU TIÊN mỗi cycle
`list_calendar_items` — Xem calendar stats (pending/approved/published)
`list_triage_items` — Xem triage inbox stats
`fill_calendar_gaps` — Tự động phát hiện ngày trống + viết caption + verify + auto-approve
`write_caption` — Viết 1 caption cho 1 topic cụ thể
`run_daily` — Full pipeline: research → plan → write → verify → queue (7 ngày)
`approve_calendar_item` / `reject_calendar_item` — Duyệt/từ chối 1 calendar item
`triage_community` — LLM phân loại comments pending
`approve_triage_reply` / `reject_triage_reply` — Duyệt/từ chối reply cho comment
`scheduled_publish` — Publish items đã approved + đến hạn
`fetch_fb_data` — Fetch full data (posts + metrics + comments) from Facebook → populate store. Dùng để refresh dữ liệu cho ResearchAgent. Parameters: post_limit (default 90), comment_posts (default 20), comment_limit (default 25), skip_comments (default false)
`fetch_fb_comments` — Fetch comments mới từ Facebook
`record_post_metrics` — Fetch metrics cho posts đã publish
`send_telegram_message` — Gửi báo cáo cho operator

## Quy tắc quyết định (priority order)
### 1️⃣ ops_status ALWAYS first
Gọi `ops_status` ngay khi cycle bắt đầu. Dùng kết quả quyết định bước tiếp.

### 2️⃣ Publish first (🔴)
Nếu có approved + due items → gọi `scheduled_publish`.
Đây là priority cao nhất — tránh miss lịch đăng.

### 3️⃣ Calendar gaps (🔵)
Nếu calendar sắp hết nội dung (pending_approval thấp, approved_ready sắp hết):
→ Gọi `fill_calendar_gaps` TRƯỚC (nhẹ, auto 3 ngày), chỉ gọi `run_daily` nếu cần nhiều hơn

### 4️⃣ Community (🟢)
Nếu có new comments:
→ `fetch_fb_comments` → `triage_community` → review kết quả → approve/reject

### 5️⃣ Approval (🟡)
Nếu có pending calendar items:
→ `list_calendar_items` → xem chi tiết → approve những cái đạt yêu cầu,
reject những cái lỗi. Dùng phán đoán của bạn.

### 6️⃣ Metrics (⚪)
Đã publish → `record_post_metrics` để thu thập dữ liệu.

### 7️⃣ WAIT (⏳)
Không có gì cần làm → trả lời text "WAIT". Không gọi tool.

## Các lưu ý quan trọng
• Luôn gọi `ops_status` sau mỗi action để cập nhật state
• Maximum {max_actions} actions / cycle — chọn lọc, không làm tất cả
• Lỗi → báo cáo lỗi + chuyển action khác (không retry vô hạn)
• Thứ tự ưu tiên: Publish > Gaps > Community > Approval > Metrics
• Không cần approve/reject từng cái — chọn những cái rõ ràng nhất
• Ưu tiên `fill_calendar_gaps` hơn `run_daily` vì nhẹ hơn và auto hơn

## Báo cáo Telegram
Kết thúc cycle, gọi `send_telegram_message` với format:

📋 *Báo cáo cycle*
📅 [thời gian] UTC
• Actions đã làm: publish (1), fill_gaps (3), triage (5)
• Trạng thái: 📅 Pending: X • Sẵn sàng: Y • Đã pub: Z | 💬 Triage: W

(Số liệu lấy từ `ops_status` cuối cùng + action results)
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

    def run_tick(self, tick_num: int = 0) -> dict:
        """Run one autonomous cycle.

        Args:
            tick_num: Optional tick number for reporting (0 = one-shot).

        Returns a summary dict describing what was done.
        """
        self.tick_calls = 0
        history: list[dict] = []
        errors: list[str] = []
        start = time.time()

        # --- Step 1: gather initial state ---
        initial_state = tool_ops_status({"reason": "cycle start"})
        initial_state["tick_count"] = tick_num

        # --- Step 2: build messages ---
        messages = self._build_messages(initial_state)

        # --- Step 3: decision loop ---
        for iteration in range(self.config.max_actions_per_tick):
            if self.tick_calls >= self.config.max_tick_calls:
                break

            # Retry LLM call up to 3 times with backoff
            response = None
            llm_error = None
            for attempt in range(3):
                try:
                    response = self.client.chat_with_tools(
                        messages=messages,
                        tools=self.tools,
                    )
                    llm_error = None
                    break
                except Exception as exc:
                    llm_error = str(exc)
                    if attempt < 2:
                        wait = (attempt + 1) * 5
                        err_msg = f"LLM call failed (attempt {attempt+1}/3): {exc} — retrying in {wait}s"
                        errors.append(err_msg)
                        time.sleep(wait)
                    else:
                        err_msg = f"LLM call failed after 3 attempts: {exc}"
                        errors.append(err_msg)

            if llm_error:
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
                result = self.run_tick(tick_num=tick)
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

        tick_num = initial.get("tick_count", 1)
        lines = [
            "🤖 *Báo cáo cycle*",
            f"Tick #{tick_num}  ⏱️ {summary.get('elapsed_seconds', 1):.0f}s  📌 {len(tool_calls)} actions",
        ]
        if tool_calls:
            action_summary = []
            for tc in tool_calls:
                name = tc.get("tool", "?")
                result = tc.get("result", {})
                ok = "❌" if result.get("error") or any(k.startswith("error") for k in result) else "✅"
                # Compact action summary
                brief = ""
                if "filled_count" in result:
                    brief = f" +{result.get('filled_count', 0)} filled"
                elif "total" in result and "items" in result:
                    brief = f" {result.get('total', 0)} items"
                elif result.get("sent"):
                    brief = " sent"
                elif result.get("approved"):
                    brief = f" {result.get('approved', '')}"
                action_summary.append(f"{ok}`{name}`{brief}")
            lines.append("")
            lines.append("▸ " + " • ".join(action_summary))

        if errors:
            lines.append("")
            lines.append(f"⚠️ *{len(errors)} lỗi:*")
            for e in errors[:2]:
                lines.append(f"  • {e}")

        # Compact state
        cal = initial.get("calendar", {})
        com = initial.get("community", {})
        pub = cal.get("published", "?")
        pend = cal.get("pending_approval", "?")
        ready = cal.get("approved_ready", "?")
        triage = com.get("pending_triage", 0)
        lines.append("")
        lines.append(f"📅 P:{pend} R:{ready} P:{pub}  💬 T:{triage}")

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
