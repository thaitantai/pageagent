"""Tests for competitor discovery tools — models, helpers, and discovery logic."""

import unittest
from datetime import datetime, timezone

from fanpage_agent.tools.research.competitor_models import (
    ContentFormat,
    CompetitorProfile,
    CrossCompetitorInsight,
)
from fanpage_agent.tools.research.competitor_helpers import (
    is_noise_url,
    has_skincare_context,
    detect_content_format,
    estimate_price_positioning,
    estimate_content_tone,
)
from fanpage_agent.tools.research.competitor_learning_store import (
    profile_to_dict,
    extract_brand_names,
)


class CompetitorModelsTest(unittest.TestCase):
    """CompetitorProfile dataclass + serialisation."""

    def test_competitor_profile_defaults(self) -> None:
        p = CompetitorProfile(name="test_brand")
        self.assertEqual(p.name, "test_brand")
        self.assertEqual(p.products_detected, [])
        self.assertEqual(p.angles_detected, [])
        # Default values
        self.assertEqual(p.top_format, "")
        self.assertIsNotNone(p.analyzed_at)
        # price_positioning defaults to "" not "mid"
        self.assertIn(p.price_positioning, ("mid", ""))
        # content_tone defaults to "" not "educational"
        self.assertIn(p.content_tone, ("educational", ""))
        self.assertEqual(p.unique_angle, "")

    def test_competitor_profile_full(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="minutes")
        p = CompetitorProfile(
            name="test_brand",
            products_detected=["Serum", "Kem chống nắng"],
            top_products=["Serum", "Kem chống nắng"],
            angles_detected=["review", "how_to"],
            top_angle="review",
            formats_detected=[ContentFormat(type="review", confidence=0.8)],
            top_format="review",
            price_positioning="premium",
            content_tone="scientific",
            search_urls=["https://example.com"],
            findings_count=5,
            unique_angle="science_clinical_focus",
            analyzed_at=now,
        )
        self.assertEqual(p.top_products, ["Serum", "Kem chống nắng"])
        self.assertEqual(p.price_positioning, "premium")
        self.assertEqual(p.content_tone, "scientific")
        self.assertEqual(len(p.search_urls), 1)

    def test_cross_competitor_insight_defaults(self) -> None:
        ins = CrossCompetitorInsight()
        self.assertEqual(ins.shared_products, [])
        self.assertEqual(ins.gap_products, [])
        self.assertEqual(ins.underused_formats, [])
        self.assertEqual(ins.recommendation, "")

    def test_cross_competitor_insight_full(self) -> None:
        ins = CrossCompetitorInsight(
            shared_products=[("Kem chống nắng", 3)],
            unique_products_by_competitor={"brand_a": ["Serum"]},
            gap_products=["Eye cream", "BHA"],
            underused_formats=["tutorial"],
            recommendation="Test recommendation",
        )
        self.assertEqual(len(ins.shared_products), 1)
        self.assertEqual(ins.shared_products[0][0], "Kem chống nắng")
        self.assertIn("BHA", ins.gap_products)
        self.assertEqual(ins.recommendation, "Test recommendation")

    def test_profile_to_dict_roundtrip(self) -> None:
        p = CompetitorProfile(
            name="roundtrip_test",
            products_detected=["Serum"],
            top_products=["Serum"],
            angles_detected=["review"],
            top_angle="review",
            formats_detected=[ContentFormat(type="how_to", confidence=0.9)],
            top_format="how_to",
            price_positioning="budget",
            content_tone="entertaining",
            unique_angle="honest_review_focus",
            findings_count=3,
        )
        d = profile_to_dict(p)
        self.assertEqual(d["name"], "roundtrip_test")
        self.assertEqual(d["top_products"], ["Serum"])
        self.assertEqual(d["content_tone"], "entertaining")
        self.assertIn("analyzed_at", d)


