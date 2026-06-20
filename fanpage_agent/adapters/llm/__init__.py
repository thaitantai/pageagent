"""LLM client package — mock and OpenAI-compatible implementations."""

from fanpage_agent.adapters.llm.factory import build_llm_client
from fanpage_agent.adapters.llm.mock import MockLLMClient
from fanpage_agent.adapters.llm.openai import OpenAICompatibleClient

__all__ = [
    "MockLLMClient",
    "OpenAICompatibleClient",
    "build_llm_client",
]
