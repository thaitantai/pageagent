"""Backward-compatibility shim — delegates to fanpage_agent.cli_commands.

This file exists so existing imports continue to work:
    from fanpage_agent.legacy_cli import main, build_ops_status_payload, ...

All real code now lives in the cli_commands/ package.
"""
from fanpage_agent.cli_commands import *  # noqa: F401, F403
