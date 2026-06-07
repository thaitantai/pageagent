"""PromptLoader — lazy-load prompt templates from prompts/ directory."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent

class PromptLoader:
    """Load and cache prompt templates from .md files.
    
    Usage:
        >>> system = PromptLoader.load("planner_system.md")
        >>> prompt = PromptLoader.format("writer_user_variants.md", count=3, topic="Retinol", ...)
    """
    _cache: dict[str, str] = {}

    @classmethod
    def load(cls, name: str) -> str:
        """Load a prompt template from prompts/<name>, cached."""
        if name not in cls._cache:
            path = _PROMPTS_DIR / name
            cls._cache[name] = path.read_text(encoding="utf-8")
        return cls._cache[name]

    @classmethod
    def format(cls, name: str, **kwargs: object) -> str:
        """Load a prompt template and substitute {var} placeholders."""
        template = cls.load(name)
        return template.format(**kwargs)

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()
