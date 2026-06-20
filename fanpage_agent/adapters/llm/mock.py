"""Mock LLM client — returns deterministic canned responses for dev/test."""

from __future__ import annotations

import json
from datetime import date, timedelta

from fanpage_agent.models import (
    BrandProfile,
    CaptionPackage,
    CaptionVariant,
    ContentStrategy,
    PlanDay,
    ResearchBrief,
    WeeklyPlan,
)


class MockLLMClient:
    """Returns deterministic mock responses without calling any external API."""

    def generate_weekly_plan(
        self,
        profile: BrandProfile,
        start_date: str,
        days: int = 7,
        research_brief: ResearchBrief | None = None,
        strategy: ContentStrategy | None = None,
    ) -> WeeklyPlan:
        start = date.fromisoformat(start_date)
        entries: list[PlanDay] = []
        objectives = self._build_objective_lane(profile, research_brief)
        pillars = self._build_pillar_lane(profile, research_brief, strategy)
        angles = self._build_angle_lane(profile, research_brief)
        first_question = (
            research_brief.frequent_questions[0]
            if research_brief and research_brief.frequent_questions
            else None
        )

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

        dos_rules = (
            list(rules) if rules else ["Giữ câu ngắn", "Nhấn lợi ích thực tế", "Dùng CTA đã duyệt"]
        )
        donts_rules = (
            list(avoid)
            if avoid
            else ["Không claim tuyệt đối", "Không giật gân", "Không dùng banned phrases"]
        )

        tone_a = [traits[0], traits[1 % len(traits)]] if traits else ["rõ ràng"]
        tone_b = (
            [traits[1 % len(traits)], traits[2 % len(traits)]]
            if len(traits) >= 2
            else (traits[:1] + ["rõ ràng"])[:2]
        )
        tone_c = (
            [traits[2 % len(traits)], traits[3 % len(traits)]]
            if len(traits) >= 3
            else (traits[:1] + [traits[-1]])[:2]
        )

        hook_a = f"Về {topic}, có một điều ít ai nói đến"
        hook_b = f"{topic} — bạn đã thử cách này chưa?"
        hook_c = f"{topic}: điều quan trọng nhất cần nhớ"

        caption_a = f"{topic}. {profile.brand_summary} Điều thực sự quan trọng là hiểu rõ bản chất vấn đề, không phải chạy theo số đông."
        caption_b = f"Nhiều người nghĩ {topic} chỉ đơn giản là… nhưng thực tế còn nhiều hơn thế. Bạn đã bao giờ dừng lại và tự hỏi: liệu mình đang làm đúng chưa? {profile.brand_summary}"
        caption_c = f"Hãy cùng nhìn nhận {topic} một cách thực tế. {profile.brand_summary} Bài học rút ra: hiểu đúng gốc rễ vấn đề để có quyết định tốt hơn."

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

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict:
        """Mock tool-compatible response — just says WAIT."""
        return {"role": "assistant", "content": json.dumps({"action": "WAIT", "reason": "mock"})}

    def complete(self, prompt: str, *, system_prompt: str = "", max_tokens: int = 2000) -> str:
        """Mock generic completion — returns a placeholder JSON hashtag response."""
        return json.dumps(
            {
                "suggestions": [
                    {
                        "tag": "#mock_skincare",
                        "tier": "high_volume",
                        "relevance_score": 0.95,
                        "reason": "mock fallback",
                    },
                    {
                        "tag": "#mock_routine",
                        "tier": "high_volume",
                        "relevance_score": 0.90,
                        "reason": "mock fallback",
                    },
                    {
                        "tag": "#mock_tips",
                        "tier": "medium_volume",
                        "relevance_score": 0.85,
                        "reason": "mock fallback",
                    },
                    {
                        "tag": "#mock_glow",
                        "tier": "medium_volume",
                        "relevance_score": 0.80,
                        "reason": "mock fallback",
                    },
                    {
                        "tag": "#mock_acne_free",
                        "tier": "low_volume",
                        "relevance_score": 0.75,
                        "reason": "mock fallback",
                    },
                    {
                        "tag": "#mock_genz",
                        "tier": "branded",
                        "relevance_score": 0.70,
                        "reason": "mock fallback",
                    },
                ],
                "recommended": ["#mock_skincare", "#mock_routine", "#mock_tips", "#mock_glow"],
            }
        )

    @staticmethod
    def _pick_cta(profile: BrandProfile, objective: str) -> str:
        for item in profile.approved_cta_patterns:
            if item.objective == objective:
                return item.cta_text
        return (
            profile.approved_cta_patterns[0].cta_text
            if profile.approved_cta_patterns
            else "Lưu lại khi cần"
        )

    @staticmethod
    def _resolve_pillar(profile: BrandProfile, pillar_name: str):
        for pillar in profile.content_pillars:
            if pillar.pillar_name == pillar_name:
                return pillar
        return profile.content_pillars[0]

    @staticmethod
    def _build_objective_lane(
        profile: BrandProfile, research_brief: ResearchBrief | None
    ) -> list[str]:
        if research_brief and research_brief.recommended_objectives:
            return research_brief.recommended_objectives
        return profile.fanpage_goals or ["reach"]

    @staticmethod
    def _build_pillar_lane(
        profile: BrandProfile,
        research_brief: ResearchBrief | None = None,
        strategy: ContentStrategy | None = None,
    ) -> list[str]:
        if strategy and strategy.recommended_pillar_mix:
            # Sort pillars by recommended mix (highest first)
            sorted_pillars = sorted(
                strategy.recommended_pillar_mix.items(),
                key=lambda x: x[1],
                reverse=True,
            )
            return [p[0] for p in sorted_pillars]
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
