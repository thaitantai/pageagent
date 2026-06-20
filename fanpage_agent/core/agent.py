"""BaseAgent — abstract base for all Agents.

Each agent runs in its own context and communicates via the AgentBus.
The orchestrator dispatches AgentTask objects to agents and collects AgentResult.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from fanpage_agent.core.types import ActionPriority, AgentResult, AgentRole, AgentTask

if TYPE_CHECKING:
    from fanpage_agent.core.bus import AgentBus


class BaseAgent(ABC):
    """Base class for all specialized agents in.

    Subclasses implement:
    - role: AgentRole enum
    - capabilities: list of action names this agent can handle
    - handle_task(): process a specific AgentTask
    - self_driving_tick(): propose actions proactively (choreography)

    All agents share:
    - AgentConfig for settings
    - LLM client for generation
    - Logging
    - AgentBus reference for shared_state (choreography)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._task_count = 0
        # Self-driving: track when each action was last completed
        self._last_action_at: dict[str, float] = {}
        # Bus reference — set by orchestrator.register_agent()
        self._bus: AgentBus | None = None

    @property
    @abstractmethod
    def role(self) -> AgentRole:
        """Agent's identity — used for routing."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """List of action strings this agent can handle."""
        ...

    def set_bus(self, bus: AgentBus) -> None:
        """Set the AgentBus reference for shared_state access."""
        self._bus = bus

    # ── Shared-state helpers (choreography pattern) ──────────────

    @property
    def _shared_state(self) -> dict[str, Any]:
        """Access the bus's shared state dict."""
        if self._bus is None:
            return {}
        return self._bus.shared_state

    def _update_shared(self, key: str, value: Any) -> None:
        """Update a key in the shared state dict."""
        if self._bus is not None:
            self._shared_state[key] = value

    def _get_shared(self, key: str, default: Any = None) -> Any:
        """Get a key from shared state with fallback."""
        return self._shared_state.get(key, default)

    def _pipeline_version(self, role_key: str, version_key: str = "version") -> int:
        """Read the current pipeline version for an upstream agent role.

        Example: self._pipeline_version("researcher") → 3
        """
        role_state = self._shared_state.get(role_key, {})
        return role_state.get(version_key, 0)

    def _has_upstream_data(self, target_role_key: str, processed_key: str) -> bool:
        """Check if upstream agent has produced new data since we last processed it.

        Example: self._has_upstream_data("researcher", "processed_research_version")
        returns True if researcher.version > strategist.processed_research_version
        """
        upstream_version = self._pipeline_version(target_role_key)
        my_state = self._shared_state.get(self.role.value, {})
        processed = my_state.get(processed_key, 0)
        return upstream_version > processed

    def can_handle(self, action: str) -> bool:
        return action in self.capabilities

    def process(self, task: AgentTask) -> AgentResult:
        """Public entry point — validates then delegates to handle_task()."""
        self._task_count += 1
        if not self.can_handle(task.action):
            return AgentResult(
                task_id=task.id,
                success=False,
                error=f"Agent {self.role.value} cannot handle action '{task.action}'",
            )
        start = time.time()
        try:
            result = self.handle_task(task)
            elapsed = time.time() - start
            result.metrics["elapsed_ms"] = int(elapsed * 1000)
            result.metrics["agent_role"] = self.role.value
            # Track last completion time for self-driving
            self._last_action_at[task.action] = time.time()
            return result
        except Exception as exc:
            elapsed = time.time() - start
            return AgentResult(
                task_id=task.id,
                success=False,
                error=str(exc),
                metrics={"elapsed_ms": int(elapsed * 1000), "agent_role": self.role.value},
            )

    @abstractmethod
    def handle_task(self, task: AgentTask) -> AgentResult:
        """Process a task and return results."""
        ...

    def self_driving_tick(self) -> list[tuple[str, dict, ActionPriority]]:
        """Return proposed actions the agent wants to take this tick.

        Called by the orchestrator during Phase 1 of _tick().
        Each proposal is (action_name, params, priority).

        Default returns empty list (passive agent).
        Override in subclasses for proactive behaviour.
        """
        return []

    # ── Helper for subclasses ────────────────────────────────────

    def _time_since_action(self, action: str) -> float:
        """Seconds since last completion of *action*, or infinity if never done."""
        last = self._last_action_at.get(action)
        return time.time() - last if last is not None else float("inf")

    def _should_act(self, action: str, min_interval: float = 3600) -> bool:
        """Return True if *action* hasn't been done in *min_interval* seconds."""
        return self._time_since_action(action) >= min_interval

    def _should_pipeline_act(
        self, action: str, min_interval: float = 7200, default_min_interval: float = 7200
    ) -> bool:
        """Return True if pipeline trigger is set OR periodic timer says so.

        Pipeline trigger comes from the orchestrator when content is needed
        (calendar gaps, fresh start, periodic refresh).

        Falls back to periodic _should_act() if no trigger is active.
        """
        trigger = self._get_shared("pipeline_trigger", False)
        if trigger:
            return True
        return self._should_act(action, default_min_interval)

    def _mark_shared_done(self, **updates: Any) -> None:
        """Write agent's pipeline output to shared_state.

        Increments my own version so downstream agents know there's new data.

        Args:
            **updates: Additional fields to merge (e.g. brief, schedule, package)
        """
        current_state = self._get_shared(self.role.value, {})
        new_version = current_state.get("version", 0) + 1
        self._update_shared(
            self.role.value,
            {
                "version": new_version,
                "completed_at": time.time(),
                **updates,
            },
        )
