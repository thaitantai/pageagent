"""
Backward-compatible re-exports.

Prefer importing from ``fanpage_agent.adapters.llm`` for new code:
    from fanpage_agent.adapters.llm import MockLLMClient, build_llm_client
"""

from fanpage_agent.adapters.llm import (  # noqa: F401
    MockLLMClient,
    OpenAICompatibleClient,
    build_llm_client,
)
