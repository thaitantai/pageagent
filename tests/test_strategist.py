"""Tests for StrategistTool — content strategy logic, mock and LLM paths."""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from fanpage_agent.models import (
    BrandProfile,
    ContentStrategy,
    ResearchBrief,
    ResearchEvidence,
    ResearchTopicScore,
    StrategyIdea,
    TrendItem,
)
from fanpage_agent.tools.content.strategist import StrategistTool

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_BRAND = ROOT / "data" / "sample" / "brand_profile.json"


def _load_profile() -> BrandProfile:
    from fanpage_agent.loaders.brand_loader import load_brand_profile
    return load_brand_profile(SAMPLE_BRAND)


def _minimal_brief() -> ResearchBrief:
    return ResearchBrief(
        top_performing_topics=["Vitamin C cho da dầu"],
        overused_topics=["Rửa mặt nhiều lần"],
        frequent_questions=["Retinol có dùng được cho da nhạy cảm không?"],
        next_angles=["Vitamin C kết hợp với E và Ferulic"],
        external_trends=[
            TrendItem(title="Xu hướng skin cycling đang hot trên TikTok", source="web", url="https://example.com/1"),
            TrendItem(title="So sánh retinol và bakuchiol cho người mới bắt đầu", source="web", url="https://example.com/2"),
        ],
        topic_scores=[
            ResearchTopicScore(topic="Vitamin C cho da dầu", total_score=8.5),
            ResearchTopicScore(topic="Retinol cho người mới", total_score=7.0),
            ResearchTopicScore(topic="Kem chống nắng vật lý vs hóa học", total_score=5.0),
        ],
        evidence=[
            ResearchEvidence(claim="Vitamin C giúp sáng da và chống oxy hóa",
                             source="web", confidence=0.8),
        ],
        confidence_score=0.75,
        quality_warnings=[],
        competitor_analysis={
            "cross_competitor": {
                "strategic_recommendations": [
                    "Tập trung vào nội dung giáo dục chuyên sâu thay vì review nhanh",
                    "Phát triển góc nhìn khoa học thay vì cảm tính",
                ],
            },
            "profiles": [
                {
                    "name": "Hasaki Vietnam",
                    "unique_angle": "Review sản phẩm bán chạy kèm deal",
                    "products_detected": ["Kem chống nắng Anessa"],
                },
                {
                    "name": "Cocoon Vietnam",
                    "unique_angle": "Mỹ phẩm thuần Việt, thân thiện môi trường",
                    "products_detected": [],
                },
            ],
        },
    )


# ═══════════════════════════════════════════════
# StrategistTool — mock mode tests
# ═══════════════════════════════════════════════

