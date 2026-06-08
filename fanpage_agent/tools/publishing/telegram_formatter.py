"""Backward-compatible re-export of TelegramFormatterTool.

The implementation has been split into the formatters/ package for maintainability.
This module re-exports the assembled class so existing imports continue to work.
"""

from fanpage_agent.tools.publishing.formatters import TelegramFormatterTool  # noqa: F401
