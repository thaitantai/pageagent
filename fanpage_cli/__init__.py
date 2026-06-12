"""Fanpage CLI — subcommand dispatch.

Each subcommand group is a module in this package.
Modules register with register_subcommand(subparsers) and expose handle(args).
"""

from __future__ import annotations

import argparse


def main() -> int:
    from fanpage_agent.utils import ensure_utf8_stdio

    ensure_utf8_stdio()
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
    )
    from fanpage_cli import (
        approval as approval_module,
    )
    from fanpage_cli import (
        content as content_module,
    )
    from fanpage_cli import (
        deliver as deliver_module,
    )
    from fanpage_cli import (
        ops as ops_module,
    )
    from fanpage_cli import (
        plan as plan_module,
    )
    from fanpage_cli import (
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
