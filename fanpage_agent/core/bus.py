"""AgentBus — inter-agent communication and orchestration hub.

The bus provides:
1. Agent registration (agents register with the bus)
2. Task dispatch (orchestrator sends tasks, bus routes to the right agent)
3. Priority queue (tasks ordered by priority)
"""

from __future__ import annotations

import uuid
from typing import Any

from fanpage_agent.core.agent import BaseAgent
from fanpage_agent.core.harness import AgentHarness
from fanpage_agent.core.types import ActionPriority, AgentResult, AgentRole, AgentTask


class AgentBus:
    """Central hub for agent communication.

    Usage::
        bus = AgentBus()
        bus.register(strategist_agent)
        bus.register(writer_agent)
        result = bus.dispatch(AgentTask(...))
    """

    def __init__(self, harness: AgentHarness | None = None) -> None:
        self._agents: dict[AgentRole, BaseAgent] = {}
        self._capability_map: dict[str, AgentRole] = {}  # action -> agent
        self._history: list[dict] = []
        self._harness = harness or AgentHarness()
        # Shared state for self-driving agents (choreography pattern)
        self.shared_state: dict[str, Any] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent on the bus."""
        role = agent.role
        if role in self._agents:
            raise ValueError(f"Agent with role {role.value} already registered")
        self._agents[role] = agent
        for action in agent.capabilities:
            self._capability_map[action] = role

    def get_agent(self, role: AgentRole) -> BaseAgent:
        """Get a registered agent by role."""
        agent = self._agents.get(role)
        if not agent:
            raise KeyError(f"No agent registered for role: {role.value}")
        return agent

    def dispatch(self, task: AgentTask) -> AgentResult:
        """Route a task to the correct agent and return the result."""
        target_role = self._capability_map.get(task.action, task.target)
        if target_role not in self._agents:
            return AgentResult(
                task_id=task.id,
                success=False,
                error=f"No agent registered for role {target_role.value} (action: {task.action})",
            )

        agent = self._agents[target_role]
        result = self._harness.run(agent, task)

        self._history.append(
            {
                "task_id": task.id,
                "action": task.action,
                "agent": target_role.value,
                "success": result.success,
                "elapsed_ms": result.metrics.get("elapsed_ms"),
                "completed_at": result.completed_at,
            }
        )
        return result

    def dispatch_batch(self, tasks: list[AgentTask]) -> list[AgentResult]:
        """Dispatch multiple tasks sorted by priority.

        Returns results in the same order as input tasks.
        """
        # Sort by priority (lower number = higher priority)
        sorted_tasks = sorted(tasks, key=lambda t: t.priority.value)
        return [self.dispatch(t) for t in sorted_tasks]

    def create_task(
        self,
        target: AgentRole,
        action: str,
        params: dict[str, Any] | None = None,
        priority: ActionPriority = ActionPriority.MEDIUM,
        context: dict[str, Any] | None = None,
    ) -> AgentTask:
        """Helper to create a task with auto-generated ID."""
        return AgentTask(
            id=f"task-{uuid.uuid4().hex[:12]}",
            target=target,
            action=action,
            params=params or {},
            priority=priority,
            context=context or {},
        )

    @property
    def registered_roles(self) -> list[str]:
        return [r.value for r in self._agents]

    @property
    def history(self) -> list[dict]:
        """Return dispatch history (for reporting)."""
        return list(self._history)

    def summary(self) -> dict:
        """Return a compact summary of bus state."""
        return {
            "agents": self.registered_roles,
            "dispatches": len(self._history),
            "recent": self._history[-10:] if self._history else [],
            "harness": self._harness.summary(),
        }

    # ── Shared state for choreography ───────────────────────────────

    def update_shared_state(self, agent_role: AgentRole, state_dict: dict) -> None:
        """Store agent state in the shared dict for peer visibility."""
        self.shared_state[agent_role.value] = state_dict

    def get_shared_state(self, agent_role: AgentRole) -> dict:
        """Read another agent's shared state (or empty dict if absent)."""
        return self.shared_state.get(agent_role.value, {})
