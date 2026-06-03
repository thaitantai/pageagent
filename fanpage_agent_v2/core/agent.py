"""BaseAgent — abstract base for all V2 agents.

Each agent runs in its own context and communicates via the AgentBus.
The orchestrator dispatches AgentTask objects to agents and collects AgentResult.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from fanpage_agent_v2.core.types import AgentRole, AgentTask, AgentResult


class BaseAgent(ABC):
    """Base class for all specialized agents in V2.

    Subclasses implement:
    - role: AgentRole enum
    - capabilities: list of action names this agent can handle
    - handle_task(): process a specific AgentTask

    All agents share:
    - AgentConfig for settings
    - LLM client for generation
    - Logging
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._task_count = 0

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
