"""Adapters — external integrations (LLM, Facebook, Sheets, Telegram, store)."""

from fanpage_agent.adapters.llm import (
    MockLLMClient,
    OpenAICompatibleClient,
    build_llm_client,
)