class StrategistToolMockTest(unittest.TestCase):
    """Tests for mock (deterministic) strategy generation."""

    def setUp(self) -> None:
        self.tool = StrategistTool()
        self.profile = _load_profile()

    def test_build_strategy_returns_content_strategy(self) -> None:
        strategy = self.tool.build_strategy(profile=self.profile)
        self.assertIsInstance(strategy, ContentStrategy)
        self.assertEqual(strategy.brand_id, self.profile.brand_id)
        self.assertEqual(strategy.generated_by, "mock")

    def test_build_strategy_has_pillar_mix(self) -> None:
        strategy = self.tool.build_strategy(profile=self.profile)
        self.assertTrue(len(strategy.recommended_pillar_mix) > 0)
        total = sum(strategy.recommended_pillar_mix.values())
        self.assertAlmostEqual(total, 1.0, places=1)

    def test_build_strategy_pillars_match_profile(self) -> None:
        strategy = self.tool.build_strategy(profile=self.profile)
        profile_pillars = {p.pillar_name for p in self.profile.content_pillars}
        strategy_pillars = set(strategy.recommended_pillar_mix.keys())
        self.assertTrue(strategy_pillars.issubset(profile_pillars))

    def test_build_strategy_no_research_brief(self) -> None:
        """Should still produce valid strategy without research input."""
        strategy = self.tool.build_strategy(profile=self.profile)
        self.assertIsNotNone(strategy.recommended_pillar_mix)
        self.assertEqual(len(strategy.trend_driven_ideas), 0)
        self.assertEqual(len(strategy.competitor_fills), 0)
        self.assertGreater(len(strategy.strategic_reasoning), 0)

    def test_build_strategy_with_research_brief(self) -> None:
        brief = _minimal_brief()
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        # 3 topic scores + 2 trends + 1 question = 6 trend ideas
        self.assertEqual(len(strategy.trend_driven_ideas), 6)
        # 2 strategic recs + 2 competitor angles + 1 product gap = 5 competitor fills
        self.assertEqual(len(strategy.competitor_fills), 5)
        self.assertGreater(strategy.confidence_score, 0.5)

    def test_build_strategy_includes_strategic_reasoning(self) -> None:
        brief = _minimal_brief()
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        self.assertTrue(len(strategy.strategic_reasoning) > 20)
        self.assertIn("pillar", strategy.strategic_reasoning.lower())

    def test_build_strategy_confidence_without_brief(self) -> None:
        strategy = self.tool.build_strategy(profile=self.profile)
        self.assertAlmostEqual(strategy.confidence_score, 0.3)

    def test_build_strategy_confidence_with_brief(self) -> None:
        brief = _minimal_brief()
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        self.assertGreater(strategy.confidence_score, 0.5)
        self.assertLessEqual(strategy.confidence_score, 1.0)

    def test_trend_ideas_from_topic_scores(self) -> None:
        brief = _minimal_brief()
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        ideas = strategy.trend_driven_ideas
        topics = [i.topic for i in ideas]
        self.assertIn("Vitamin C cho da dầu", topics)
        self.assertIn("Retinol cho người mới", topics)

    def test_trend_ideas_high_priority(self) -> None:
        brief = _minimal_brief()
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        high_priority = [i for i in strategy.trend_driven_ideas if i.priority == "high"]
        medium = [i for i in strategy.trend_driven_ideas if i.priority == "medium"]
        self.assertTrue(len(high_priority) > 0)
        self.assertTrue(len(medium) > 0)

    def test_trend_ideas_from_external_trends(self) -> None:
        brief = _minimal_brief()
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        ideas = strategy.trend_driven_ideas
        # External trends should be included
        self.assertTrue(any("skin cycling" in i.topic for i in ideas) or
                        any("retinol" in i.topic.lower() for i in ideas))

    def test_trend_ideas_from_questions(self) -> None:
        brief = _minimal_brief()
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        ideas = strategy.trend_driven_ideas
        self.assertTrue(any("retinol" in i.topic.lower() for i in ideas))

    def test_competitor_fills_from_cross_competitor(self) -> None:
        brief = _minimal_brief()
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        fills = strategy.competitor_fills
        self.assertTrue(len(fills) > 0)
        # Should include the strategic recommendation
        self.assertTrue(any("giáo dục" in f.topic for f in fills) or
                        any("education" in f.topic.lower() for f in fills))

    def test_competitor_fills_from_profiles(self) -> None:
        brief = _minimal_brief()
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        fills = strategy.competitor_fills
        # Should reference competitor names
        all_text = " ".join(f.topic for f in fills)
        self.assertTrue("Hasaki" in all_text or "Cocoon" in all_text)

    def test_competitor_fills_include_product_gaps(self) -> None:
        brief = _minimal_brief()
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        product_fills = [f for f in strategy.competitor_fills if f.pillar == "product_review"]
        self.assertTrue(len(product_fills) >= 1)

    def test_recommended_posting_times_default(self) -> None:
        strategy = self.tool.build_strategy(profile=self.profile)
        self.assertTrue(len(strategy.recommended_posting_times) >= 2)
        self.assertIn("09:00", strategy.recommended_posting_times)

    def test_weekly_frequency(self) -> None:
        strategy = self.tool.build_strategy(profile=self.profile)
        self.assertIn(strategy.weekly_frequency, [5, 7])

    def test_compute_pillar_mix_normalizes_to_1(self) -> None:
        mix = self.tool._compute_pillar_mix(self.profile)
        total = sum(mix.values())
        self.assertAlmostEqual(total, 1.0, places=1)

    def test_compute_pillar_mix_with_brief_recommendations(self) -> None:
        brief = ResearchBrief(recommended_pillars=["education", "product_review"])
        mix = self.tool._compute_pillar_mix(self.profile, brief)
        # education should be boosted
        default_mix = self.tool._compute_pillar_mix(self.profile)
        self.assertGreaterEqual(mix.get("education", 0), default_mix.get("education", 0))

    def test_infer_pillar_routine(self) -> None:
        self.assertEqual(self.tool._infer_pillar("Routine sáng tối cơ bản"), "routine_guide")

    def test_infer_pillar_education(self) -> None:
        self.assertEqual(self.tool._infer_pillar("Vitamin C và cách dùng"), "education")

    def test_infer_pillar_myth(self) -> None:
        self.assertEqual(self.tool._infer_pillar("Myth về dưỡng ẩm cho da dầu"), "myth_busting")

    def test_infer_pillar_product_review(self) -> None:
        self.assertEqual(self.tool._infer_pillar("Review kem chống nắng giá rẻ"), "product_review")

    def test_infer_pillar_viet_brand(self) -> None:
        self.assertEqual(self.tool._infer_pillar("Mỹ phẩm thuần Việt nào đáng mua?"), "viet_brand_spotlight")

    def test_infer_pillar_fallback(self) -> None:
        self.assertEqual(self.tool._infer_pillar("Một chủ đề hoàn toàn mới và lạ"), "education")

    def test_empty_brief_no_crash(self) -> None:
        """Empty ResearchBrief should not cause errors."""
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=ResearchBrief())
        self.assertIsInstance(strategy, ContentStrategy)

    def test_generated_at_is_valid_iso(self) -> None:
        strategy = self.tool.build_strategy(profile=self.profile)
        # Should be a valid ISO datetime string
        dt = datetime.fromisoformat(strategy.generated_at)
        self.assertIsNotNone(dt)

    def test_warnings_from_quality_gate(self) -> None:
        brief = _minimal_brief()
        brief.quality_warnings = ["Low confidence on some topics", "Source age > 30 days"]
        strategy = self.tool.build_strategy(profile=self.profile, research_brief=brief)
        self.assertTrue(len(strategy.warnings) > 0)


