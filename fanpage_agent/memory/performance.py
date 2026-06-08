"""Backward-compat shim — re-exports from the memory package.

Prefer: from fanpage_agent.memory import PerformanceMemory
"""

from fanpage_agent.memory import BackupError, IntegrityError, PerformanceMemory  # noqa: F401

__all__ = ["PerformanceMemory", "BackupError", "IntegrityError"]
