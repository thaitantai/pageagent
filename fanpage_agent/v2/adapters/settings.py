"""Reuse V1 Settings from the root config.

Usage::

    from fanpage_agent.v2.adapters.settings import get_settings
    settings = get_settings()
    fb = FacebookAdapter(settings)
"""
from __future__ import annotations

from pathlib import Path

from config import Settings as _Settings

_settings_cache: _Settings | None = None


def get_settings() -> _Settings:
    """Return a cached Settings instance (loads .env once)."""
    global _settings_cache
    if _settings_cache is None:
        # Auto-discover .env from cwd / parents so CLI works too
        _settings_cache = _Settings.from_env(
            load_dotenv=True,
        )
    return _settings_cache