# ═══════════════════════════════════════════════
# StrategistTool — LLM mode tests
# ═══════════════════════════════════════════════

class StrategistToolLLMTest(unittest.TestCase):
    """Tests for LLM strategy generation (uses mock LLM)."""

    def test_build_strategy_with_mock_llm_fallback(self) -> None:
        """When LLM client returns non-JSON, should fall back to mock."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = "This is not JSON"
        tool = StrategistTool(llm_client=mock_llm)
        strategy = tool.build_strategy(profile=_load_profile())
        self.assertEqual(strategy.generated_by, "mock")

    def test_build_strategy_with_mock_llm_valid_json(self) -> None:
        """When LLM client returns valid JSON, should parse it."""
        mock_llm = MagicMock()
        strategy_json = json.dumps({
            "recommended_pillar_mix": {"education": 0.5, "product_review": 0.3, "routine_guide": 0.2},
            "trend_driven_ideas": [
                {"pillar": "education", "topic": "Skin cycling", "angle": "Từ TikTok đến khoa học", "priority": "high", "rationale": "Hot trend"},
            ],
            "competitor_fills": [],
            "recommended_posting_times": ["08:00", "20:00"],
            "weekly_frequency": 7,
            "strategic_reasoning": "Tập trung giáo dục là chính",
            "confidence_score": 0.85,
        })
        mock_llm.complete.return_value = strategy_json
        tool = StrategistTool(llm_client=mock_llm)
        strategy = tool.build_strategy(profile=_load_profile())
        self.assertEqual(strategy.generated_by, "llm")
        self.assertEqual(strategy.weekly_frequency, 7)
        self.assertEqual(len(strategy.trend_driven_ideas), 1)
        self.assertEqual(strategy.trend_driven_ideas[0].pillar, "education")

    def test_build_strategy_llm_with_code_fence(self) -> None:
        """LLM returns JSON inside markdown code fence."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = """Here is the strategy:
