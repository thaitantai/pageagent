"""Compatibility package for the merged V2 code.

The V2 implementation now lives under ``fanpage_agent.v2``.  This package keeps
old imports such as ``fanpage_agent_v2.core.bus`` working while callers migrate.
"""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent / "fanpage_agent" / "v2")]
