"""Subcommands that exist only on the fanpage-agent console script."""

from __future__ import annotations

import argparse
import json

from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.cli_commands.parser import ROOT_DIR, add_store_backend_arg
from fanpage_agent.config import Settings


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "init-sheets", help="Create all standard tabs + headers in the Google Sheet"
    )
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_init_sheets)


def cmd_init_sheets(args: argparse.Namespace) -> int:
    """Create all standard tabs + headers in the configured Google Sheet."""
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    if not hasattr(store, "initialize_standard_tabs"):
        print("init-sheets only works with --store-backend google")
        return 1
    status = store.initialize_standard_tabs()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print(f"\n✅ {len(status)} tabs ready.")
    return 0