```json
{"recommended_pillar_mix": {"education": 1.0}, "trend_driven_ideas": [], "competitor_fills": [], "recommended_posting_times": ["09:00"], "weekly_frequency": 5, "strategic_reasoning": "test", "confidence_score": 0.5}
```
"""
        tool = StrategistTool(llm_client=mock_llm)
        strategy = tool.build_strategy(profile=_load_profile())
        self.assertEqual(strategy.generated_by, "llm")
        self.assertIn("education", strategy.recommended_pillar_mix)

    def test_build_strategy_llm_client_raises_error(self) -> None:
        """When LLM client raises, should fall back to mock gracefully."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = RuntimeError("API error")
        tool = StrategistTool(llm_client=mock_llm)
        strategy = tool.build_strategy(profile=_load_profile())
        self.assertEqual(strategy.generated_by, "mock")
        self.assertIsInstance(strategy, ContentStrategy)


# ═══════════════════════════════════════════════
# ContentStrategy model tests
# ═══════════════════════════════════════════════

class ContentStrategyModelTest(unittest.TestCase):
    """Tests for ContentStrategy Pydantic model."""

    def test_minimal_strategy(self) -> None:
        s = ContentStrategy(brand_id="test", generated_at="2026-06-09T12:00:00", recommended_pillar_mix={"education": 1.0})
        self.assertEqual(s.brand_id, "test")
        self.assertEqual(s.generated_by, "mock")
        self.assertEqual(len(s.trend_driven_ideas), 0)
        self.assertEqual(len(s.competitor_fills), 0)

    def test_strategy_serializes_to_json(self) -> None:
        s = ContentStrategy(brand_id="test", generated_at="2026-06-09T12:00:00", recommended_pillar_mix={"education": 0.5, "product_review": 0.5})
        data = s.model_dump(mode="json")
        self.assertIn("recommended_pillar_mix", data)
        self.assertIn("generated_by", data)
        self.assertEqual(data["brand_id"], "test")

    def test_strategy_idea_high_priority(self) -> None:
        idea = StrategyIdea(pillar="education", topic="Vitamin C", angle="Cách dùng", priority="high")
        self.assertEqual(idea.priority, "high")

    def test_strategy_idea_with_target_audience(self) -> None:
        idea = StrategyIdea(pillar="education", topic="Retinol", angle="Cho người mới", target_audience="GenZ mới tập skincare")
        self.assertTrue(len(idea.target_audience) > 0)

    def test_strategy_idea_default_priority(self) -> None:
        idea = StrategyIdea(pillar="education", topic="Test", angle="test angle")
        self.assertEqual(idea.priority, "medium")


# ═══════════════════════════════════════════════
# PlannerTool integration tests
# ═══════════════════════════════════════════════

class PlannerToolIntegrationTest(unittest.TestCase):
    """PlannerTool should accept ContentStrategy and adjust pillar lane."""

    def test_planner_accepts_strategy(self) -> None:
        from fanpage_agent.tools.publishing.planner import PlannerTool
        from fanpage_agent.adapters.llm_client import MockLLMClient

        profile = _load_profile()
        strategy = ContentStrategy(
            brand_id=profile.brand_id,
            generated_at="2026-06-09T12:00:00",
            recommended_pillar_mix={"education": 0.5, "product_review": 0.3, "routine_guide": 0.2},
        )
        planner = PlannerTool(llm_client=MockLLMClient())
        plan = planner.plan_week(profile=profile, start_date="2026-06-09", days=3, strategy=strategy)
        self.assertEqual(len(plan.days), 3)

    def test_planner_strategy_affects_pillar_order(self) -> None:
        from fanpage_agent.tools.publishing.planner import PlannerTool
        from fanpage_agent.adapters.llm_client import MockLLMClient

        profile = _load_profile()
        # Sample profile has "education" and "trust"
        strategy = ContentStrategy(
            brand_id=profile.brand_id,
            generated_at="2026-06-09T12:00:00",
            recommended_pillar_mix={"education": 0.6, "trust": 0.4},
        )
        planner = PlannerTool(llm_client=MockLLMClient())
        plan = planner.plan_week(profile=profile, start_date="2026-06-09", days=3, strategy=strategy)
        # First day should be the highest mix pillar
        self.assertEqual(plan.days[0].pillar, "education")


if __name__ == "__main__":
    unittest.main()
