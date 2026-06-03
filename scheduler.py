"""Scheduler — daemon loop for autonomous tick execution.

Designed to run inside a Docker container (fanpage-agent-daemon).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent import AgentConfig, Orchestrator
from config import Settings


# ── Compatibility wrappers for fanpage_cli ─────────────────────


def load_config(path: str) -> AgentConfig:
    """Load AgentConfig from a JSON file."""
    import json

    with open(path) as f:
        data = json.load(f)
    return AgentConfig(**data)


def daemon(agent_config: AgentConfig | None = None) -> None:
    """Legacy wrapper for run_daemon."""
    interval = agent_config.tick_interval_seconds if agent_config else 7200
    run_daemon(agent_config=agent_config, tick_interval=interval)


# ── Core API ───────────────────────────────────────────────────


def tick(agent_config: AgentConfig | None = None) -> dict:
    """Run one autonomous tick and return the summary."""
    root = Path(__file__).resolve().parent
    settings = Settings.from_env(root_dir=root)
    orchestrator = Orchestrator(settings=settings, agent_config=agent_config)
    return orchestrator.run_tick()


def run_daemon(
    agent_config: AgentConfig | None = None,
    tick_interval: int = 7200,
) -> None:
    """Run daemon loop: tick → sleep → repeat.

    Args:
        agent_config: Optional AgentConfig override.
        tick_interval: Seconds between ticks (default 7200 = 2h).
    """
    root = Path(__file__).resolve().parent
    settings = Settings.from_env(root_dir=root)
    orchestrator = Orchestrator(settings=settings, agent_config=agent_config)

    tick = 0
    retry_delay = 60  # shorter retry after failed tick

    while True:
        tick += 1
        now = datetime.now(timezone.utc)

        print(f"\n{'=' * 60}")
        print(f"  Tick #{tick}  |  {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"{'=' * 60}")

        try:
            result = orchestrator.run_tick(tick_num=tick)
            actions = len(
                [h for h in result.get("history", []) if h.get("type") == "tool_call"]
            )
            errors = result.get("errors", [])
            print(f"  Actions: {actions}  |  Errors: {len(errors)}")
            if errors:
                for e in errors[:3]:
                    print(f"  ⚠ {e}")
            # Reset retry on success
            retry_delay = 60
            sleep_time = tick_interval
        except Exception as exc:
            print(f"  ❌ Tick failed: {exc}")
            sleep_time = retry_delay
            # Exponential backoff: 60s → 120s → 240s → max 900s (15 min)
            retry_delay = min(retry_delay * 2, 900)

        print(f"  Sleeping {sleep_time}s...")
        time.sleep(sleep_time)


def main() -> None:
    """Entry point for the daemon."""
    import sys

    interval = 7200
    if len(sys.argv) > 1:
        try:
            interval = int(sys.argv[1])
        except ValueError:
            print(f"Usage: {sys.argv[0]} [interval_seconds]")
            sys.exit(1)

    run_daemon(tick_interval=interval)


if __name__ == "__main__":
    main()
