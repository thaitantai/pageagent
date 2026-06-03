"""CLI entry point — fanpage-agent command.

Dispatches to fanpage_cli subcommand modules.
"""

from __future__ import annotations

import sys

from fanpage_cli import main as cli_main


if __name__ == "__main__":
    raise SystemExit(cli_main())
