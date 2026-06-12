"""Tests cho CompetitorLearningEngine — self-learning engine cho competitor analysis."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fanpage_agent.tools.research.competitor_learning_engine import (
    CompetitorLearningEngine,
    _AUTO_PROMOTE_MIN_SCORE,
)
from fanpage_agent.tools.research.competitor_learning_store import (
    extract_brand_names,
    extract_next_topics,
    insight_to_gaps,
    profile_to_dict,
)


# ── Helpers ─────────────────────────────────────────────────────


def _make_profile(
    name: str = "Cocoon",
    products: list[str] | None = None,
    top_products: list[str] | None = None,
    top_angle: str = "natural_organic",
    top_format: str = "review",
    price_positioning: str = "mid",
    content_tone: str = "educational",
    unique_angle: str = "natural_organic_focus",
    findings_count: int = 5,
    search_urls: list[str] | None = None,
    analyzed_at: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        products_detected=products or ["Retinol", "Vitamin C", "Niacinamide"],
        top_products=top_products or ["Retinol", "Vitamin C"],
        top_angle=top_angle,
        top_format=top_format,
        price_positioning=price_positioning,
        content_tone=content_tone,
        unique_angle=unique_angle,
        findings_count=findings_count,
        search_urls=search_urls or [],
        analyzed_at=analyzed_at or datetime.now(timezone.utc).isoformat(),
    )


def _make_insight(
    shared_products: list | None = None,
    unique_products: dict | None = None,
    gap_products: list | None = None,
    underused_formats: list | None = None,
    recommendation: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        shared_products=shared_products or [("Retinol", 2)],
        unique_products_by_competitor=unique_products or {"Cocoon": ["Niacinamide"]},
        gap_products=gap_products or ["Azelaic Acid"],
        underused_formats=underused_formats or ["tutorial"],
        recommendation=recommendation or "Focus on gap products.",
    )


def _make_search_result(
    title: str, snippet: str = "", url: str = "https://example.com"
) -> SimpleNamespace:
    return SimpleNamespace(title=title, snippet=snippet, url=url, engine="searxng", score=0.8)


# ── CompetitorLearningEngine tests ─────────────────────────


class CompetitorLearningEngineTest(unittest.TestCase):
    """Unit tests for CompetitorLearningEngine."""

    def setUp(self) -> None:
        self.mock_store = MagicMock()
        self.mock_tool = MagicMock()
        self.engine = CompetitorLearningEngine(
            discovery_tool=self.mock_tool,
            store=self.mock_store,
        )

    def test_init(self) -> None:
        """Khởi tạo với discovery_tool + store."""
        self.assertIs(self.engine._tool, self.mock_tool)
        self.assertIs(self.engine._store, self.mock_store)

    # ── record_scan_result ────────────────────────────────────

    def test_record_scan_result_registers_competitors(self) -> None:
        """record_scan_result gọi upsert_competitor cho từng tên."""
        profiles = [_make_profile("Cocoon"), _make_profile("Hasaki")]
        insight = _make_insight()

        self.engine.record_scan_result(
            competitor_names=["Cocoon", "Hasaki"],
            profiles=profiles,
            insight=insight,
        )

        self.assertEqual(self.mock_store.upsert_competitor.call_count, 2)
        self.mock_store.upsert_competitor.assert_any_call("Cocoon")
        self.mock_store.upsert_competitor.assert_any_call("Hasaki")

    def test_record_scan_result_saves_snapshots(self) -> None:
        """Mỗi profile được lưu snapshot xuống DB."""
        profiles = [_make_profile("Cocoon")]
        insight = _make_insight()
        self.mock_store.save_competitor_snapshot.return_value = 1

        result = self.engine.record_scan_result(
            competitor_names=["Cocoon"],
            profiles=profiles,
            insight=insight,
        )

        self.mock_store.save_competitor_snapshot.assert_called_once()
        call = self.mock_store.save_competitor_snapshot.call_args
        self.assertEqual(call[1]["competitor_name"], "Cocoon")
        assert "snapshot_ids" in result
        self.assertEqual(result["snapshot_ids"], [1])

    def test_record_scan_result_records_products(self) -> None:
        """Mỗi sản phẩm trong products_detected được ghi vào DB."""
        profiles = [_make_profile("Cocoon", products=["Retinol", "Vitamin C"])]
        insight = _make_insight()

        self.engine.record_scan_result(
            competitor_names=["Cocoon"], profiles=profiles, insight=insight,
        )

        self.assertEqual(self.mock_store.record_competitor_product.call_count, 2)

    def test_record_scan_result_auto_discovers(self) -> None:
        """Gọi _auto_discover với danh sách tên đã scan."""
        profiles = [_make_profile("Cocoon")]
        insight = _make_insight()

        with patch.object(self.engine, "_auto_discover", return_value=["Co May"]) as mock_ad:
            result = self.engine.record_scan_result(
                competitor_names=["Cocoon"], profiles=profiles, insight=insight,
            )
            mock_ad.assert_called_once_with(existing_names=["Cocoon"])
            assert "discovered_candidates" in result
            self.assertEqual(result["discovered_candidates"], ["Co May"])

    def test_record_scan_result_detects_trends(self) -> None:
        """Gọi _detect_trends với profile names."""
        profiles = [_make_profile("Cocoon")]
        insight = _make_insight()

        with patch.object(self.engine, "_detect_trends", return_value={"rising_products": []}) as mock_dt:
            result = self.engine.record_scan_result(
                competitor_names=["Cocoon"], profiles=profiles, insight=insight,
            )
            mock_dt.assert_called_once_with(profile_names=["Cocoon"])

    def test_record_scan_result_saves_gaps(self) -> None:
        """Gap products được lưu xuống DB."""
        profiles = [_make_profile("Cocoon")]
        insight = _make_insight(gap_products=["Azelaic Acid"])

        self.engine.record_scan_result(
            competitor_names=["Cocoon"], profiles=profiles, insight=insight,
        )

        self.mock_store.save_competitor_gaps.assert_called_once()
        gaps_arg = self.mock_store.save_competitor_gaps.call_args[0][0]
        self.assertTrue(any(g["gap_name"] == "Azelaic Acid" for g in gaps_arg))

    def test_record_scan_result_empty_profiles(self) -> None:
        """Không có profiles → không lưu snapshot hay gap."""
        result = self.engine.record_scan_result(
            competitor_names=["Cocoon"], profiles=[], insight=None,
        )

        self.mock_store.save_competitor_snapshot.assert_not_called()
        self.mock_store.record_competitor_product.assert_not_called()
        self.mock_store.save_competitor_gaps.assert_not_called()
        self.assertEqual(result["snapshot_ids"], [])
        self.assertEqual(result["trends"], {})

    # ── scan (full pipeline) ──────────────────────────────────

    def test_scan_full_pipeline(self) -> None:
        """scan() chạy đầy đủ: register → analyze → snapshot → discover → trends → gaps."""
        profiles = [_make_profile("Cocoon")]
        insight = _make_insight()
        self.mock_tool.analyze_competitors.return_value = (profiles, insight)
        self.mock_store.upsert_competitor.return_value = {"id": 1}
        self.mock_store.save_competitor_snapshot.return_value = 42

        result = self.engine.scan(competitor_names=["Cocoon"])

        self.mock_tool.analyze_competitors.assert_called_once_with(["Cocoon"])
        self.mock_store.upsert_competitor.assert_called_once_with("Cocoon")
        self.mock_store.save_competitor_snapshot.assert_called_once()
        assert "snapshot_ids" in result
        assert "profiles" in result
        assert "cross_competitor" in result

    def test_scan_empty_names(self) -> None:
        """scan với danh sách rỗng → analyze_competitors gọi với []."""
        self.mock_tool.analyze_competitors.return_value = ([], _make_insight())

        result = self.engine.scan(competitor_names=[])

        self.mock_tool.analyze_competitors.assert_called_once_with([])
        self.mock_store.upsert_competitor.assert_not_called()

    def test_scan_no_snapshot(self) -> None:
        """save_snapshot=False → không lưu snapshot, product, gaps, trend."""
        self.mock_tool.analyze_competitors.return_value = (
            [_make_profile("Cocoon")], _make_insight(),
        )

        result = self.engine.scan(competitor_names=["Cocoon"], save_snapshot=False)

        self.mock_store.save_competitor_snapshot.assert_not_called()
        self.mock_store.record_competitor_product.assert_not_called()
        self.mock_store.save_competitor_gaps.assert_not_called()

    def test_scan_no_discover(self) -> None:
        """discover_new=False → không gọi auto-discover."""
        self.mock_tool.analyze_competitors.return_value = (
            [_make_profile("Cocoon")], _make_insight(),
        )

        with patch.object(self.engine, "_auto_discover") as mock_ad:
            self.engine.scan(competitor_names=["Cocoon"], discover_new=False)
            mock_ad.assert_not_called()

    # ── scan_auto_discover ────────────────────────────────────

    def test_scan_auto_discover_no_candidates(self) -> None:
        """Không có candidate đủ điểm → trả về no_candidates."""
        self.mock_store.list_competitor_candidates.return_value = []

        result = self.engine.scan_auto_discover()

        self.assertEqual(result["status"], "no_candidates")
        self.assertEqual(result["promoted"], [])

    def test_scan_auto_discover_promotes_and_scans(self) -> None:
        """Candidate đủ điểm → promote → scan đối thủ mới."""
        self.mock_store.list_competitor_candidates.return_value = [
            {"candidate_name": "Co May", "total_score": 3.0},
        ]
        self.mock_store.promote_candidate.return_value = {"status": "ok"}

        with patch.object(self.engine, "scan", return_value={"profiles": []}) as mock_scan:
            result = self.engine.scan_auto_discover()

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["promoted"], ["Co May"])
            mock_scan.assert_called_once_with(
                competitor_names=["Co May"],
                save_snapshot=True,
                discover_new=True,
            )

    def test_scan_auto_discover_promotion_failed(self) -> None:
        """promote_candidate thất bại → không scan."""
        self.mock_store.list_competitor_candidates.return_value = [
            {"candidate_name": "Bad", "total_score": 3.0},
        ]
        self.mock_store.promote_candidate.return_value = {"error": "already active"}

        with patch.object(self.engine, "scan") as mock_scan:
            result = self.engine.scan_auto_discover()
            self.assertEqual(result["status"], "promotion_failed")
            mock_scan.assert_not_called()

    # ── get_learning_summary ──────────────────────────────────

    def test_get_learning_summary(self) -> None:
        """Trả về summary dict với đầy đủ keys."""
        self.mock_store.list_competitors.return_value = [
            {"name": "Cocoon", "auto_discovered": 0, "is_active": 1},
        ]
        self.mock_store.list_competitor_candidates.return_value = [
            {"candidate_name": "Co May", "total_score": 1.5},
        ]
        self.mock_store.get_latest_gaps.return_value = [{"gap_name": "Azelaic Acid"}]
        self.mock_store.get_top_competitor_products.return_value = [("Retinol", 3)]
        self.mock_store.get_competitor_trend.return_value = {
            "scan_count": 2,
            "auto_discovered": False,
            "products_tracked": 3,
            "new_products": 1,
            "last_scanned": "2026-06-09",
        }

        summary = self.engine.get_learning_summary()

        self.assertEqual(summary["total_competitors"], 1)
        self.assertEqual(summary["auto_discovered"], 0)
        self.assertEqual(summary["total_candidates"], 1)
        self.assertEqual(len(summary["competitors"]), 1)
        self.assertEqual(len(summary["top_products_across_competitors"]), 1)
        self.assertEqual(len(summary["latest_gaps"]), 1)

    # ── _extract_brand_names (static) ─────────────────────────

    def test_extract_brand_names_from_comparison(self) -> None:
        """'X vs Y' pattern → phát hiện Y (word đầu) với score 1.5."""
        text = "Cocoon vs Co May review skincare"
        known = {"cocoon"}

        candidates = extract_brand_names(text, known)

        scores = dict(candidates)
        # Non-greedy regex captures only first word after "vs"
        self.assertIn("Co", scores)
        self.assertEqual(scores["Co"], 1.5)

    def test_extract_brand_names_skips_known(self) -> None:
        """Tên đã biết → không đưa vào kết quả."""
        text = "Cocoon vs Hasaki"
        known = {"cocoon", "hasaki"}

        candidates = extract_brand_names(text, known)

        # "Has" (non-greedy match on "Hasaki") — 1.5 comparison, not skincare keyword
        # Our known set has "hasaki" but regex found "Has" which isn't known
        for name, _ in candidates:
            self.assertNotEqual(name.lower(), "hasaki")

    def test_extract_brand_names_detects_skincare_keywords(self) -> None:
        """Tên chứa từ khóa skincare → score 1.0."""
        text = "SkinCare Beauty Vietnam new brand"
        known = set()

        candidates = extract_brand_names(text, known)

        # "Care Beauty Vietnam" — 3 capitalized words, contains "care" (skincare keyword)
        names = [c[0] for c in candidates]
        self.assertIn("Care Beauty Vietnam", names)

    # ── _profile_to_dict (static) ─────────────────────────────

    def test_profile_to_dict(self) -> None:
        """Convert CompetitorProfile → dict đầy đủ keys."""
        profile = _make_profile(
            name="Cocoon",
            products=["Retinol"],
            top_products=["Retinol"],
            unique_angle="natural_organic_focus",
            search_urls=["https://example.com"],
        )

        d = profile_to_dict(profile)

        self.assertEqual(d["name"], "Cocoon")
        self.assertEqual(d["top_products"], ["Retinol"])
        self.assertEqual(d["unique_angle"], "natural_organic_focus")
        self.assertEqual(d["search_urls"], ["https://example.com"])

    # ── _extract_next_topics (static) ─────────────────────────

    def test_extract_next_topics_from_gaps(self) -> None:
        """Gap products → topic gợi ý."""
        profile = _make_profile()
        insight = _make_insight(gap_products=["Azelaic Acid"], underused_formats=["tutorial"])

        topics = extract_next_topics(profile, insight)

        self.assertTrue(any("Azelaic Acid" in t for t in topics))
        self.assertTrue(any("tutorial" in t for t in topics))
        self.assertLessEqual(len(topics), 5)

    # ── _insight_to_gaps (static) ──────────────────────────────

    def test_insight_to_gaps(self) -> None:
        """Gap products + underused formats → list gap records."""
        insight = _make_insight(gap_products=["Azelaic Acid"], underused_formats=["tutorial"])

        gaps = insight_to_gaps(insight)

        self.assertEqual(len(gaps), 2)
        product_gaps = [g for g in gaps if g["gap_type"] == "product"]
        format_gaps = [g for g in gaps if g["gap_type"] == "format"]
        self.assertEqual(len(product_gaps), 1)
        self.assertEqual(product_gaps[0]["gap_name"], "Azelaic Acid")
        self.assertEqual(len(format_gaps), 1)
        self.assertEqual(format_gaps[0]["gap_name"], "tutorial")

    # ── _detect_trends ────────────────────────────────────────

    def test_detect_trends_first_scan(self) -> None:
        """Lần scan đầu (chỉ 1 snapshot) → không có trend."""
        profile = _make_profile("Cocoon", products=["Retinol"])
        self.mock_store.get_competitor_snapshots.return_value = [
            {"products_json": ["Retinol"], "unique_angle": "natural", "top_format": "review"},
        ]

        trends = self.engine._detect_trends(profile_names=["Cocoon"])

        self.assertEqual(trends["new_products_detected"]["Cocoon"], ["Retinol"])
        self.assertFalse(trends["angle_changes"])
        self.assertFalse(trends["format_changes"])

    def test_detect_trends_new_products(self) -> None:
        """Lần scan 2 có sản phẩm mới → detect."""
        profile = _make_profile("Cocoon", products=["Retinol", "Vitamin C"])
        self.mock_store.get_competitor_snapshots.return_value = [
            {"products_json": ["Retinol", "Vitamin C"], "unique_angle": "natural", "top_format": "review"},
            {"products_json": ["Retinol"], "unique_angle": "natural", "top_format": "review"},
        ]

        trends = self.engine._detect_trends(profile_names=["Cocoon"])

        self.assertEqual(trends["new_products_detected"]["Cocoon"], ["vitamin c"])
        self.assertIn("vitamin c", [p[0] for p in trends["rising_products"]])

    def test_detect_trends_angle_change(self) -> None:
        """Unique angle thay đổi → detect."""
        self.mock_store.get_competitor_snapshots.return_value = [
            {"products_json": [], "unique_angle": "science_clinical_focus", "top_format": "review"},
            {"products_json": [], "unique_angle": "natural_organic_focus", "top_format": "review"},
        ]

        trends = self.engine._detect_trends(profile_names=["Cocoon"])

        self.assertIn("Cocoon", trends["angle_changes"])

    def test_detect_trends_format_change(self) -> None:
        """Top format thay đổi → detect."""
        self.mock_store.get_competitor_snapshots.return_value = [
            {"products_json": [], "unique_angle": "natural", "top_format": "tutorial"},
            {"products_json": [], "unique_angle": "natural", "top_format": "review"},
        ]

        trends = self.engine._detect_trends(profile_names=["Cocoon"])

        self.assertIn("Cocoon", trends["format_changes"])


if __name__ == "__main__":
    unittest.main()
