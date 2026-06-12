"""
StrategistTool — content strategist that sits between Research and Planner.

Transforms ResearchBrief + BrandProfile into a structured ContentStrategy:
  - Recommended pillar mix (% per pillar)
  - Trend-driven content ideas
  - Competitor gap fills
  - Optimal posting schedule / timing
  - Strategic reasoning

Two modes:
  1. mock — deterministic output based on brand profile + research (dev/test)
  2. llm — LLM-generated strategy via OpenAICompatibleClient
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fanpage_agent.models import (
    BrandProfile,
    ContentStrategy,
    ResearchBrief,
    StrategyIdea,
)
from fanpage_agent.tools.research.competitor_page_discovery import (
    CompetitorPageDiscoveryTool,
)

logger = logging.getLogger(__name__)

# ── Default pillar mix khi không có LLM ──────────────────────────
DEFAULT_PILLAR_MIX: dict[str, float] = {
    "education": 0.30,
    "product_review": 0.20,
    "myth_busting": 0.15,
    "routine_guide": 0.20,
    "viet_brand_spotlight": 0.15,
}

DEFAULT_POSTING_TIMES: list[str] = [
    "09:00",
    "12:00",
    "20:00",
]


class StrategistTool:
    """Content strategist — research → strategy bridge."""

    def __init__(
        self,
        llm_client: Any = None,
        competitor_discovery: CompetitorPageDiscoveryTool | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._competitor_discovery = competitor_discovery or CompetitorPageDiscoveryTool()

    # ── Public API ──────────────────────────────────────────────

    def build_strategy(
        self,
        profile: BrandProfile,
        research_brief: ResearchBrief | None = None,
    ) -> ContentStrategy:
        """Build a full content strategy from brand profile + research data.

        Uses LLM client if available, otherwise falls back to deterministic mock.
        """
        if self._llm_client and hasattr(self._llm_client, "complete"):
            try:
                return self._llm_strategy(profile, research_brief)
            except Exception as exc:
                logger.warning("LLM strategy failed, falling back to mock: %s", exc)

        return self._mock_strategy(profile, research_brief)

    # ── Mock mode (deterministic, no LLM calls) ────────────────

    def _mock_strategy(
        self,
        profile: BrandProfile,
        research_brief: ResearchBrief | None = None,
    ) -> ContentStrategy:
        """Generate a deterministic strategy from brand profile + research data.

        This is the dev/test fallback. It produces reasonable output purely from
        rule-based logic.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        pillar_mix = self._compute_pillar_mix(profile, research_brief)
        trend_ideas = self._mock_trend_ideas(profile, research_brief)
        competitor_fills = self._mock_competitor_fills(profile, research_brief) if research_brief else []
        warnings: list[str] = []

        # ── Reasoning ──
        reasoning_parts: list[str] = []
        reasoning_parts.append(
            f"Phân bổ pillar dựa trên {len(profile.content_pillars)} pillar có sẵn."
        )
        if research_brief:
            if research_brief.topic_scores:
                reasoning_parts.append(
                    f"Có {len(research_brief.topic_scores)} topic đã chấm điểm — ưu tiên topic điểm cao."
                )
            if research_brief.external_trends:
                reasoning_parts.append(
                    f"Phát hiện {len(research_brief.external_trends)} trend ngoài — "
                    f"sinh {len(trend_ideas)} ý tưởng trend-driven."
                )
            if research_brief.competitor_analysis:
                cc = research_brief.competitor_analysis
                comp_count = len(cc.get("profiles", [])) if isinstance(cc, dict) else 0
                if comp_count:
                    reasoning_parts.append(
                        f"Phân tích {comp_count} đối thủ — phát hiện {len(competitor_fills)} cơ hội gap."
                    )
                else:
                    reasoning_parts.append("Có dữ liệu competitor analysis nhưng chưa có profile cụ thể.")
            if research_brief.quality_warnings:
                warnings.extend(research_brief.quality_warnings[:3])

        total_products = len(profile.products_services)
        if total_products:
            reasoning_parts.append(
                f"Tận dụng {total_products} product/service categories cho bài review."
            )

        # ── Confidence ──
        confidence = 0.3
        if research_brief:
            if research_brief.topic_scores:
                confidence += 0.2
            if research_brief.external_trends:
                confidence += 0.15
            if research_brief.competitor_analysis:
                confidence += 0.15
            if research_brief.evidence:
                confidence += 0.15
        confidence = min(confidence, 0.95)

        return ContentStrategy(
            brand_id=profile.brand_id,
            generated_at=now,
            recommended_pillar_mix=pillar_mix,
            trend_driven_ideas=trend_ideas,
            competitor_fills=competitor_fills,
            recommended_posting_times=list(DEFAULT_POSTING_TIMES),
            weekly_frequency=self._compute_weekly_frequency(profile, research_brief),
            strategic_reasoning=" | ".join(reasoning_parts),
            confidence_score=round(confidence, 2),
            generated_by="mock",
            warnings=warnings,
        )

    def _compute_pillar_mix(
        self,
        profile: BrandProfile,
        research_brief: ResearchBrief | None = None,
    ) -> dict[str, float]:
        """Compute pillar mix from brand profile pillars + research signals."""
        pillar_names = [p.pillar_name for p in profile.content_pillars]
        if not pillar_names:
            return dict(DEFAULT_PILLAR_MIX)

        # Start with default mix, keep only pillars that exist in profile
        mix = {k: v for k, v in DEFAULT_PILLAR_MIX.items() if k in pillar_names}

        # Add any extra pillars from profile (evenly split from remainder)
        extra_pillars = [p for p in pillar_names if p not in mix]
        if extra_pillars:
            remainder = 1.0 - sum(mix.values())
            each = remainder / len(extra_pillars)
            for p in extra_pillars:
                mix[p] = round(each, 2)

        # Normalize
        total = sum(mix.values())
        if total > 0:
            mix = {k: round(v / total, 2) for k, v in mix.items()}

        # Adjust from research signals
        if research_brief and research_brief.recommended_pillars:
            boost = research_brief.recommended_pillars[:3]
            for p in boost:
                if p in mix:
                    mix[p] = min(mix[p] + 0.10, 0.50)

        # Re-normalize
        total = sum(mix.values())
        if total > 0:
            mix = {k: round(v / total, 2) for k, v in mix.items()}

        return mix

    def _mock_trend_ideas(
        self,
        profile: BrandProfile,
        research_brief: ResearchBrief | None = None,
    ) -> list[StrategyIdea]:
        """Generate trend-driven ideas from research data."""
        ideas: list[StrategyIdea] = []

        if not research_brief:
            return ideas

        # Ideas from topic scores
        seen_topics: set[str] = set()
        for ts in research_brief.topic_scores[:5]:
            if ts.topic in seen_topics:
                continue
            seen_topics.add(ts.topic)
            priority = "high" if ts.total_score >= 7 else ("medium" if ts.total_score >= 4 else "low")
            pillar = self._infer_pillar(ts.topic)
            audience = profile.target_audiences[0].segment_name if profile.target_audiences else ""

            ideas.append(StrategyIdea(
                pillar=pillar,
                topic=ts.topic,
                angle=f"Khám phá {ts.topic} — dựa trên dữ liệu nghiên cứu thực tế",
                target_audience=audience,
                rationale=f"Topic score {ts.total_score}/10 — {ts.rationale[:100]}" if ts.rationale else f"Topic score {ts.total_score}/10",
                priority=priority,
            ))

        # Ideas from external trends
        for trend in research_brief.external_trends[:3]:
            if trend.title in seen_topics:
                continue
            seen_topics.add(trend.title)
            ideas.append(StrategyIdea(
                pillar=self._infer_pillar(trend.title),
                topic=trend.title[:80],
                angle=f"Theo xu hướng — {trend.snippet[:100]}" if trend.snippet else "Xu hướng mới — khai thác sớm",
                rationale=f"Nguồn: {trend.source}",
                priority="high" if trend.relevance else "medium",
            ))

        # Ideas from frequent questions
        for q in research_brief.frequent_questions[:3]:
            if q in seen_topics:
                continue
            seen_topics.add(q)
            ideas.append(StrategyIdea(
                pillar="education",
                topic=q[:80],
                angle=f"Giải đáp thắc mắc phổ biến: {q[:80]}",
                rationale="Từ câu hỏi thực tế của community — đảm bảo relevance",
                priority="high",
            ))

        return ideas

    def _mock_competitor_fills(
        self,
        profile: BrandProfile,
        research_brief: ResearchBrief | None,
    ) -> list[StrategyIdea]:
        """Generate competitor gap fill ideas from competitor_analysis."""
        fills: list[StrategyIdea] = []
        if not research_brief:
            return fills

        ca = research_brief.competitor_analysis
        if not isinstance(ca, dict):
            return fills

        # Cross-competitor insight
        cross = ca.get("cross_competitor", {})
        if isinstance(cross, dict):
            for rec in cross.get("strategic_recommendations", [])[:3]:
                fills.append(StrategyIdea(
                    pillar=self._infer_pillar(str(rec)),
                    topic=str(rec)[:80],
                    angle=f"Chiến lược đối thủ → hành động: {str(rec)[:80]}",
                    rationale="Từ phân tích cross-competitor gap",
                    priority="high",
                ))

        # Unique angle from each competitor profile
        profiles = ca.get("profiles", []) if isinstance(ca, dict) else []
        if isinstance(profiles, list):
            for prof in profiles[:5]:
                if isinstance(prof, dict):
                    name = prof.get("name", "?")
                    angle = prof.get("unique_angle") or prof.get("unique_selling_proposition", "")
                    if angle:
                        fills.append(StrategyIdea(
                            pillar=self._infer_pillar(str(angle)),
                            topic=f"Cơ hội từ {name}: {str(angle)[:80]}",
                            angle=f"Đối thủ {name} đang làm '{str(angle)[:80]}' — mình có thể khai thác góc nhìn khác",
                            rationale=f"Unique angle của {name} chưa được khai thác",
                            priority="high",
                        ))
                    products = prof.get("products_detected", [])
                    if isinstance(products, list) and products:
                        gap = products[0]
                        fills.append(StrategyIdea(
                            pillar="product_review",
                            topic=f"Sản phẩm đối thủ đang đẩy: {gap}",
                            angle=f"Phân tích sản phẩm {gap} — review khách quan từ góc nhìn GenZ",
                            rationale=f"{name} đang tập trung vào sản phẩm này — cần theo dõi",
                            priority="medium",
                        ))

        return fills

    # ── LLM mode ────────────────────────────────────────────────

    def _llm_strategy(
        self,
        profile: BrandProfile,
        research_brief: ResearchBrief | None = None,
    ) -> ContentStrategy:
        """Generate strategy using LLM client."""
        research_context = self._format_research_for_llm(research_brief)

        user_prompt = f"""Xây dựng chiến lược content cho fanpage skincare GenZ.

THƯƠNG HIỆU: {profile.brand_name}
NGÀNH: {profile.industry}
MỤC TIÊU: {profile.business_goal}

CONTENT PILLARS:
{self._format_pillars(profile)}

ĐỐI TƯỢNG:
{self._format_audiences(profile)}

{research_context}

YÊU CẦU OUTPUT (JSON):
{{
  "recommended_pillar_mix": {{"pillar_name": percentage_0_to_1}},
  "trend_driven_ideas": [
    {{"pillar": "pillar_name", "topic": "chủ đề", "angle": "góc tiếp cận", "priority": "high|medium|low", "rationale": "lý do"}}
  ],
  "competitor_fills": [
    {{"pillar": "pillar_name", "topic": "chủ đề", "angle": "góc tiếp cận", "priority": "high|medium|low", "rationale": "lý do"}}
  ],
  "recommended_posting_times": ["HH:MM", "HH:MM", "HH:MM"],
  "weekly_frequency": 5,
  "strategic_reasoning": "giải thích ngắn gọn chiến lược",
  "confidence_score": 0.7
}}

Viết reasoning bằng tiếng Việt. Phân bổ pillar phải dựa trên mục tiêu brand (reach/engagement/lead).
"""

        result = self._llm_client.complete(
            prompt=user_prompt,
            system_prompt=self._strategist_system_prompt(),
            max_tokens=3000,
        )

        try:
            data = json.loads(self._extract_json(result))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("LLM JSON parse failed: %s — falling back to mock", exc)
            return self._mock_strategy(profile, research_brief)

        now = datetime.now(tz=timezone.utc).isoformat()
        ideas = [
            StrategyIdea(**i) for i in data.get("trend_driven_ideas", [])
            if isinstance(i, dict) and i.get("pillar") and i.get("topic")
        ]
        fills = [
            StrategyIdea(**i) for i in data.get("competitor_fills", [])
            if isinstance(i, dict) and i.get("pillar") and i.get("topic")
        ]

        return ContentStrategy(
            brand_id=profile.brand_id,
            generated_at=now,
            recommended_pillar_mix=data.get("recommended_pillar_mix", self._compute_pillar_mix(profile, research_brief)),
            trend_driven_ideas=ideas,
            competitor_fills=fills,
            recommended_posting_times=data.get("recommended_posting_times", list(DEFAULT_POSTING_TIMES)),
            weekly_frequency=data.get("weekly_frequency", 5),
            strategic_reasoning=data.get("strategic_reasoning", ""),
            confidence_score=round(data.get("confidence_score", 0.7), 2),
            generated_by="llm",
            warnings=[],
        )

    # ── Helpers ─────────────────────────────────────────────────

    def _compute_weekly_frequency(
        self,
        profile: BrandProfile,
        research_brief: ResearchBrief | None = None,
    ) -> int:
        """Suggest weekly posting frequency based on goals and research."""
        goals = {g.lower() for g in profile.fanpage_goals}
        if "reach" in goals and "engagement" in goals:
            return 7
        if "lead" in goals:
            return 5
        return 5

    @staticmethod
    def _infer_pillar(text: str) -> str:
        """Map a topic/idea to the most likely pillar."""
        t = text.lower()
        if any(w in t for w in ["routine", "sáng", "tối", "layer", "bước"]):
            return "routine_guide"
        if any(w in t for w in ["việt", "cocoon", "thuần việt", "nội địa"]):
            return "viet_brand_spotlight"
        if any(w in t for w in ["vitamin", "retinol", "niacinamide", "bha", "aha", "thành phần", "ingredient"]):
            return "education"
        if any(w in t for w in ["myth", "lầm tưởng", "sai lầm", "thật"]):
            return "myth_busting"
        if any(w in t for w in ["review", "so sánh", "sản phẩm", "đáng mua", "giá"]):
            return "product_review"
        return "education"

    @staticmethod
    def _strategist_system_prompt() -> str:
        return (
            "Bạn là strategist content cho fanpage skincare GenZ. "
            "Nhiệm vụ: phân tích dữ liệu nghiên cứu (trend, đối thủ, community Q&A) "
            "và đưa ra chiến lược content tối ưu — pillar mix, ý tưởng trend-driven, "
            "gap fill từ đối thủ. Output là JSON có cấu trúc. "
            "Luôn ưu tiên nội dung dựa trên evidence, không phỏng đoán."
        )

    @staticmethod
    def _format_pillars(profile: BrandProfile) -> str:
        parts = []
        for p in profile.content_pillars:
            angles = "; ".join(p.example_angles[:3]) if p.example_angles else ""
            parts.append(f"  - {p.pillar_name}: {p.description} [{p.goal}]")
            if angles:
                parts.append(f"    Góc: {angles}")
        return "\n".join(parts)

    @staticmethod
    def _format_audiences(profile: BrandProfile) -> str:
        parts = []
        for a in profile.target_audiences:
            pains = "; ".join(a.pain_points[:3])
            parts.append(f"  - {a.segment_name}: {pains}")
        return "\n".join(parts)

    @staticmethod
    def _format_research_for_llm(research_brief: ResearchBrief | None) -> str:
        if not research_brief:
            return "KHÔNG CÓ DỮ LIỆU NGHIÊN CỨU."

        parts: list[str] = []
        parts.append("DỮ LIỆU NGHIÊN CỨU:")

        if research_brief.topic_scores:
            parts.append(f"\nTOPIC SCORES ({len(research_brief.topic_scores)} topics):")
            for ts in research_brief.topic_scores[:8]:
                parts.append(f"  - [{ts.total_score}/10] {ts.topic} (risk: {ts.duplication_risk})")

        if research_brief.external_trends:
            parts.append(f"\nEXTERNAL TRENDS ({len(research_brief.external_trends)} items):")
            for t in research_brief.external_trends[:5]:
                parts.append(f"  - {t.title} ({t.source})")

        if research_brief.frequent_questions:
            parts.append(f"\nCOMMON QUESTIONS ({len(research_brief.frequent_questions)}):")
            for q in research_brief.frequent_questions[:5]:
                parts.append(f"  - {q}")

        if research_brief.competitor_analysis:
            parts.append(f"\nCOMPETITOR ANALYSIS: available")

        if research_brief.overused_topics:
            parts.append(f"\nTRÁNH (overused): {', '.join(research_brief.overused_topics[:5])}")

        return "\n".join(parts)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from LLM response (handles markdown code fences)."""
        import re
        # Try ```json ... ``` first
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Try standalone { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return m.group(0)
        return text.strip()
