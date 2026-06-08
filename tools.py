"""Tool registry — wraps existing pipeline logic as callable tools.

Each tool has:
- A JSON schema (OpenAI tools format) so the LLM can call it
- A Python callable that the orchestrator can dispatch to

Tools are split by domain in tools_defs/ and assembled here.
"""

from __future__ import annotations

from typing import Any

# ── per-domain tool definitions ─────────────────────────────────
from fanpage_agent.tools_defs.approval import REGISTRY_BUILDERS as APPROVAL_BUILDERS
from fanpage_agent.tools_defs.approval import TOOL_DEFINITIONS as APPROVAL_DEFS
from fanpage_agent.tools_defs.content import REGISTRY_BUILDERS as CONTENT_BUILDERS
from fanpage_agent.tools_defs.content import TOOL_DEFINITIONS as CONTENT_DEFS
from fanpage_agent.tools_defs.data import REGISTRY_BUILDERS as DATA_BUILDERS
from fanpage_agent.tools_defs.data import TOOL_DEFINITIONS as DATA_DEFS
from fanpage_agent.tools_defs.ops import REGISTRY_BUILDERS as OPS_BUILDERS
from fanpage_agent.tools_defs.ops import TOOL_DEFINITIONS as OPS_DEFS
from fanpage_agent.tools_defs.telegram import REGISTRY_BUILDERS as TG_BUILDERS
from fanpage_agent.tools_defs.telegram import TOOL_DEFINITIONS as TG_DEFS

# ── assemble ────────────────────────────────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    *OPS_DEFS,
    *APPROVAL_DEFS,
    *CONTENT_DEFS,
    *DATA_DEFS,
    *TG_DEFS,
]

REGISTRY_BUILDERS: dict[str, tuple] = {
    **OPS_BUILDERS,
    **APPROVAL_BUILDERS,
    **CONTENT_BUILDERS,
    **DATA_BUILDERS,
    **TG_BUILDERS,
}

TOOL_REGISTRY: dict[str, Any] = {}
for name, (fn, _) in REGISTRY_BUILDERS.items():
    TOOL_REGISTRY[name] = fn


# ── public API ──────────────────────────────────────────────────


def get_tool_definitions() -> list[dict]:
    """Return the full tool definitions list (OpenAI tools format)."""
    return TOOL_DEFINITIONS


def dispatch_tool(name: str, args: dict | None = None) -> dict:
    """Look up and call a tool by name."""
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {name}"}
    resolved_args = args or {}
    fn = TOOL_REGISTRY[name]
    try:
        result = fn(**resolved_args)
    except TypeError:
        result = fn()
    if not isinstance(result, dict):
        return {"result": str(result)}
    return result


def tool_ops_status(args: dict | None = None) -> dict:
    """Shorthand — call ops_status tool directly."""
    return dispatch_tool("ops_status", args)
