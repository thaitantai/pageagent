"""OrchestratorAgent — the master coordinator that drives the pipeline.

On each tick, the orchestrator:
1. Gathers state (calendar, community, performance from all agents)
2. Decides what to do next (priority-based decision)
3. Delegates tasks to specialized agents
4. Consolidates results
5. Produces output (publish / report / learn)
6. Cycles through configured pages round-robin
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fanpage_agent.core.agent import BaseAgent
from fanpage_agent.core.bus import AgentBus
from fanpage_agent.core.types import (
    ActionPriority,
    AgentResult,
    AgentRole,
    AgentTask,
    PipelineState,
)


class OrchestratorAgent(BaseAgent):
    """Master coordinator — drives the multi-agent content pipeline.

    Orchestrator does NOT generate content itself. It decides WHAT to do
    and delegates to specialized agents via AgentBus.

    Supports multi-page: cycles through ``page_ids`` round-robin on each
    tick, injecting ``page_id`` into task params so downstream agents
    (publisher, community) operate on the correct page.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        bus: AgentBus | None = None,
        state_path: str | Path | None = None,
        page_ids: list[str] | None = None,
    ) -> None:
        super().__init__(config)
        self._bus = bus or AgentBus()
        self._state_path = Path(state_path) if state_path else Path("data/agent/state.json")
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._tick_count = 0
        self._started_at = time.time()
        self._last_state: PipelineState | None = None
        self._page_ids = page_ids or ["main"]
        self._page_index = 0

    @property
    def role(self) -> AgentRole:
        return AgentRole.ORCHESTRATOR

    @property
    def capabilities(self) -> list[str]:
        return ["tick", "run_pipeline", "status", "force_publish"]

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params

        if action == "tick":
            return self._tick()
        elif action == "run_pipeline":
            return self._run_pipeline(
                mode=params.get("mode", "full"),
            )
        elif action == "status":
            return self._status()
        return AgentResult(task_id=task.id, success=False, error=f"Unknown action: {action}")

    # ── Public API ──────────────────────────────────────────────

    def register_agent(self, agent: BaseAgent) -> None:
        """Register a specialized agent with the bus."""
        self._bus.register(agent)
        agent.set_bus(self._bus)  # type: ignore  — _bus is always AgentBus at runtime

    def register_all(self, agents: list[BaseAgent]) -> None:
        """Register all agents at once."""
        for agent in agents:
            self._bus.register(agent)
            agent.set_bus(self._bus)  # type: ignore

    # ── Multi-page helpers ──────────────────────────────────────

    @property
    def current_page_id(self) -> str | None:
        """Page selected for this tick (None for single-page mode)."""
        if not self._page_ids:
            return None
        return self._page_ids[self._page_index]

    def _cycle_page(self) -> str | None:
        """Advance round-robin and return the next page_id."""
        pid = self.current_page_id
        self._page_index = (self._page_index + 1) % max(len(self._page_ids), 1)
        return pid

    # ── Pipeline ────────────────────────────────────────────────

    def _tick(self) -> AgentResult:
        """Main tick — 2-phase choreography.

        Phase 1: Gather state + broadcast heartbeat to shared_state
        Phase 2: Self-driving agents propose actions, orchestrator dispatches
                 (content generation pipeline still orchestrated as before)

        Each tick operates on one page (round-robin).
        """
        self._tick_count += 1
        tick_id = f"tick-{uuid.uuid4().hex[:8]}"
        tick_start = time.time()

        page_id = self._cycle_page()

        # ── Phase 1: Gather state + broadcast heartbeat ──────────
        pipeline_state = self._gather_state()
        self._bus.update_shared_state(
            AgentRole.ORCHESTRATOR,
            {
                "heartbeat": time.time(),
                "tick_count": self._tick_count,
                "state": pipeline_state.to_dict(),
                "current_page_id": page_id,
            },
        )

        # ── Phase 2a: Set pipeline trigger if content is needed ──
        # Agents self-coordinate via shared_state (choreography chain)
        if self._should_generate_content(pipeline_state):
            self._log_content_gen()
            self._bus.shared_state["pipeline_trigger"] = True  # type: ignore
            self._bus.shared_state["pipeline_trigger_at"] = time.time()  # type: ignore

        # ── Phase 2b: Self-driving agents propose actions ────────
        results: list[AgentResult] = []
        for agent in self._bus._agents.values():
            if agent.role == AgentRole.ORCHESTRATOR:
                continue
            if not hasattr(agent, "self_driving_tick"):
                continue
            try:
                proposals = agent.self_driving_tick()
                for action_name, params, priority in proposals:
                    # Inject current page_id so downstream agents know which page
                    if page_id is not None:
                        params["page_id"] = page_id
                    task = self._bus.create_task(
                        target=agent.role,
                        action=action_name,
                        params=params,
                        priority=priority,
                    )
                    result = self._bus.dispatch(task)
                    results.append(result)
            except Exception:
                pass

        elapsed = time.time() - tick_start

        # ── Summarise ────────────────────────────────────────────
        summary_data = {
            "tick_id": tick_id,
            "tick_number": self._tick_count,
            "page_id": page_id,
            "elapsed_ms": int(elapsed * 1000),
            "state": pipeline_state.to_dict(),
            "actions_taken": [{"action": r.task_id, "success": r.success} for r in results if r],
            "state_path": str(self._state_path),
        }

        self._last_state = pipeline_state
        self._save_state(pipeline_state)

        return AgentResult(
            task_id=tick_id,
            success=True,
            data=summary_data,
        )

    def _run_pipeline(self, mode: str = "full", page_id: str | None = None) -> AgentResult:
        """Run a specific pipeline phase."""
        page_id = page_id or self.current_page_id

        steps: list[str] = []
        if mode in ("full", "planning"):
            steps.extend(["research", "strategy", "ideation"])
        if mode in ("full", "creation"):
            steps.extend(["writing", "design"])
        if mode in ("full", "publishing"):
            steps.append("publish")

        results = []
        research_data: dict | None = None
        strategist_data: dict | None = None
        writer_package = None  # ContentPackage from writer

        for step in steps:
            if step == "research":
                r = self._bus.dispatch(
                    self._bus.create_task(AgentRole.RESEARCHER, "research_trends", {"pillars": []})
                )
                if r.success and r.data:
                    research_data = r.data.get("brief")
                results.append(r)
            elif step == "strategy":
                params: dict = {"days": 1}
                if research_data:
                    params["research_brief"] = research_data
                r = self._bus.dispatch(
                    self._bus.create_task(AgentRole.STRATEGIST, "plan_weekly", params)
                )
                if r.success and r.data:
                    strategist_data = r.data
                results.append(r)
            elif step == "writing":
                # Get topic + pillar from strategist's day-0 schedule
                topic = ""
                pillar = ""
                if strategist_data and strategist_data.get("schedule"):
                    day0 = strategist_data["schedule"][0]
                    topic = day0.get("topic_template", "")
                    pillar = day0.get("pillar", "")
                # Fallback if strategist returned empty topics — use seasonal engine
                if not topic.strip():
                    topic, pillar = self._seasonal_topic_and_pillar(pillar)
                r = self._bus.dispatch(
                    self._bus.create_task(
                        AgentRole.WRITER,
                        "write_variants",
                        {"variants": 2, "topic": topic, "pillar": pillar},
                    )
                )
                if r.success and r.data:
                    writer_package = r.data  # ContentPackage dataclass
                results.append(r)
            elif step == "design":
                r = self._bus.dispatch(
                    self._bus.create_task(
                        AgentRole.DESIGNER, "generate_brief", {"format": "text_image"}
                    )
                )
                results.append(r)
            elif step == "publish":
                # Compose message from writer's best variant
                message, image_path = self._compose_message(writer_package)
                pub_params: dict[str, Any] = {"message": message, "image_path": image_path}
                if page_id is not None:
                    pub_params["page_id"] = page_id
                pub_result = self._bus.dispatch(
                    self._bus.create_task(
                        AgentRole.PUBLISHER,
                        "publish_due",
                        pub_params,
                    )
                )
                results.append(pub_result)

                # ── Self-reply on new post for early engagement ──
                fb_post_id = pub_result.data.get("fb_post_id", "") if pub_result.success else ""
                if fb_post_id:
                    topic = (
                        writer_package.best_variant().topic
                        if writer_package and hasattr(writer_package, "best_variant")
                        else ""
                    )
                    self_reply_params: dict[str, Any] = {"fb_post_id": fb_post_id, "topic": topic}
                    if page_id is not None:
                        self_reply_params["page_id"] = page_id
                    self_reply = self._bus.dispatch(
                        self._bus.create_task(
                            AgentRole.COMMUNITY,
                            "self_reply_post",
                            self_reply_params,
                        )
                    )
                    results.append(self_reply)

                # ── Track performance after publish ──
                if fb_post_id:
                    variant_id = ""
                    pkg_id = None
                    if writer_package:
                        if hasattr(writer_package, "best_variant"):
                            v = writer_package.best_variant()
                            if v:
                                variant_id = v.variant_id
                        if hasattr(writer_package, "package_id"):
                            pkg_id = writer_package.package_id
                    track_params: dict[str, Any] = {
                        "fb_post_id": fb_post_id,
                        "variant_id": variant_id,
                        "package_id": pkg_id,
                    }
                    if page_id is not None:
                        track_params["page_id"] = page_id
                    track_result = self._bus.dispatch(
                        self._bus.create_task(
                            AgentRole.PUBLISHER,
                            "track_performance",
                            track_params,
                        )
                    )
                    results.append(track_result)

        return AgentResult(
            task_id=f"pipeline-{mode}",
            success=True,
            data={"mode": mode, "steps_run": steps, "results": [r.completed_at for r in results]},
        )

    @staticmethod
    def _compose_message(package) -> tuple[str, str | None]:
        """Extract message text and image_path from a ContentPackage (or dict).

        Returns (message_string, image_path_or_None).
        """
        from fanpage_agent.core.types import ContentPackage  # local import

        variant = None
        if package is None:
            pass
        elif isinstance(package, ContentPackage):
            variant = package.best_variant()
        elif isinstance(package, dict):
            try:
                pkg = ContentPackage(**package)
                variant = pkg.best_variant()
            except Exception:
                variant = None

        if variant is None:
            return "Tin tức làm đẹp mỗi ngày ✨", None

        parts = []
        if variant.hook:
            parts.append(f"💡 {variant.hook}")
        if variant.caption:
            parts.append(variant.caption)
        if variant.cta:
            parts.append(variant.cta)
        if variant.hashtags:
            parts.append(" ".join(f"#{t.lstrip('#')}" for t in variant.hashtags))

        message = "\n\n".join(parts) if parts else "Tin tức làm đẹp mỗi ngày ✨"
        return message, variant.image_path

    def _status(self) -> AgentResult:
        """Return current orchestrator status."""
        state = self._last_state or self._gather_state()
        uptime_h = (time.time() - self._started_at) / 3600
        return AgentResult(
            task_id="status",
            success=True,
            data={
                "uptime_hours": round(uptime_h, 1),
                "ticks": self._tick_count,
                "agents": self._bus.registered_roles,
                "dispatches": len(self._bus.history),
                "state": state.to_dict(),
                "data_path": str(self._state_path.parent),
                "page_ids": self._page_ids,
                "page_index": self._page_index,
            },
        )

    # ── Internals ───────────────────────────────────────────────

    def _gather_state(self) -> PipelineState:
        """Collect state from all agents and data sources."""
        state = PipelineState()

        # Analyst state
        analyst_result = self._bus.dispatch(
            self._bus.create_task(
                AgentRole.ANALYST,
                "weekly_report",
                priority=ActionPriority.LOW,
            )
        )
        if analyst_result and analyst_result.success and isinstance(analyst_result.data, dict):
            state.weekly_post_count = analyst_result.data.get("total_posts", 0)
            state.avg_reach_7d = analyst_result.data.get("avg_reach", 0)
            state.avg_engagement_7d = analyst_result.data.get("avg_engagement", 0)
            pillars = analyst_result.data.get("pillars", [])
            if pillars:
                state.top_pillar_last_7d = pillars[0].get("pillar") if pillars else None

        state.last_tick_status = "ok"
        state.uptime_hours = (time.time() - self._started_at) / 3600
        return state

    def _decide_actions(self, state: PipelineState) -> list[tuple[ActionPriority, dict]]:
        """Decide what actions to take based on pipeline state.

        Returns a list of (priority, action_dict) tuples.
        """
        actions: list[tuple[ActionPriority, dict]] = []

        # Priority 1: Check if publishing is due
        if state.approved_ready > 0 or state.next_publish_due:
            actions.append(
                (
                    ActionPriority.CRITICAL,
                    {
                        "agent": AgentRole.PUBLISHER,
                        "action": "publish_due",
                    },
                )
            )

        # Community: fetch + triage (every 3 ticks when FB adapter available)
        if self._tick_count % 3 == 1:  # tick #1, #4, #7, ...
            actions.append(
                (
                    ActionPriority.HIGH,
                    {
                        "agent": AgentRole.COMMUNITY,
                        "action": "fetch_and_triage",
                        "params": {"limit": 50},
                    },
                )
            )
            # Auto-reply after fetch (limit to 5 per tick to be safe)
            actions.append(
                (
                    ActionPriority.HIGH,
                    {
                        "agent": AgentRole.COMMUNITY,
                        "action": "auto_reply",
                        "params": {"limit": 5, "max_replies": 3},
                    },
                )
            )
        elif state.pending_triage > 0 or state.new_comments_24h > 0:
            actions.append(
                (
                    ActionPriority.HIGH,
                    {
                        "agent": AgentRole.COMMUNITY,
                        "action": "triage_comments",
                        "params": {"limit": 20},
                    },
                )
            )

        # Priority 2: Content planning if calendar has gaps
        if state.calendar_gap_days:
            actions.append(
                (
                    ActionPriority.MEDIUM,
                    {
                        "agent": AgentRole.STRATEGIST,
                        "action": "plan_weekly",
                        "params": {"days": 3},
                    },
                )
            )

        # Priority 3: Analytics (every tick)
        actions.append(
            (
                ActionPriority.LOW,
                {
                    "agent": AgentRole.ANALYST,
                    "action": "weekly_report",
                },
            )
        )

        # Periodic metric refresh every 3 ticks
        if self._tick_count > 0 and self._tick_count % 3 == 0:
            actions.append(
                (
                    ActionPriority.LOW,
                    {
                        "agent": AgentRole.PUBLISHER,
                        "action": "refresh_metrics",
                        "params": {"limit": 10},
                    },
                )
            )

        return actions

    def _should_generate_content(self, state: PipelineState) -> bool:
        """Check if we need to auto-generate content this tick.

        Triggers when:
        - No posts published yet (fresh start)
        - Nothing scheduled for today/tomorrow
        - Every 2 ticks (periodic refresh, ~4h cycle)
        """
        calendar_empty = (
            state.published_today == 0
            and state.approved_ready == 0
            and not state.next_publish_due
            and not state.calendar_gap_days
        )
        periodic_refresh = self._tick_count > 0 and self._tick_count % 2 == 0
        return calendar_empty or periodic_refresh

    def _log_content_gen(self) -> None:
        """Log content generation start to stdout (visible in Docker logs)."""
        print(
            f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}] "
            f"🔄 auto-generating content (tick #{self._tick_count})",
            flush=True,
        )

    @staticmethod
    def _seasonal_topic_and_pillar(current_pillar: str = "") -> tuple[str, str]:
        """Generate a seasonally-relevant topic & pillar based on current month."""
        month = datetime.now(timezone.utc).month
        pillar = current_pillar or "education"

        if month in (1, 2):
            topics = [
                "Chăm sóc da ngày Tết: ăn bánh chưng không lo lên mụn",
                "Da đổ dầu ngày Tết? Mẹo skincare cấp tốc cho GenZ",
                "Bí kíp giữ da đẹp xuyên Tết dù thức khuya liên tục",
                "Skincare routine Tết: tối giản vẫn hiệu quả",
            ]
            pillar = "entertainment"
        elif month in (3, 4):
            topics = [
                "Da 'nổi loạn' mùa giao mùa? 3 bước ổn định ngay",
                "Giao mùa rồi, da dầu càng đổ dầu — cứu sao đây?",
                "Skin barrier: tại sao da bạn yếu hơn vào tháng 3-4?",
                "Mẹo chăm da mùa giao mùa cho GenZ: ít mà đúng",
            ]
            pillar = "education"
        elif month in (5, 6):
            topics = [
                "Chống nắng mùa hè: đừng để da cháy nắng khi đi chơi",
                "Da đổ dầu như 'đổ xăng' mùa hè? Cách kiểm soát",
                "Top 3 kem chống nắng cho da dầu mụn mùa hè 2026",
                "Mồ hôi + dầu = mụn? Mẹo skincare mùa nóng",
            ]
            pillar = "review"
        elif month in (7, 8):
            topics = [
                "Mùa mưa ẩm: da dầu càng 'khổ' — làm sao đây?",
                "Maskne mùa mưa: bí kíp giữ da thông thoáng",
                "Độ ẩm cao làm da đổ dầu nhiều hơn? Sự thật bất ngờ",
                "Skincare mùa mưa: 3 sản phẩm KHÔNG thể thiếu",
            ]
            pillar = "trust"
        elif month in (9, 10):
            topics = [
                "Tựu trường rồi: skincare tối giản trong dorm cho GenZ",
                "Budget skincare cho sinh viên: rẻ mà vẫn hiệu quả",
                "Áp lực học tập làm da xấu đi? Mẹo skincare cho mùa thi",
                "Dorm skincare: 4 bước cơ bản không thể thiếu",
            ]
            pillar = "trust"
        else:  # 11-12
            topics = [
                "Cuối năm rồi: da dầu có cần dưỡng ẩm nhiều hơn không?",
                "Review năm cũ: sản phẩm skincare nào đáng mua lại?",
                "Mùa lạnh + da dầu = 3 lỗi ai cũng mắc phải",
                "Năm mới, da mới: mục tiêu skincare 2027 cho GenZ",
            ]
            pillar = "review"

        import random

        topic = random.choice(topics)
        return topic, pillar

    def _save_state(self, state: PipelineState) -> None:
        """Persist pipeline state to disk."""
        import json

        try:
            data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tick": self._tick_count,
                "page_ids": self._page_ids,
                "page_index": self._page_index,
                "state": state.to_dict(),
            }
            self._state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            pass  # Non-critical, don't crash the tick
