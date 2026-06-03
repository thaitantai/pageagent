from __future__ import annotations

import argparse
import json

from config import AgentConfig
from scheduler import load_config, tick, daemon


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    tick_parser = subparsers.add_parser("agent-tick", help="Run one autonomous agent cycle")
    tick_parser.add_argument("--config", help="Path to agent config JSON")
    tick_parser.add_argument("--max-actions", type=int, default=5, help="Max actions per tick")
    tick_parser.set_defaults(_handler=cmd_agent_tick)

    daemon_parser = subparsers.add_parser("agent-daemon", help="Run agent in daemon mode (infinite loop)")
    daemon_parser.add_argument("--config", help="Path to agent config JSON")
    daemon_parser.add_argument("--interval", type=int, default=7200, help="Tick interval in seconds")
    daemon_parser.set_defaults(_handler=cmd_agent_daemon)


def cmd_agent_tick(args: argparse.Namespace) -> int:
    cfg = AgentConfig(max_actions_per_tick=args.max_actions)
    if args.config:
        cfg = load_config(args.config)
    result = tick(cfg)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_agent_daemon(args: argparse.Namespace) -> int:
    cfg = AgentConfig(tick_interval_seconds=args.interval)
    if args.config:
        cfg = load_config(args.config)
    daemon(cfg)
    return 0
