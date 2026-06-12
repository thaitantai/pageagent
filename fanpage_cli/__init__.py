"""Fanpage CLI — the `fanpage-agent` console script.

One parser tree, one dispatch table: build_parser() reuses the canonical
subcommand declarations from fanpage_agent.cli_commands.parser and grafts
the HANDLERS mapping from fanpage_agent.cli_commands.main onto every
subparser, so this entry point and `python -m fanpage_agent.main` can never
drift apart. Commands exclusive to the console script (init-sheets) are
registered on top.
"""

from __future__ import annotations

import argparse


def main() -> int:
    from fanpage_agent.utils import ensure_utf8_stdio

    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args()
    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


def build_parser() -> argparse.ArgumentParser:
    from fanpage_agent.cli_commands.main import HANDLERS
    from fanpage_agent.cli_commands.parser import build_parser as _build_canonical_parser

    parser = _build_canonical_parser()
    parser.prog = "fanpage-agent"
    subparsers = next(
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    for name, subparser in subparsers.choices.items():
        handler = HANDLERS.get(name)
        if handler is not None:
            subparser.set_defaults(_handler=handler)

    from fanpage_cli import sheets

    sheets.register_subcommand(subparsers)
    return parser
