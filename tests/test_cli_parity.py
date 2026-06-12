"""Parity contract between the two CLI entry points.

`python -m fanpage_agent.main <cmd>` (cron/docker) and `fanpage-agent <cmd>`
(console script) must expose the same subcommands with the same flags.
fanpage_cli builds its tree FROM the canonical parser, so these tests guard
against anyone reintroducing a second, hand-maintained tree.
"""

from __future__ import annotations

import argparse
import unittest

from fanpage_agent.cli_commands.main import HANDLERS
from fanpage_agent.cli_commands.parser import build_parser as build_canonical_parser
from fanpage_cli import build_parser as build_console_parser

# Commands that intentionally exist only on the console script.
CONSOLE_ONLY = {"init-sheets"}


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    return dict(action.choices)


def _option_signature(subparser: argparse.ArgumentParser) -> set[tuple]:
    signature = set()
    for action in subparser._actions:
        if action.dest == "help":
            continue
        signature.add(
            (
                tuple(action.option_strings) or (action.dest,),
                bool(getattr(action, "required", False)),
                type(action).__name__,
            )
        )
    return signature


class CliParityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.canonical = _subparsers(build_canonical_parser())
        self.console = _subparsers(build_console_parser())

    def test_console_script_exposes_every_canonical_command(self) -> None:
        missing = sorted(set(self.canonical) - set(self.console))
        self.assertEqual(missing, [])

    def test_console_only_commands_are_whitelisted(self) -> None:
        extra = sorted(set(self.console) - set(self.canonical))
        self.assertEqual(extra, sorted(CONSOLE_ONLY))

    def test_shared_commands_have_identical_flags(self) -> None:
        for name in self.canonical:
            with self.subTest(command=name):
                self.assertEqual(
                    _option_signature(self.canonical[name]),
                    _option_signature(self.console[name]),
                )

    def test_every_console_command_has_a_handler(self) -> None:
        for name, subparser in self.console.items():
            with self.subTest(command=name):
                self.assertIsNotNone(
                    subparser._defaults.get("_handler"),
                    f"{name} has no _handler",
                )

    def test_handlers_cover_exactly_the_canonical_commands(self) -> None:
        self.assertEqual(sorted(HANDLERS), sorted(self.canonical))


if __name__ == "__main__":
    unittest.main()
