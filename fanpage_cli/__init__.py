"""Fanpage CLI — subcommand dispatch.

Each subcommand group is a module in this package.
Modules register with register_subcommand(subparsers) and expose handle(args).
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    # Each subcommand module stores a _HANDLER in the registered parser
    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fanpage-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    from fanpage_cli import (
        agent as agent_module,
        approval as approval_module,
        content as content_module,
        deliver as deliver_module,
        ops as ops_module,
        plan as plan_module,
        triage as triage_module,
    )

    plan_module.register_subcommand(subparsers)
    approval_module.register_subcommand(subparsers)
    agent_module.register_subcommand(subparsers)
    content_module.register_subcommand(subparsers)
    deliver_module.register_subcommand(subparsers)
    ops_module.register_subcommand(subparsers)
    triage_module.register_subcommand(subparsers)

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
