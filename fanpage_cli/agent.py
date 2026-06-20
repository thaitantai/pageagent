"""Agent subcommands — tick and daemon using multi-agent orchestrator."""

from __future__ import annotations

import argparse
import json
import sys
import time

from fanpage_agent.core.types import ActionPriority, AgentRole, AgentTask
from fanpage_agent.main import create_pipeline


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    tick_parser = subparsers.add_parser("agent-tick", help="Run one autonomous agent cycle")
    tick_parser.add_argument("--config", help="Path to agent config JSON (unused in)")
    tick_parser.add_argument("--data-dir", default="data/agent", help="agent data directory")
    tick_parser.set_defaults(_handler=cmd_agent_tick)

    daemon_parser = subparsers.add_parser(
        "agent-daemon", help="Run Agent in daemon mode (infinite loop)"
    )
    daemon_parser.add_argument("--config", help="Path to agent config JSON (unused in)")
    daemon_parser.add_argument(
        "--interval", type=int, default=7200, help="Tick interval in seconds"
    )
    daemon_parser.add_argument("--data-dir", default="data/agent", help="agent data directory")
    daemon_parser.set_defaults(_handler=cmd_agent_daemon)


def cmd_agent_tick(args: argparse.Namespace) -> int:
    """Run a single tick."""
    orchestrator = create_pipeline(data_dir=args.data_dir)
    result = orchestrator.process(
        AgentTask(
            id="cli-tick",
            target=AgentRole.ORCHESTRATOR,
            action="tick",
            priority=ActionPriority.HIGH,
        )
    )
    output = result.data if result.success else {"error": result.error, "success": False}
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0 if result.success else 1


def cmd_agent_daemon(args: argparse.Namespace) -> int:
    """Run Agent daemon loop — orchestrate multi-agent pipeline every interval."""
    orchestrator = create_pipeline(data_dir=args.data_dir)
    tick_number = 0
    while True:
        tick_number += 1
        result = orchestrator.process(
            AgentTask(
                id=f"daemon-tick-{int(time.time())}",
                target=AgentRole.ORCHESTRATOR,
                action="tick",
                priority=ActionPriority.HIGH,
            )
        )
        elapsed = result.metrics.get("elapsed_ms", 0)
        status = "✅" if result.success else "❌"
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] tick #{tick_number}: {status} ({elapsed}ms)")
        sys.stdout.flush()
        time.sleep(args.interval)
