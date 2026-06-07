"""Tests cho CompetitorPageDiscoveryService + FacebookClient cross-page API."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.config import Settings
from fanpage_agent.services.competitor_page_discovery import (
    CompetitorPageDiscoveryService,
)

# ── Helpers ─────────────────────────────────────────────────────


def _fake_post(
    post_id: str,
    message: str,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
) -> dict:
    return {
        "id": post_id,
        "message": message,
        "created_time": "2026-01-01T00:00:00+0000",
        "permalink_url": f"https://fb.com/{post_id}",
        "likes": {"summary": {"total_count": likes}},
        "comments": {"summary": {"total_count": comments}},
        "shares": {"count": shares} if shares else {},
    }


class FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


# ── FacebookClient cross-page API tests ─────────────────────────


class FacebookClientCrossPageTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.settings = Settings.from_env(
            env={
                "FB_PAGE_ID": "our_page",
                "FB_PAGE_TOKEN": "test-page-token",
                "FB_API_VERSION": "v21.0",
            },
            root_dir=root,
            load_dotenv=False,
        )

    # ------------------------------------------------------------------
    # get_public_page_info
    # ------------------------------------------------------------------

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_get_public_page_info_returns_basic_fields(
        self, mock_urlopen
    ) -> None:
        mock_urlopen.return_value = FakeHttpResponse({
            "id": "987654321",
            "name": "Skincare Vietnam",
            "category": "Health/Beauty",
            "description": "Chia sẻ bí quyết skincare",
            "link": "https://fb.com/skincarevn",
            "fan_count": 125000,
        })
        client = FacebookClient(self.settings)
        result = client.get_public_page_info("987654321")

        self.assertEqual(result["name"], "Skincare Vietnam")
        self.assertEqual(result["category"], "Health/Beauty")
        self.assertEqual(result["fan_count"], 125000)

        # Verify correct endpoint
        req = mock_urlopen.call_args[0][0]
        parts = req.full_url.split("?")[0]
        self.assertIn("/v21.0/987654321", parts)

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_get_public_page_info_minimal_response(
        self, mock_urlopen
    ) -> None:
        mock_urlopen.return_value = FakeHttpResponse({
            "id": "11111",
            "name": "Minimal Page",
        })
        client = FacebookClient(self.settings)
        result = client.get_public_page_info("11111")
        self.assertEqual(result["name"], "Minimal Page")
        self.assertNotIn("category", result)

    # ------------------------------------------------------------------
    # get_public_page_posts
    # ------------------------------------------------------------------

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_get_public_page_posts_empty_page(
        self, mock_urlopen
    ) -> None:
        mock_urlopen.return_value = FakeHttpResponse({"data": []})
        client = FacebookClient(self.settings)
        results = client.get_public_page_posts("competitor_1")
        self.assertEqual(results, [])

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_get_public_page_posts_returns_parsed_insights(
        self, mock_urlopen
    ) -> None:
        mock_urlopen.return_value = FakeHttpResponse({
            "data": [
                _fake_post(
                    "c1_post_1", "Review kem chống nắng mới",
                    likes=20, comments=5, shares=2,
                ),
                _fake_post(
                    "c1_post_2", "Serum vitamin C giá tốt",
                    likes=10, comments=1,
                ),
            ],
        })
        client = FacebookClient(self.settings)
        results = client.get_public_page_posts("competitor_2", limit=10)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], "c1_post_1")
        self.assertEqual(results[0]["engagements"], 27)  # 20 + 5 + 2
        self.assertEqual(results[1]["id"], "c1_post_2")
        self.assertEqual(results[1]["engagements"], 11)  # 10 + 1 + 0

        # Verify access_token in URL
        req = mock_urlopen.call_args[0][0]
        self.assertIn("access_token=test-page-token", req.full_url)


# ── CompetitorPageDiscoveryService tests ────────────────────


class CompetitorPageDiscoveryServiceTest(unittest.TestCase):
    """Unit tests for CompetitorPageDiscoveryService."""

    def test_init_no_fb_client(self) -> None:
        """Không có fb_client → discover trả về empty list."""
        service = CompetitorPageDiscoveryService()
        offers, pages = service.discover(
            competitor_page_ids=["123", "456"]
        )
        self.assertEqual(offers, [])
        self.assertEqual(pages, [])

    def test_discover_with_empty_page_list(self) -> None:
        """Không có competitor pages → trả về empty."""
        fb_client = MagicMock()
        service = CompetitorPageDiscoveryService(fb_client=fb_client)
        offers, pages = service.discover(competitor_page_ids=[])
        self.assertEqual(offers, [])
        self.assertEqual(pages, [])
        fb_client.get_public_page_posts.assert_not_called()

    def test_discover_extracts_products_from_posts(self) -> None:
        """Phát hiện sản phẩm từ post của competitor page."""
        fb_client = MagicMock()
        fb_client.get_public_page_posts.return_value = [
            _fake_post(
                "p1",
                "Review serum retinol cho người mới bắt đầu - "
                "giá tốt nhất thị trường!",
            ),
        ]
        service = CompetitorPageDiscoveryService(fb_client=fb_client)
        offers, pages = service.discover(
            competitor_page_ids=["comp_1"],
            max_posts_per_page=10,
        )

        # Should detect "retinol" and "serum" as product markers
        self.assertGreater(len(offers), 0)
        offer_names = {o.product_name.lower() for o in offers}
        self.assertTrue(
            "Retinol" in offer_names or "retinol" in offer_names
            or "Serum" in offer_names or "serum" in offer_names
        )
        # All discovered offers should have competitor_page_discovery reason code
        for o in offers:
            self.assertIn("competitor_page_discovery", o.reason_codes)

    def test_discover_mentions_extracts_new_pages(self) -> None:
        """Trích xuất page mention @[page_id:1:Name] từ post."""
        fb_client = MagicMock()
        fb_client.get_public_page_posts.return_value = [
            _fake_post(
                "p1",
                "Sản phẩm này hợp tác với @[555:1:Some Brand] "
                "và được @[666:1:Another Co] review rất kỹ.",
            ),
        ]
        service = CompetitorPageDiscoveryService(fb_client=fb_client)
        offers, pages = service.discover(
            competitor_page_ids=["comp_1"],
            max_posts_per_page=10,
        )
        self.assertEqual(len(pages), 2)
        self.assertIn("555", pages)
        self.assertIn("666", pages)

    def test_discover_deduplicates_new_pages(self) -> None:
        """Không thêm page mention đã có trong competitor_page_ids."""
        fb_client = MagicMock()
        fb_client.get_public_page_posts.return_value = [
            _fake_post(
                "p1",
                "@[comp_1:1:Existing Page] @[555:1:New Brand]",
            ),
        ]
        service = CompetitorPageDiscoveryService(fb_client=fb_client)
        offers, pages = service.discover(
            competitor_page_ids=["comp_1"],
            max_posts_per_page=10,
        )
        # "comp_1" already in seed → should not appear in new pages
        self.assertNotIn("comp_1", pages)
        self.assertEqual(pages, ["555"])

    def test_discover_handles_api_failure_gracefully(self) -> None:
        """Lỗi API từ một page không làm hỏng toàn bộ discovery."""
        fb_client = MagicMock()

        def side_effect(page_id: str, limit: int) -> list[dict]:
            if page_id == "failing":
                raise RuntimeError("API rate limit")
            return [
                _fake_post("ok", "Review kem chống nắng giá rẻ")
            ]

        fb_client.get_public_page_posts.side_effect = side_effect
        service = CompetitorPageDiscoveryService(fb_client=fb_client)
        offers, pages = service.discover(
            competitor_page_ids=["failing", "working"],
            max_posts_per_page=10,
        )
        # Should still get products from "working" page
        self.assertGreater(len(offers), 0)
        self.assertTrue(
            any("kem chống nắng" in o.topic.lower() for o in offers)
        )

    def test_deduplicate_existing_offers(self) -> None:
        """Không tạo offer candidate trùng với existing_offers."""
        fb_client = MagicMock()
        fb_client.get_public_page_posts.return_value = [
            _fake_post("p1", "Review kem chống nắng Anessa 2026"),
            _fake_post("p2", "Kem chống nắng nào tốt nhất? So sánh"),
        ]
        service = CompetitorPageDiscoveryService(fb_client=fb_client)
        offers, pages = service.discover(
            competitor_page_ids=["comp_1"],
            existing_offers=["Kem chống nắng"],
            max_posts_per_page=10,
        )
        # "Kem chống nắng" in existing → candidates should NOT include it
        # (but may still detect other markers like "retinol" which aren't here)
        for o in offers:
            self.assertNotIn(
                "kem chống nắng", o.product_name.lower()
            )

    def test_discover_respects_max_offers(self) -> None:
        """Tôn trọng max_discovered_offers giới hạn."""
        fb_client = MagicMock()
        fb_client.get_public_page_posts.return_value = [
            _fake_post(
                "p1",
                "Review retinol + serum vitamin C + niacinamide + "
                "hyaluronic acid tốt nhất!",
            ),
        ]
        service = CompetitorPageDiscoveryService(fb_client=fb_client)
        offers, pages = service.discover(
            competitor_page_ids=["comp_1"],
            max_discovered_offers=2,
            max_posts_per_page=10,
        )
        self.assertLessEqual(len(offers), 2)

    # ------------------------------------------------------------------
    # _extract_mentions static method
    # ------------------------------------------------------------------

    def test_extract_mentions_empty_text(self) -> None:
        result = CompetitorPageDiscoveryService._extract_mentions("")
        self.assertEqual(result, [])

    def test_extract_mentions_no_mentions(self) -> None:
        result = CompetitorPageDiscoveryService._extract_mentions(
            "Bài viết thông thường không mention ai"
        )
        self.assertEqual(result, [])

    def test_extract_mentions_multiple(self) -> None:
        result = CompetitorPageDiscoveryService._extract_mentions(
            "Sản phẩm từ @[111:1:Brand A] và @[222:3:Brand B] rất tốt"
        )
        self.assertEqual(len(result), 2)
        self.assertIn(("111", "Brand A"), result)
        self.assertIn(("222", "Brand B"), result)

    # ------------------------------------------------------------------
    # _detect_angle static method
    # ------------------------------------------------------------------

    def test_detect_angle_comparison(self) -> None:
        angle = CompetitorPageDiscoveryService._detect_angle(
            "so sánh hai sản phẩm", 2
        )
        self.assertEqual(angle, "comparison")

    def test_detect_angle_buying_guide(self) -> None:
        angle = CompetitorPageDiscoveryService._detect_angle(
            "top sản phẩm tốt nhất", 2
        )
        self.assertEqual(angle, "buying_guide")

    def test_detect_angle_review(self) -> None:
        angle = CompetitorPageDiscoveryService._detect_angle(
            "trải nghiệm thực tế sản phẩm", 4
        )
        self.assertEqual(angle, "review")

    def test_detect_angle_education_fallback(self) -> None:
        angle = CompetitorPageDiscoveryService._detect_angle(
            "công dụng của retinol", 0
        )
        self.assertEqual(angle, "education")

    # ------------------------------------------------------------------
    # _estimate_customer_value static method
    # ------------------------------------------------------------------

    def test_estimate_customer_value_base(self) -> None:
        val = CompetitorPageDiscoveryService._estimate_customer_value(
            "thông tin cơ bản", 0
        )
        self.assertEqual(val, 0.4)

    def test_estimate_customer_value_with_review(self) -> None:
        val = CompetitorPageDiscoveryService._estimate_customer_value(
            "review đánh giá sản phẩm kem chống nắng", 3
        )
        self.assertGreater(val, 0.5)

    def test_estimate_customer_value_capped(self) -> None:
        val = CompetitorPageDiscoveryService._estimate_customer_value(
            "review đánh giá trải nghiệm mẹo tip cách chọn "
            "giá rẻ deal coupon sản phẩm tốt nhất",
            5,
        )
        self.assertLessEqual(val, 1.0)

    # ------------------------------------------------------------------
    # _scan_text — edge cases
    # ------------------------------------------------------------------

    def test_scan_text_empty(self) -> None:
        result = CompetitorPageDiscoveryService(
            fb_client=None
        )._scan_text("", "test")
        self.assertEqual(result, [])

    def test_scan_text_no_product_markers(self) -> None:
        """Không có NICHE_PRODUCT_MARKERS → không có candidate."""
        result = CompetitorPageDiscoveryService(
            fb_client=None
        )._scan_text(
            "Thời tiết hôm nay đẹp quá!", "test"
        )
        self.assertEqual(result, [])

    def test_scan_text_source_name_in_reason_codes(self) -> None:
        """Mỗi candidate có fb_source trong reason_codes để trace."""
        result = CompetitorPageDiscoveryService(
            fb_client=None
        )._scan_text(
            "Review kem chống nắng tốt nhất!", "fb_competitor:comp_123"
        )
        self.assertGreater(len(result), 0)
        self.assertTrue(
            any(
                "fb_source:fb_competitor:comp_123" in c.reason_codes
                for c in result
            )
        )


if __name__ == "__main__":
    unittest.main()
