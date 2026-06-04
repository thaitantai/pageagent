"""OrchestratorAgent — the V2 master coordinator that drives the pipeline.

On each tick, the orchestrator:
1. Gathers state (calendar, community, performance from all agents)
2. Decides what to do next (priority-based decision)
3. Delegates tasks to specialized agents
4. Consolidates results
5. Produces output (publish / report / learn)
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fanpage_agent_v2.core.agent import BaseAgent
from fanpage_agent_v2.core.types import (
    ActionPriority,
    AgentRole,
    AgentResult,
    AgentTask,
    PipelineState,
)
from fanpage_agent_v2.core.bus import AgentBus


class OrchestratorAgent(BaseAgent):
    """Master coordinator — drives the multi-agent content pipeline.

    Orchestrator does NOT generate content itself. It decides WHAT to do
    and delegates to specialized agents via AgentBus.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        bus: AgentBus | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        super().__init__(config)
        self._bus = bus or AgentBus()
        self._state_path = Path(state_path) if state_path else Path("data/v2/state.json")
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._tick_count = 0
        self._started_at = time.time()
        self._last_state: PipelineState | None = None

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

    def register_all(self, agents: list[BaseAgent]) -> None:
        """Register all agents at once."""
        for agent in agents:
            self._bus.register(agent)

    # ── Pipeline ────────────────────────────────────────────────

    def _tick(self) -> AgentResult:
        """Main tick — the entry point called by the scheduler.

        Flow:
        1. Gather state from agents (calendar, community, performance)
        2. Decide what to do
        3. Execute decisions
        4. Report
        """
        self._tick_count += 1
        tick_id = f"tick-{uuid.uuid4().hex[:8]}"
        tick_start = time.time()

        # Step 1: Gather state
        pipeline_state = self._gather_state()

        # Step 2: Decide actions (community, analyst, etc.)
        actions = self._decide_actions(pipeline_state)

        # Step 2b: Auto-generate content if calendar is empty or periodic
        if self._should_generate_content(pipeline_state):
            self._log_content_gen()
            gen_result = self._run_pipeline(mode="full")
            if gen_result.success:
                pipeline_state.published_today += 1
            else:
                pipeline_state.errors_24h += 1

        # Step 3: Execute
        results = []
        for priority, action in actions:
            task = self._bus.create_task(
                target=action["agent"],
                action=action["action"],
                params=action.get("params", {}),
                priority=priority,
            )
            result = self._bus.dispatch(task)
            results.append(result)

        elapsed = time.time() - tick_start

        # Step 4: Summarise
        summary_data = {
            "tick_id": tick_id,
            "tick_number": self._tick_count,
            "elapsed_ms": int(elapsed * 1000),
            "state": pipeline_state.to_dict(),
            "actions_taken": [
                {"action": r.task_id, "success": r.success}
                for r in results if r
            ],
            "state_path": str(self._state_path),
        }

        # Persist state
        self._last_state = pipeline_state
        self._save_state(pipeline_state)

        return AgentResult(
            task_id=tick_id,
            success=True,
            data=summary_data,
        )

    def _run_pipeline(self, mode: str = "full") -> AgentResult:
        """Run a specific pipeline phase."""
        pipeline_state = self._gather_state()

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
                r = self._bus.dispatch(self._bus.create_task(
                    AgentRole.RESEARCHER, "research_trends", {"pillars": []}
                ))
                if r.success and r.data:
                    research_data = r.data.get("brief")
                results.append(r)
            elif step == "strategy":
                params = {"days": 1}
                if research_data:
                    params["research_brief"] = research_data
                r = self._bus.dispatch(self._bus.create_task(
                    AgentRole.STRATEGIST, "plan_weekly", params
                ))
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
                # Fallback if strategist returned empty topics
                if not topic.strip():
                    topic = "Chăm sóc da dầu mụn cho GenZ"
                    pillar = pillar or "education"
                r = self._bus.dispatch(self._bus.create_task(
                    AgentRole.WRITER, "write_variants",
                    {"variants": 2, "topic": topic, "pillar": pillar},
                ))
                if r.success and r.data:
                    writer_package = r.data  # ContentPackage dataclass
                results.append(r)
            elif step == "design":
                r = self._bus.dispatch(self._bus.create_task(
                    AgentRole.DESIGNER, "generate_brief", {"format": "text_image"}
                ))
                results.append(r)
            elif step == "publish":
                # Compose message from writer's best variant
                message, image_path = self._compose_message(writer_package)
                r = self._bus.dispatch(self._bus.create_task(
                    AgentRole.PUBLISHER, "publish_due",
                    {"message": message, "image_path": image_path},
                ))
                results.append(r)

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
        from fanpage_agent_v2.core.types import ContentPackage  # local import

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
                "v2_data_path": str(self._state_path.parent),
            },
        )

    # ── Internals ───────────────────────────────────────────────

    def _gather_state(self) -> PipelineState:
        """Collect state from all agents and data sources."""
        state = PipelineState()

        # Analyst state
        analyst_result = self._bus.dispatch(self._bus.create_task(
            AgentRole.ANALYST, "weekly_report",
            priority=ActionPriority.LOW,
        ))
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
            actions.append((ActionPriority.CRITICAL, {
                "agent": AgentRole.PUBLISHER,
                "action": "publish_due",
            }))

        # Community: fetch + triage (every 3 ticks when FB adapter available)
        if self._tick_count % 3 == 1:  # tick #1, #4, #7, ...
            actions.append((ActionPriority.HIGH, {
                "agent": AgentRole.COMMUNITY,
                "action": "fetch_and_triage",
                "params": {"limit": 50},
            }))
            # Auto-reply after fetch (limit to 5 per tick to be safe)
            actions.append((ActionPriority.HIGH, {
                "agent": AgentRole.COMMUNITY,
                "action": "auto_reply",
                "params": {"limit": 5, "max_replies": 3},
            }))
        elif state.pending_triage > 0 or state.new_comments_24h > 0:
            actions.append((ActionPriority.HIGH, {
                "agent": AgentRole.COMMUNITY,
                "action": "triage_comments",
                "params": {"limit": 20},
            }))

        # Priority 2: Content planning if calendar has gaps
        if state.calendar_gap_days:
            actions.append((ActionPriority.MEDIUM, {
                "agent": AgentRole.STRATEGIST,
                "action": "plan_weekly",
                "params": {"days": 3},
            }))

        # Priority 3: Analytics (every tick)
        actions.append((ActionPriority.LOW, {
            "agent": AgentRole.ANALYST,
            "action": "weekly_report",
        }))

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
        import sys
        print(
            f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}] "
            f"🔄 auto-generating content (tick #{self._tick_count})",
            flush=True,
        )

    def _save_state(self, state: PipelineState) -> None:
        """Persist pipeline state to disk."""
        import json
        try:
            data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tick": self._tick_count,
                "state": state.to_dict(),
            }
            self._state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            pass  # Non-critical, don't crash the tick
