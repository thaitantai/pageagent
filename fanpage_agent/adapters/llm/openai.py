"""OpenAI-compatible LLM client — wraps REST API for structured and chat completions."""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from fanpage_agent.config import Settings
from fanpage_agent.models import (
    BrandProfile,
    CaptionPackage,
    ResearchBrief,
    WeeklyPlan,
)
from fanpage_agent.prompts._loader import PromptLoader


class OpenAICompatibleClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is required for openai-compatible provider")
        if not settings.llm_base_url:
            raise RuntimeError("LLM_BASE_URL is required for openai-compatible provider")
        self.endpoint = settings.llm_base_url.rstrip("/") + "/chat/completions"
        self._preferred_model = settings.llm_model
        self._models = self._build_model_list()

    def generate_weekly_plan(
        self,
        profile: BrandProfile,
        start_date: str,
        days: int = 7,
        research_brief: ResearchBrief | None = None,
    ) -> WeeklyPlan:
        payload = self._complete_json(
            system_prompt=self._weekly_plan_system_prompt(),
            user_prompt=self._weekly_plan_user_prompt(profile, start_date, days, research_brief),
            response_model=WeeklyPlan,
        )
        return WeeklyPlan.model_validate(payload)

    def generate_caption_package(
        self,
        profile: BrandProfile,
        topic: str,
        pillar: str,
        objective: str,
        fmt: str,
    ) -> CaptionPackage:
        payload = self._complete_json(
            system_prompt=self._caption_system_prompt(),
            user_prompt=self._caption_user_prompt(profile, topic, pillar, objective, fmt),
            response_model=CaptionPackage,
        )
        return CaptionPackage.model_validate(payload)

    def complete(self, prompt: str, *, system_prompt: str = "", max_tokens: int = 2000) -> str:
        """Generic completion — sends a user prompt, returns raw text.

        Useful for one-off LLM calls (hashtags, summaries, etc.) that
        don't need a structured response model.
        """
        final_system = system_prompt or "You are a helpful assistant. Respond in plain text."
        for model in self._model_attempt_order():
            try:
                return self._chat_completion(
                    system_prompt=final_system,
                    user_prompt=prompt,
                    model=model,
                )
            except RuntimeError as exc:
                if self._should_try_next_model(str(exc)):
                    continue
                raise
        raise RuntimeError("All models exhausted for generic completion")

    def _complete_json(self, system_prompt: str, user_prompt: str, response_model: type[WeeklyPlan | CaptionPackage]) -> dict:
        errors: list[str] = []
        for model in self._model_attempt_order():
            for _ in range(2):
                try:
                    raw_content = self._chat_completion(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        model=model,
                        response_format={"type": "json_object"},
                    )
                except RuntimeError as exc:
                    errors.append(f"{model}: {exc}")
                    if self._should_try_next_model(str(exc)):
                        break
                    raise

                try:
                    payload = self._extract_json(raw_content)
                    payload = self._normalize_payload(payload, response_model)
                    response_model.model_validate(payload)
                    self._preferred_model = model
                    return payload
                except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                    errors.append(f"{model}: {type(exc).__name__}: {exc}")
        raise RuntimeError(
            f"Failed to parse {response_model.__name__} from LLM response after 2 attempts. "
            f"Errors: {' | '.join(errors)}"
        )

    def _chat_completion(self, system_prompt: str, user_prompt: str, model: str, *, response_format: dict | None = None) -> str:
        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": self.settings.llm_max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format is not None:
            payload["response_format"] = response_format
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.llm_api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            raise RuntimeError(f"LLM HTTP error {exc.code}: {detail[:500]}") from exc
        except URLError as exc:
            raise RuntimeError(f"LLM connection error: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            sse_content = self._extract_sse_content(body)
            if sse_content:
                return sse_content
            json_stream_content = self._extract_json_stream_content(body)
            if json_stream_content:
                return json_stream_content
            raise RuntimeError(f"LLM returned non-JSON HTTP body: {body[:500]}") from exc

        choices = parsed.get("choices") or []
        if not choices:
            raise RuntimeError(f"LLM response missing choices: {body[:500]}")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
            joined = "\n".join(part for part in text_parts if part)
            if joined:
                return joined
        raise RuntimeError(f"LLM response missing message content: {body[:500]}")

    @staticmethod
    def _extract_sse_content(body: str) -> str:
        parts: list[str] = []
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if not data or data == "[DONE]":
                continue
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            for choice in chunk.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta") or {}
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if isinstance(content, str):
                        parts.append(content)
                message = choice.get("message") or {}
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        parts.append(content)
        return "".join(parts)

    @classmethod
    def _extract_json_stream_content(cls, body: str) -> str:
        parts: list[str] = []
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            parts.append(cls._extract_choice_content(chunk))
        return "".join(part for part in parts if part)

    @staticmethod
    def _extract_choice_content(parsed: dict) -> str:
        parts: list[str] = []
        for choice in parsed.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message") or {}
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    parts.extend(part.get("text", "") for part in content if isinstance(part, dict))
            delta = choice.get("delta") or {}
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    parts.append(content)
        return "".join(part for part in parts if part)

    def _build_model_list(self) -> list[str]:
        ordered: list[str] = []
        for model in [self.settings.llm_model, *self.settings.llm_model_candidates]:
            if model and model not in ordered:
                ordered.append(model)
        return ordered or [self.settings.llm_model]

    def _model_attempt_order(self) -> list[str]:
        if self._preferred_model not in self._models:
            return list(self._models)
        return [self._preferred_model, *[model for model in self._models if model != self._preferred_model]]

    @staticmethod
    def _should_try_next_model(error_text: str) -> bool:
        lowered = error_text.lower()
        retryable_fragments = [
            "llm http error 400",
            "llm http error 402",
            "llm http error 404",
            "llm http error 429",
            "llm http error 503",
            "no endpoints found",
            "does not have any endpoints",
            "insufficient credits",
            "model not found",
        ]
        return any(fragment in lowered for fragment in retryable_fragments)

    @staticmethod
    def _extract_json(raw_content: str) -> dict:
        text = raw_content.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON object found in model response")
        return json.loads(text[start : end + 1])

    @staticmethod
    def _ensure_list(value) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [str(value)]

    @classmethod
    def _normalize_payload(cls, payload: dict, response_model: type[WeeklyPlan | CaptionPackage]) -> dict:
        if response_model is WeeklyPlan:
            normalized = dict(payload)
            normalized["strategy_notes"] = cls._ensure_list(normalized.get("strategy_notes"))
            normalized["gaps_or_assumptions"] = cls._ensure_list(normalized.get("gaps_or_assumptions"))
            raw_days = normalized.get("days")
            if isinstance(raw_days, list):
                days = []
                for item in raw_days:
                    if isinstance(item, dict):
                        day = dict(item)
                        day["risk_notes"] = cls._ensure_list(day.get("risk_notes"))
                        days.append(day)
                    else:
                        days.append(item)
                normalized["days"] = days
            return normalized
        if response_model is CaptionPackage:
            normalized = dict(payload)
            normalized["dos"] = cls._ensure_list(normalized.get("dos"))
            normalized["donts"] = cls._ensure_list(normalized.get("donts"))
            raw_variants = normalized.get("variants")
            if isinstance(raw_variants, list):
                variants = []
                for item in raw_variants:
                    if isinstance(item, dict):
                        variant = dict(item)
                        variant["tone_tags"] = cls._ensure_list(variant.get("tone_tags"))
                        variants.append(variant)
                    else:
                        variants.append(item)
                normalized["variants"] = variants
            return normalized
        return payload

    @staticmethod
    def _weekly_plan_system_prompt() -> str:
        return PromptLoader.load("planner_system.md")

    @staticmethod
    def _caption_system_prompt() -> str:
        return PromptLoader.load("caption_system.md")

    @staticmethod
    def _compact_profile_payload(profile: BrandProfile) -> dict:
        return {
            "brand_id": profile.brand_id,
            "brand_name": profile.brand_name,
            "business_goal": profile.business_goal,
            "fanpage_goals": profile.fanpage_goals[:2],
            "brand_summary": profile.brand_summary,
            "target_audiences": [
                {
                    "segment_name": item.segment_name,
                    "pain_points": item.pain_points[:2],
                    "desired_outcomes": item.desired_outcomes[:2],
                }
                for item in profile.target_audiences[:1]
            ],
            "content_pillars": [
                {
                    "pillar_name": item.pillar_name,
                    "description": item.description,
                    "example_angles": item.example_angles[:1],
                }
                for item in profile.content_pillars[:3]
            ],
            "tone_of_voice": {
                "brand_traits": profile.tone_of_voice.brand_traits,
                "writing_rules": profile.tone_of_voice.writing_rules,
                "things_to_avoid": profile.tone_of_voice.things_to_avoid,
                "sample_phrases": profile.tone_of_voice.sample_phrases[:3],
            },
            "approved_cta_patterns": [
                {"objective": item.objective, "cta_text": item.cta_text}
                for item in profile.approved_cta_patterns[:2]
            ],
            "banned_phrases": profile.banned_phrases[:4],
            "compliance_notes": profile.compliance_notes[:2],
        }

    @staticmethod
    def _compact_research_payload(research_brief: ResearchBrief | None) -> dict | None:
        if not research_brief:
            return None
        result: dict = {
            "recommended_objectives": research_brief.recommended_objectives[:3],
            "recommended_pillars": research_brief.recommended_pillars[:4],
            "next_angles": research_brief.next_angles[:5],
            "frequent_questions": research_brief.frequent_questions[:5],
            "campaign_focus": research_brief.campaign_focus[:4],
            "overused_topics": research_brief.overused_topics[:4],
            "recommendations": research_brief.recommendations[:4],
        }
        # Enrich with trend data if available
        if research_brief.trend_keywords:
            result["trend_keywords"] = research_brief.trend_keywords[:15]
        if research_brief.trend_clusters:
            result["trend_clusters"] = dict(
                list(research_brief.trend_clusters.items())[:5]
            )
        return result

    @staticmethod
    def _weekly_plan_user_prompt(
        profile: BrandProfile,
        start_date: str,
        days: int,
        research_brief: ResearchBrief | None,
    ) -> str:
        return PromptLoader.format(
            "planner_user_weekly_plan.md",
            start_date=start_date,
            days=days,
            brand_context=json.dumps(
                OpenAICompatibleClient._compact_profile_payload(profile),
                ensure_ascii=False,
            ),
            research_brief=json.dumps(
                OpenAICompatibleClient._compact_research_payload(research_brief),
                ensure_ascii=False,
            ),
            brand_id=profile.brand_id,
        )

    @staticmethod
    def _caption_user_prompt(
        profile: BrandProfile,
        topic: str,
        pillar: str,
        objective: str,
        fmt: str,
    ) -> str:
        compact_profile = OpenAICompatibleClient._compact_profile_payload(profile)
        compact_profile["content_pillars"] = [
            item for item in compact_profile["content_pillars"] if item["pillar_name"] == pillar
        ] or compact_profile["content_pillars"][:1]
        compact_profile["approved_cta_patterns"] = [
            item for item in compact_profile["approved_cta_patterns"] if item["objective"] == objective
        ] or compact_profile["approved_cta_patterns"][:2]
        return PromptLoader.format(
            "caption_user.md",
            topic=topic,
            pillar=pillar,
            objective=objective,
            fmt=fmt,
            brand_context=json.dumps(compact_profile, ensure_ascii=False),
        )


    # ── tools / function calling ─────────────────────────────────

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict:
        """Send messages with optional tools array.

        Returns the full message dict from the LLM response.
        If the LLM wants to call tools, the dict includes
        ``tool_calls`` — a list of ``{id, type, function: {name, arguments}}``.
        If the LLM responds with text, ``tool_calls`` is absent.

        Uses model fallback like the rest of this client.
        """
        errors: list[str] = []
        for model in self._model_attempt_order():
            try:
                return self._tool_completion(
                    messages=messages,
                    tools=tools,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except RuntimeError as exc:
                err = f"{model}: {exc}"
                errors.append(err)
                if self._should_try_next_model(str(exc)):
                    continue
                raise
        raise RuntimeError(
            f"All models exhausted for chat_with_tools. "
            f"Errors: {' | '.join(errors[:3])}"
        )

    def _tool_completion(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        model: str,
        temperature: float,
        max_tokens: int | None,
    ) -> dict:
        """Raw HTTP call that returns the full message dict (with tool_calls)."""
        payload: dict = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens or self.settings.llm_max_tokens,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.llm_api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            raise RuntimeError(f"LLM HTTP error {exc.code}: {detail[:500]}") from exc
        except URLError as exc:
            raise RuntimeError(f"LLM connection error: {exc}") from exc

        parsed: dict = json.loads(body)
        choices = parsed.get("choices") or []
        if not choices:
            raise RuntimeError(f"LLM response missing choices: {body[:500]}")

        message: dict = choices[0].get("message") or {}

        # Normalise text content
        content = message.get("content")
        if isinstance(content, list):
            text_parts = [
                part.get("text", "") for part in content if isinstance(part, dict)
            ]
            message["content"] = "\n".join(p for p in text_parts if p)

        # Parse tool_calls
        raw_tool_calls = message.get("tool_calls") or []
        if raw_tool_calls:
            parsed_calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    args = {"raw": fn.get("arguments", "")}
                parsed_calls.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": fn.get("name", ""),
                        "arguments": args,
                    },
                })
            message["tool_calls"] = parsed_calls

        return message


