"""Factory — builds the right LLM client based on settings."""

from __future__ import annotations

from fanpage_agent.adapters.llm.mock import MockLLMClient
from fanpage_agent.adapters.llm.openai import OpenAICompatibleClient


def build_llm_client(settings):
    """Build an LLM client based on provider config."""
    if settings.llm_provider == "mock-local":
        return MockLLMClient()
    if settings.llm_provider == "openai-compatible":
        return OpenAICompatibleClient(settings)
    raise ValueError(f"Unsupported provider: {settings.llm_provider}")