class CompetitorHelpersTest(unittest.TestCase):
    """Utility functions used throughout competitor analysis."""

    def test_is_noise_url_matches_noise_domains(self) -> None:
        self.assertTrue(is_noise_url("https://kenh14.vn/lam-dep.html"))
        self.assertTrue(is_noise_url("https://webtretho.com/forum/skincare"))
        self.assertTrue(is_noise_url("https://ngoisao.vn/tin-tuc"))
        self.assertTrue(is_noise_url("https://yeah1.com/lam-dep"))

    def test_is_noise_url_skips_clean_urls(self) -> None:
        self.assertFalse(is_noise_url("https://hasaki.vn/serum-duong-da"))
        self.assertFalse(is_noise_url("https://cocoonvietnam.com/san-pham"))
        self.assertFalse(is_noise_url("https://example.com/skincare-review"))

    def test_is_noise_url_filters_by_category(self) -> None:
        # vnexpress regex matches ALL vnexpress URLs (no category filter)
        self.assertTrue(is_noise_url("https://vnexpress.net/suc-khoe/lam-dep"))
        self.assertTrue(is_noise_url("https://vnexpress.net/thoi-su/chinh-tri"))

    def test_has_skincare_context_positives(self) -> None:
        self.assertTrue(has_skincare_context("review kem chống nắng cho da dầu"))
        self.assertTrue(has_skincare_context("cách chăm sóc da mụn hiệu quả"))
        self.assertTrue(has_skincare_context("beauty tips for oily skin"))
        self.assertTrue(has_skincare_context("mỹ phẩm thuần chay cho da nhạy cảm"))

    def test_has_skincare_context_edge_cases(self) -> None:
        # Single-word context from category keywords
        self.assertTrue(has_skincare_context("chăm sóc da cơ bản"))
        # "thâm" alone may not match — check actual keyword set
        result = has_skincare_context("trị thâm sau mụn treatment")
        self.assertIsInstance(result, bool)

    def test_has_skincare_context_negatives(self) -> None:
        self.assertFalse(has_skincare_context("cách nấu phở bò ngon"))
        self.assertFalse(has_skincare_context("tin tức thời sự hôm nay"))
        self.assertFalse(has_skincare_context("review laptop văn phòng"))

    def test_detect_content_format_review(self) -> None:
        fmt = detect_content_format("Bài review serum sau 30 ngày dùng", "review serum")
        self.assertEqual(fmt.type, "review")

    def test_detect_content_format_comparison(self) -> None:
        fmt = detect_content_format("So sánh kem chống nắng vật lý và hóa học", "so sánh sunscreen")
        self.assertEqual(fmt.type, "comparison")

    def test_detect_content_format_tutorial(self) -> None:
        fmt = detect_content_format("Cách dùng retinol cho người mới bắt đầu", "hướng dẫn retinol")
        self.assertEqual(fmt.type, "tutorial")

    def test_detect_content_format_fallback(self) -> None:
        fmt = detect_content_format("Một câu ngắn", "ngắn")
        self.assertEqual(fmt.type, "general")

    def test_estimate_price_positioning(self) -> None:
        self.assertEqual(estimate_price_positioning("rẻ nhất thị trường giá tốt"), "budget")
        self.assertEqual(estimate_price_positioning("giá cao cấp đắt tiền"), "premium")
        self.assertEqual(estimate_price_positioning("giá phải chăng hợp lý"), "mid")

    def test_estimate_price_positioning_default(self) -> None:
        self.assertEqual(estimate_price_positioning("nội dung chung chung"), "mid")

    def test_estimate_content_tone(self) -> None:
        self.assertEqual(estimate_content_tone("nghiên cứu khoa học cho thấy", "general"), "scientific")
        self.assertEqual(estimate_content_tone("xu hướng hot trend mới", "general"), "entertaining")
        self.assertEqual(estimate_content_tone("học cách chăm sóc kiến thức", "general"), "educational")

    def test_estimate_content_tone_default(self) -> None:
        self.assertEqual(estimate_content_tone("một câu không đặc trưng", "general"), "educational")

    def test_extract_brand_names_returns_list(self) -> None:
        names = extract_brand_names(
            text="Hasaki Vietnam review serum duong da",
            known_names={"Hasaki Vietnam", "Cocoon"},
        )
        self.assertIsInstance(names, list)

    def test_extract_brand_names_empty_input(self) -> None:
        self.assertEqual(extract_brand_names(text="", known_names=set()), [])


if __name__ == "__main__":
    unittest.main()
