"""Tests cho CompetitorPageDiscoveryTool — MultiSourceSearchClient (web search) thay vì Facebook API."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fanpage_agent.tools.research.competitor_page_discovery import (
    CompetitorPageDiscoveryTool,
)


# ── Helpers ─────────────────────────────────────────────────────


def _make_search_result(
    title: str,
    snippet: str = "",
    url: str = "https://example.com",
    engine: str = "searxng",
    score: float = 0.8,
) -> object:
    """Tạo fake SearchResult duck-typing."""
    from types import SimpleNamespace

    return SimpleNamespace(
        title=title,
        snippet=snippet,
        url=url,
        engine=engine,
        score=score,
    )


# ── CompetitorPageDiscoveryTool tests ────────────────────


class CompetitorPageDiscoveryToolTest(unittest.TestCase):
    """Unit tests for CompetitorPageDiscoveryTool (web search backend)."""

    def test_init_defaults(self) -> None:
        """Khởi tạo không cần param — tự tạo MultiSourceSearchClient."""
        service = CompetitorPageDiscoveryTool()
        self.assertIsNotNone(service._web_search)

    def test_discover_with_empty_names(self) -> None:
        """Không có tên đối thủ → trả về empty."""
        service = CompetitorPageDiscoveryTool(web_search=MagicMock())
        offers, pages = service.discover(competitor_names=[])
        self.assertEqual(offers, [])
        self.assertEqual(pages, [])

    def test_discover_extracts_products_from_web_search(self) -> None:
        """Phát hiện sản phẩm từ kết quả web search về đối thủ."""
        mock_search = MagicMock()
        mock_search.search_multiple.return_value = [
            _make_search_result(
                title="Review serum retinol cho người mới bắt đầu - giá tốt nhất thị trường!",
                snippet="Serum retinol là lựa chọn tuyệt vời cho người mới tập skincare",
            ),
        ]

        service = CompetitorPageDiscoveryTool(web_search=mock_search)
        offers, pages = service.discover(
            competitor_names=["Hasaki"],
        )

        # Should detect "retinol" and/or "serum" as product markers
        self.assertGreater(len(offers), 0)
        offer_names = {o.product_name.lower() for o in offers}
        self.assertTrue(
            "Retinol" in offer_names
            or "retinol" in offer_names
            or "Serum" in offer_names
            or "serum" in offer_names
        )
        # All discovered offers should have competitor_page_discovery reason code
        for o in offers:
            self.assertIn("competitor_page_discovery", o.reason_codes)

        # Verify search query was built from competitor name
        called_queries = mock_search.search_multiple.call_args[1].get(
            "queries", []
        )
        self.assertTrue(
            any("hasaki" in q.lower() for q in called_queries)
        )

    def test_discover_handles_no_results(self) -> None:
        """Không có kết quả search → trả về empty."""
        mock_search = MagicMock()
        mock_search.search_multiple.return_value = []

        service = CompetitorPageDiscoveryTool(web_search=mock_search)
        offers, pages = service.discover(
            competitor_names=["Some Unknown Brand"],
        )
        self.assertEqual(offers, [])
        self.assertEqual(pages, [])

    def test_discover_handles_search_failure_gracefully(self) -> None:
        """Lỗi search từ một đối thủ không làm hỏng toàn bộ."""
        mock_search = MagicMock()

        call_count = [0]

        def side_effect(queries, **kwargs) -> list:
            call_count[0] += 1
            if call_count[0] <= 1:  # first competitor fails
                raise RuntimeError("Search timeout")
            return [
                _make_search_result(
                    title="Review kem chống nắng giá rẻ",
                    snippet="Kem chống nắng tốt cho da dầu",
                ),
            ]

        mock_search.search_multiple.side_effect = side_effect

        service = CompetitorPageDiscoveryTool(web_search=mock_search)
        offers, pages = service.discover(
            competitor_names=["Failing", "Working"],
        )
        # Should still get products from "Working"
        self.assertGreater(len(offers), 0)
        self.assertTrue(
            any("kem chống nắng" in o.topic.lower() for o in offers)
        )

    def test_deduplicate_existing_offers(self) -> None:
        """Không tạo offer candidate trùng với existing_offers."""
        mock_search = MagicMock()
        mock_search.search_multiple.return_value = [
            _make_search_result(
                title="Review kem chống nắng Anessa 2026",
                snippet="Kem chống nắng nào tốt nhất? So sánh",
            ),
        ]

        service = CompetitorPageDiscoveryTool(web_search=mock_search)
        offers, pages = service.discover(
            competitor_names=["Hasaki"],
            existing_offers=["Kem chống nắng"],
        )
        # "Kem chống nắng" in existing → candidates should NOT include it
        for o in offers:
            self.assertNotIn(
                "kem chống nắng", o.product_name.lower()
            )

    def test_discover_respects_max_offers(self) -> None:
        """Tôn trọng max_discovered_offers giới hạn."""
        mock_search = MagicMock()
        mock_search.search_multiple.return_value = [
            _make_search_result(
                title="Review retinol + serum vitamin C + niacinamide + hyaluronic acid tốt nhất!",
                snippet="Đánh giá chi tiết các sản phẩm",
            ),
        ]

        service = CompetitorPageDiscoveryTool(web_search=mock_search)
        offers, pages = service.discover(
            competitor_names=["Hasaki"],
            max_discovered_offers=2,
        )
        self.assertLessEqual(len(offers), 2)

    # ------------------------------------------------------------------
    # _extract_mentions static method (giữ nguyên logic cũ)
    # ------------------------------------------------------------------

    def test_extract_mentions_empty_text(self) -> None:
        result = CompetitorPageDiscoveryTool._extract_mentions("")
        self.assertEqual(result, [])

    def test_extract_mentions_no_mentions(self) -> None:
        result = CompetitorPageDiscoveryTool._extract_mentions(
            "Bài viết thông thường không mention ai"
        )
        self.assertEqual(result, [])

    def test_extract_mentions_multiple(self) -> None:
        result = CompetitorPageDiscoveryTool._extract_mentions(
            "Sản phẩm từ @[111:1:Brand A] và @[222:3:Brand B] rất tốt"
        )
        self.assertEqual(len(result), 2)
        self.assertIn(("111", "Brand A"), result)
        self.assertIn(("222", "Brand B"), result)

    # ------------------------------------------------------------------
    # _detect_angle static method
    # ------------------------------------------------------------------

    def test_detect_angle_comparison(self) -> None:
        angle = CompetitorPageDiscoveryTool._detect_angle(
            "so sánh hai sản phẩm", 2
        )
        self.assertEqual(angle, "comparison")

    def test_detect_angle_buying_guide(self) -> None:
        angle = CompetitorPageDiscoveryTool._detect_angle(
            "top sản phẩm tốt nhất", 2
        )
        self.assertEqual(angle, "buying_guide")

    def test_detect_angle_review(self) -> None:
        angle = CompetitorPageDiscoveryTool._detect_angle(
            "trải nghiệm thực tế sản phẩm", 4
        )
        self.assertEqual(angle, "review")

    def test_detect_angle_education_fallback(self) -> None:
        angle = CompetitorPageDiscoveryTool._detect_angle(
            "công dụng của retinol", 0
        )
        self.assertEqual(angle, "education")

    # ------------------------------------------------------------------
    # _estimate_customer_value static method
    # ------------------------------------------------------------------

    def test_estimate_customer_value_base(self) -> None:
        val = CompetitorPageDiscoveryTool._estimate_customer_value(
            "thông tin cơ bản", 0
        )
        self.assertEqual(val, 0.4)

    def test_estimate_customer_value_with_review(self) -> None:
        val = CompetitorPageDiscoveryTool._estimate_customer_value(
            "review đánh giá sản phẩm kem chống nắng", 3
        )
        self.assertGreater(val, 0.5)

    def test_estimate_customer_value_capped(self) -> None:
        val = CompetitorPageDiscoveryTool._estimate_customer_value(
            "review đánh giá trải nghiệm mẹo tip cách chọn "
            "giá rẻ deal coupon sản phẩm tốt nhất",
            5,
        )
        self.assertLessEqual(val, 1.0)

    # ------------------------------------------------------------------
    # _scan_text — edge cases (giữ nguyên logic cũ)
    # ------------------------------------------------------------------

    def test_scan_text_empty(self) -> None:
        result = CompetitorPageDiscoveryTool()._scan_text("", "test")
        self.assertEqual(result, [])

    def test_scan_text_no_product_markers(self) -> None:
        """Không có NICHE_PRODUCT_MARKERS → không có candidate."""
        result = CompetitorPageDiscoveryTool()._scan_text(
            "Thời tiết hôm nay đẹp quá!", "test"
        )
        self.assertEqual(result, [])

    def test_scan_text_source_name_in_reason_codes(self) -> None:
        """Mỗi candidate có web_source trong reason_codes để trace."""
        result = CompetitorPageDiscoveryTool()._scan_text(
            "Review kem chống nắng tốt nhất!",
            "web_search:hasaki",
        )
        self.assertGreater(len(result), 0)
        self.assertTrue(
            any(
                "web_source:web_search:hasaki" in c.reason_codes
                for c in result
            )
        )


if __name__ == "__main__":
    unittest.main()
