from __future__ import annotations

import json
import re
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from fanpage_agent.config import Settings
from fanpage_agent.models import BrandProfile, CaptionPackage, CaptionVariant, PlanDay, ResearchBrief, WeeklyPlan


class MockLLMClient:
    def generate_weekly_plan(
        self,
        profile: BrandProfile,
        start_date: str,
        days: int = 7,
        research_brief: ResearchBrief | None = None,
    ) -> WeeklyPlan:
        start = date.fromisoformat(start_date)
        entries: list[PlanDay] = []
        objectives = self._build_objective_lane(profile, research_brief)
        pillars = self._build_pillar_lane(profile, research_brief)
        angles = self._build_angle_lane(profile, research_brief)
        first_question = research_brief.frequent_questions[0] if research_brief and research_brief.frequent_questions else None

        for index in range(days):
            pillar_name = pillars[index % len(pillars)]
            pillar = self._resolve_pillar(profile, pillar_name)
            objective = objectives[index % len(objectives)]
            angle = angles[index % len(angles)]
            fmt = pillar.allowed_formats[0] if pillar.allowed_formats else "post_short"
            cta = self._pick_cta(profile, objective)
            if index == 0 and first_question:
                topic = first_question
            else:
                topic = f"{pillar.pillar_name.title()} - {angle} cho {profile.target_audiences[0].segment_name}"
            entries.append(
                PlanDay(
                    date=(start + timedelta(days=index)).isoformat(),
                    pillar=pillar.pillar_name,
                    objective=objective,
                    topic=topic,
                    angle=angle,
                    format=fmt,
                    hook=f"{profile.brand_name}: {angle.capitalize()} bạn nên biết",
                    cta=cta,
                    visual_brief=f"Thiết kế tối giản, nhấn mạnh ý '{angle}' với tone {', '.join(profile.tone_of_voice.brand_traits[:2])}",
                    risk_notes=[],
                )
            )

        strategy_notes = [
            f"Ưu tiên mix {len(profile.content_pillars)} pillar để tránh lặp ý.",
            "Giữ CTA nhẹ cho bài reach và rõ hơn cho bài lead.",
        ]
        if research_brief:
            if research_brief.campaign_focus:
                strategy_notes.append(f"Bám campaign focus: {research_brief.campaign_focus[0]}.")
            if research_brief.overused_topics:
                strategy_notes.append(f"Tránh lặp lại topic: {research_brief.overused_topics[0]}.")

        return WeeklyPlan(
            plan_title=f"weekly-plan-{profile.brand_id}-{start_date}",
            days=entries,
            strategy_notes=strategy_notes,
            gaps_or_assumptions=[],
        )

    def generate_caption_package(
        self,
        profile: BrandProfile,
        topic: str,
        pillar: str,
        objective: str,
        fmt: str,
    ) -> CaptionPackage:
        cta = self._pick_cta(profile, objective)
        traits = profile.tone_of_voice.brand_traits
        rules = profile.tone_of_voice.writing_rules
        avoid = profile.tone_of_voice.things_to_avoid
        sample = profile.tone_of_voice.sample_phrases

        # Build dos from writing_rules (positive phrasing) + commonsense defaults
        dos_rules = list(rules) if rules else ["Giữ câu ngắn", "Nhấn lợi ích thực tế", "Dùng CTA đã duyệt"]
        # Build donts from things_to_avoid + commonsense defaults
        donts_rules = list(avoid) if avoid else ["Không claim tuyệt đối", "Không giật gân", "Không dùng banned phrases"]

        # Default tone tags from brand traits
        # All tone tags must come from brand_traits so they pass tone validation
        tone_a = [traits[0], traits[1 % len(traits)]] if traits else ["rõ ràng"]
        tone_b = [traits[1 % len(traits)], traits[2 % len(traits)]] if len(traits) >= 2 else (traits[:1] + ["rõ ràng"])[:2]
        tone_c = [traits[2 % len(traits)], traits[3 % len(traits)]] if len(traits) >= 3 else (traits[:1] + [traits[-1]])[:2]

        # Default sample-based hooks
        hook_a = f"Về {topic}, có một điều ít ai nói đến"
        hook_b = f"{topic} — bạn đã thử cách này chưa?"
        hook_c = f"{topic}: điều quan trọng nhất cần nhớ"

        caption_a = (
            f"{topic}. "
            f"{profile.brand_summary} "
            f"Điều thực sự quan trọng là hiểu rõ bản chất vấn đề, không phải chạy theo số đông."
        )
        caption_b = (
            f"Nhiều người nghĩ {topic} chỉ đơn giản là… nhưng thực tế còn nhiều hơn thế. "
            f"Bạn đã bao giờ dừng lại và tự hỏi: liệu mình đang làm đúng chưa? "
            f"{profile.brand_summary}"
        )
        caption_c = (
            f"Hãy cùng nhìn nhận {topic} một cách thực tế. "
            f"{profile.brand_summary} "
            f"Bài học rút ra: hiểu đúng gốc rễ vấn đề để có quyết định tốt hơn."
        )

        return CaptionPackage(
            topic=topic,
            variants=[
                CaptionVariant(
                    label="A",
                    hook=hook_a,
                    caption=caption_a,
                    cta=cta,
                    tone_tags=tone_a,
                    visual_brief=f"{fmt} với headline ngắn, làm rõ chủ đề {topic}. Tone: {', '.join(tone_a)}.",
                ),
                CaptionVariant(
                    label="B",
                    hook=hook_b,
                    caption=caption_b,
                    cta=cta,
                    tone_tags=tone_b,
                    visual_brief=f"{fmt} so sánh before/after theo hướng giáo dục. Tone: {', '.join(tone_b)}.",
                ),
                CaptionVariant(
                    label="C",
                    hook=hook_c,
                    caption=caption_c,
                    cta=cta,
                    tone_tags=tone_c,
                    visual_brief=f"{fmt} dạng checklist, ưu tiên dễ đọc trên mobile. Tone: {', '.join(tone_c)}.",
                ),
            ],
            dos=dos_rules[:5],
            donts=donts_rules[:5],
        )

    @staticmethod
    def _pick_cta(profile: BrandProfile, objective: str) -> str:
        for item in profile.approved_cta_patterns:
            if item.objective == objective:
                return item.cta_text
        return profile.approved_cta_patterns[0].cta_text if profile.approved_cta_patterns else "Lưu lại khi cần"

    @staticmethod
    def _resolve_pillar(profile: BrandProfile, pillar_name: str):
        for pillar in profile.content_pillars:
            if pillar.pillar_name == pillar_name:
                return pillar
        return profile.content_pillars[0]

    @staticmethod
    def _build_objective_lane(profile: BrandProfile, research_brief: ResearchBrief | None) -> list[str]:
        if research_brief and research_brief.recommended_objectives:
            return research_brief.recommended_objectives
        return profile.fanpage_goals or ["reach"]

    @staticmethod
    def _build_pillar_lane(profile: BrandProfile, research_brief: ResearchBrief | None) -> list[str]:
        if research_brief and research_brief.recommended_pillars:
            return research_brief.recommended_pillars
        return [item.pillar_name for item in profile.content_pillars]

    @staticmethod
    def _build_angle_lane(profile: BrandProfile, research_brief: ResearchBrief | None) -> list[str]:
        if research_brief and research_brief.next_angles:
            return research_brief.next_angles
        angles: list[str] = []
        for pillar in profile.content_pillars:
            if pillar.example_angles:
                angles.extend(pillar.example_angles)
        return angles or [profile.content_pillars[0].description]


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

    def _complete_json(self, system_prompt: str, user_prompt: str, response_model: type[WeeklyPlan | CaptionPackage]) -> dict:
        errors: list[str] = []
        for model in self._model_attempt_order():
            for _ in range(2):
                try:
                    raw_content = self._chat_completion(system_prompt=system_prompt, user_prompt=user_prompt, model=model)
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

    def _chat_completion(self, system_prompt: str, user_prompt: str, model: str) -> str:
        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": self.settings.llm_max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
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
        return (
            "Bạn là planner cho fanpage. TONE OF VOICE LÀ YẾU TỐ QUAN TRỌNG NHẤT — "
            "mọi đề xuất chủ đề, hook, góc tiếp cận phải trung thành với brand_traits và writing_rules của brand. "
            "Chỉ trả về đúng 1 JSON object hợp lệ, không markdown, không giải thích. "
            "Bám brand voice, tránh generic, tránh claim quá mức, và đảm bảo đủ schema WeeklyPlan."
        )

    @staticmethod
    def _caption_system_prompt() -> str:
        return (
            "Bạn là content writer cho fanpage. TONE OF VOICE LÀ YẾU TỐ QUAN TRỌNG NHẤT — "
            "giọng văn quyết định caption. Bám chặt brand_traits, writing_rules, và sample_phrases trong brand_context. "
            "Sample phrases là tham chiếu giọng — hãy bắt chước phong cách, không sao chép nội dung. "
            "Chỉ trả về đúng 1 JSON object hợp lệ, không markdown, không giải thích. "
            "Caption phải cụ thể, có CTA đúng objective, tránh generic, tránh overclaim, và đúng schema CaptionPackage."
        )

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
        return {
            "recommended_objectives": research_brief.recommended_objectives[:3],
            "recommended_pillars": research_brief.recommended_pillars[:4],
            "next_angles": research_brief.next_angles[:5],
            "frequent_questions": research_brief.frequent_questions[:5],
            "campaign_focus": research_brief.campaign_focus[:4],
            "overused_topics": research_brief.overused_topics[:4],
            "recommendations": research_brief.recommendations[:4],
        }

    @staticmethod
    def _weekly_plan_user_prompt(
        profile: BrandProfile,
        start_date: str,
        days: int,
        research_brief: ResearchBrief | None,
    ) -> str:
        return json.dumps(
            {
                "task": "generate_weekly_plan",
                "start_date": start_date,
                "requested_day_count": days,
                "brand_context": OpenAICompatibleClient._compact_profile_payload(profile),
                "research_brief": OpenAICompatibleClient._compact_research_payload(research_brief),
                "requirements": {
                    "plan_title_format": f"weekly-plan-{profile.brand_id}-{start_date}",
                    "one_plan_day_per_requested_day": True,
                    "days_output_must_be_array": "Return days as a JSON array of day objects, never as a number.",
                    "return_json_only": True,
                    "day_fields": ["date", "pillar", "objective", "topic", "angle", "format", "hook", "cta", "visual_brief", "risk_notes"],
                    "top_level_fields": ["plan_title", "days", "strategy_notes", "gaps_or_assumptions"],
                },
            },
            ensure_ascii=False,
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
        return json.dumps(
            {
                "task": "generate_caption_package",
                "topic": topic,
                "pillar": pillar,
                "objective": objective,
                "format": fmt,
                "brand_context": compact_profile,
                "requirements": {
                    "minimum_variants": 1,
                    "return_json_only": True,
                    "variant_fields": ["label", "hook", "caption", "cta", "tone_tags", "visual_brief"],
                    "top_level_fields": ["topic", "variants", "dos", "donts"],
                },
            },
            ensure_ascii=False,
        )


def build_llm_client(settings: Settings):
    if settings.llm_provider == "mock-local":
        return MockLLMClient()
    if settings.llm_provider == "openai-compatible":
        return OpenAICompatibleClient(settings)
    raise ValueError(f"Unsupported provider: {settings.llm_provider}")
