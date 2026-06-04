"""V2 LLM adapter — wraps V1 OpenAICompatibleClient for V2 agents.

Provides V2-friendly methods that V2 agents can call to generate
real content (strategies, captions, replies) using the configured
LLM provider ($9router / DeepSeek / etc).
"""
from __future__ import annotations

from typing import Any

from fanpage_agent.adapters.llm_client import (
    OpenAICompatibleClient as _RealLLMClient,
)
from fanpage_agent_v2.adapters.settings import get_settings


class LLMAdapter:
    """Thin wrapper around V1 OpenAICompatibleClient for V2 agents.

    Provides two styles:
    1. ``generate_json()`` — for structured outputs
    2. ``complete()`` — for raw text generation
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = _RealLLMClient(settings)

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Send a prompt and parse the response as JSON.

        Returns the parsed dict. Raises RuntimeError on failure.
        """
        prompt = user_prompt + "\n\nRespond ONLY with a valid JSON object."
        raw = self._client.complete(
            prompt,
            system_prompt=system_prompt + "\nAlways respond with valid JSON.",
            max_tokens=max_tokens,
        )
        import json
        import re
        # Extract JSON from fenced block or bare response
        text = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        return json.loads(text)

    def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 2000,
    ) -> str:
        """Send a prompt and return raw text response."""
        return self._client.complete(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
