"""Scheduler — daemon and one-shot entry points for the standalone agent.

Usage:
    python -m scheduler tick        # one cycle
    python -m scheduler daemon      # infinite loop
"""

from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent import Orchestrator
from fanpage_agent.config import Settings
from config import AgentConfig


def tick(agent_config: AgentConfig | None = None) -> dict:
    """Run one autonomous tick and return the summary."""
    root = Path(__file__).resolve().parent
    settings = Settings.from_env(root_dir=root)
    orchestrator = Orchestrator(settings=settings, agent_config=agent_config)
    return orchestrator.run_tick()


def daemon(agent_config: AgentConfig | None = None) -> None:
    """Run daemon (infinite loop)."""
    root = Path(__file__).resolve().parent
    settings = Settings.from_env(root_dir=root)
    orchestrator = Orchestrator(settings=settings, agent_config=agent_config)

    shutdown = False

    def _signal_handler(signum: int, _frame: Any) -> None:
        nonlocal shutdown
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        shutdown = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    orchestrator.run_daemon()


def load_config(config_path: str | Path | None = None) -> AgentConfig:
    """Load agent config from a JSON file, or return defaults."""
    if config_path is None:
        default = Path.home() / ".hermes" / "fanpage-agent" / "agent_config.json"
        if default.exists():
            config_path = default
        else:
            return AgentConfig()

    path = Path(config_path)
    if not path.exists():
        print(f"Config file not found: {path}, using defaults", file=sys.stderr)
        return AgentConfig()

    raw = json.loads(path.read_text(encoding="utf-8"))
    return AgentConfig(**raw)


# ── CLI entry point ────────────────────────────────────────────


def main() -> None:
    """CLI entry point: ``python -m scheduler <mode>``."""
    args = sys.argv[1:] if len(sys.argv) > 1 else ["tick"]
    mode = args[0].lower()

    config_path = None
    if "--config" in args:
        idx = args.index("--config")
        if idx + 1 < len(args):
            config_path = args[idx + 1]

    cfg = load_config(config_path)

    if mode == "daemon":
        print(f"[{datetime.now(timezone.utc).isoformat()}] Fanpage Agent — daemon mode")
        print(f"  Tick interval: {cfg.tick_interval_seconds}s")
        print(f"  Max actions/tick: {cfg.max_actions_per_tick}")
        print(f"  Deliver Telegram: {cfg.deliver_telegram}")
        daemon(cfg)
    elif mode == "tick":
        print(f"[{datetime.now(timezone.utc).isoformat()}] Fanpage Agent — tick mode")
        result = tick(cfg)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"Unknown mode: {mode}. Use 'tick' or 'daemon'.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
