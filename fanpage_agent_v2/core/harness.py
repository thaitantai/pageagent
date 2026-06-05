"""Execution harness for V2 agents.

The harness is the safety and observability layer around agent execution. It
validates whether a task is allowed, executes the agent, and records an audit
trail that can be inspected by operators or tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from fanpage_agent_v2.core.types import AgentResult, AgentRole, AgentTask


@dataclass(frozen=True)
class HarnessPolicy:
    """Runtime permissions for the agent bus."""

    allowed_actions: dict[AgentRole, set[str]] = field(default_factory=dict)
    blocked_actions: set[str] = field(default_factory=set)
    approval_required_actions: set[str] = field(default_factory=lambda: {
        "publish_now",
        "force_publish",
        "publish_post",
        "publish_package",
        "publish_due",
        "delete_post",
    })
    max_payload_chars: int = 120_000

    def is_action_allowed(
        self,
        task: AgentTask,
        agent_role: AgentRole,
        capabilities: list[str],
    ) -> tuple[bool, str | None]:
        if task.action in self.blocked_actions:
            return False, f"Action '{task.action}' is blocked by harness policy"

        allowed_for_role = self.allowed_actions.get(agent_role)
        if allowed_for_role is not None and task.action not in allowed_for_role:
            return False, f"Action '{task.action}' is not allowed for {agent_role.value}"

        if task.action not in capabilities:
            return False, f"Agent {agent_role.value} cannot handle action '{task.action}'"

        payload_size = len(str(task.params)) + len(str(task.context))
        if payload_size > self.max_payload_chars:
            return False, f"Task payload too large: {payload_size} chars"

        if task.action in self.approval_required_actions and not task.context.get("approved"):
            return False, f"Action '{task.action}' requires explicit approval"

        return True, None


@dataclass
class HarnessEvent:
    task_id: str
    action: str
    agent: str
    status: str
    reason: str | None = None
    elapsed_ms: int | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "agent": self.agent,
            "status": self.status,
            "reason": self.reason,
            "elapsed_ms": self.elapsed_ms,
            "created_at": self.created_at,
        }


class RunnableAgent(Protocol):
    @property
    def role(self) -> AgentRole: ...

    @property
    def capabilities(self) -> list[str]: ...

    def process(self, task: AgentTask) -> AgentResult: ...


class AgentHarness:
    """Guarded execution wrapper used by AgentBus."""

    def __init__(self, policy: HarnessPolicy | None = None, audit_manager: Any | None = None) -> None:
        self.policy = policy or HarnessPolicy()
        self._audit_manager = audit_manager
        self._events: list[HarnessEvent] = []

    def run(self, agent: RunnableAgent, task: AgentTask) -> AgentResult:
        allowed, reason = self.policy.is_action_allowed(task, agent.role, agent.capabilities)
        if not allowed:
            event = HarnessEvent(
                task_id=task.id,
                action=task.action,
                agent=agent.role.value,
                status="blocked",
                reason=reason,
            )
            self._record_event(event)
            return AgentResult(
                task_id=task.id,
                success=False,
                error=f"Harness blocked task: {reason}",
                metrics={"agent_role": agent.role.value, "harness_status": "blocked"},
            )

        result = agent.process(task)
        status = "success" if result.success else "failed"
        elapsed_ms = result.metrics.get("elapsed_ms") if result.metrics else None
        self._record_event(HarnessEvent(
            task_id=task.id,
            action=task.action,
            agent=agent.role.value,
            status=status,
            reason=result.error,
            elapsed_ms=elapsed_ms,
        ))
        result.metrics["harness_status"] = status
        return result

    def _record_event(self, event: HarnessEvent) -> None:
        self._events.append(event)
        if self._audit_manager is None:
            return
        self._audit_manager.record(
            event_type=f"harness.{event.status}",
            source="AgentHarness",
            event_data={
                "task_id": event.task_id,
                "action": event.action,
                "agent": event.agent,
                "reason": event.reason,
            },
            success=event.status == "success",
            duration_ms=event.elapsed_ms,
            error=event.reason if event.status != "success" else None,
        )

    @property
    def events(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events]

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for event in self._events:
            counts[event.status] = counts.get(event.status, 0) + 1
        return {"events": len(self._events), "counts": counts, "recent": self.events[-10:]}
