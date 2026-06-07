"""Tests for the multi-affiliate provider system.

Covers:
  - AffiliateProduct model
  - AccessTradeProvider (with mock HTTP)
  - ShopeeProvider (with mock GraphQL)
  - AffiliateRegistry (search, dedup, conversion to ProductTopicCandidate)
  - Pipeline integration (build_brief with affiliate_registry)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from fanpage_agent.affiliate import (
    AccessTradeProvider,
    AffiliateProduct,
    AffiliateRegistry,
    AffiliateSettings,
    ShopeeProvider,
)
from fanpage_agent.affiliate.base import (
    SKINCARE_SEARCH_KEYWORDS,
    AffiliateNetwork,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. AffiliateProduct model
# ═══════════════════════════════════════════════════════════════════════════


class TestAffiliateProduct:
    def test_effective_price_uses_sale_price(self) -> None:
        p = AffiliateProduct(
            product_id="1",
            product_name="Kem chống nắng",
            network="accesstrade",
            price=200000,
            sale_price=150000,
        )
        assert p.effective_price == 150000

    def test_effective_price_falls_back_to_price(
        self,
    ) -> None:
        p = AffiliateProduct(
            product_id="2",
            product_name="Serum C",
            network="shopee",
            price=300000,
        )
        assert p.effective_price == 300000

    def test_effective_price_none_when_both_none(
        self,
    ) -> None:
        p = AffiliateProduct(
            product_id="3",
            product_name="Retinol",
            network="accesstrade",
        )
        assert p.effective_price is None

    def test_network_label_from_enum(self) -> None:
        p = AffiliateProduct(
            product_id="1",
            product_name="A",
            network=AffiliateNetwork.ACCESSTRADE.value,
        )
        assert p.network_label == "Accesstrade"

    def test_network_label_custom(self) -> None:
        p = AffiliateProduct(
            product_id="2",
            product_name="B",
            network="custom_network",
        )
        assert p.network_label == "Custom_Network"


# ═══════════════════════════════════════════════════════════════════════════
# 2. AccessTradeProvider
# ═══════════════════════════════════════════════════════════════════════════


class TestAccessTradeProvider:
    """Tests for AccessTradeProvider using the real /campaigns API format."""

    @pytest.fixture
    def config(self) -> AffiliateSettings:
        s = AffiliateSettings(enabled=True)
        s.access_trade.enabled = True
        s.access_trade.api_key = "test_key"
        return s

    def _mock_campaigns_response(self, campaigns: list[dict]) -> httpx.Response:
        """Create a mock httpx.Response with campaign JSON."""
        body = {"data": campaigns, "page": 1, "total_page": 1.0}
        return httpx.Response(
            200,
            text=json.dumps(body),
            request=httpx.Request("GET", "http://test/campaigns"),
        )

    def _mock_empty_response(self) -> httpx.Response:
        """Create a mock httpx.Response for an empty page (end of pagination)."""
        return httpx.Response(
            200,
            text=json.dumps({"data": [], "page": 2, "total_page": 1.0}),
            request=httpx.Request("GET", "http://test/campaigns"),
        )

    def test_is_configured_true(self, config) -> None:
        provider = AccessTradeProvider(config.access_trade)
        assert provider.is_configured() is True

    def test_is_configured_false(self) -> None:
        provider = AccessTradeProvider(
            AffiliateSettings().access_trade
        )
        assert provider.is_configured() is False

    @patch("httpx.Client.get")
    def test_search_products_parses_campaign_format(
        self, mock_get, config
    ) -> None:
        """Campaign with 12% max_com should parse to 0.12 commission."""
        camp = {
            "id": "6990399044122386089",
            "name": "Test Skincare - Serum Vitamin C",
            "category": "68",
            "sub_category": "32",
            "max_com": "12%",
            "merchant": "test_merchant",
            "url": "https://shop.example.com/serum",
            "logo": "https://img.example.com/logo.png",
            "type": "3",
            "approval": "unregistered",
            "status": "1",
            "scope": "",
            "start_time": None,
            "end_time": None,
        }
        mock_get.side_effect = [
            self._mock_campaigns_response([camp]),
            self._mock_empty_response(),
        ]

        provider = AccessTradeProvider(config.access_trade)
        results = provider.search_products("serum", max_results=5)

        assert len(results) == 1
        p = results[0]
        assert p.product_name == "Test Skincare - Serum Vitamin C"
        assert p.commission_rate == 0.12
        assert "12.0%" in p.commission_note
        assert p.network == "accesstrade"
        assert p.product_url == "https://shop.example.com/serum"
        assert p.image_url == "https://img.example.com/logo.png"
        assert p.metadata["merchant_name"] == "test_merchant"

    @patch("httpx.Client.get")
    def test_search_products_filters_by_keyword(
        self, mock_get, config
    ) -> None:
        """Only campaigns matching the keyword should be returned."""
        camps = [
            {
                "id": "1",
                "name": "Retinol Serum",
                "category": "68",
                "max_com": "10%",
                "merchant": "brand_a",
                "url": "",
            },
            {
                "id": "2",
                "name": "Kem chống nắng",
                "category": "68",
                "max_com": "5%",
                "merchant": "brand_b",
                "url": "",
            },
        ]
        mock_get.side_effect = [
            self._mock_campaigns_response(camps),
            self._mock_empty_response(),
        ]

        provider = AccessTradeProvider(config.access_trade)
        results = provider.search_products("retinol")

        assert len(results) == 1
        assert results[0].product_name == "Retinol Serum"

    @patch("httpx.Client.get")
    def test_search_products_empty_on_failure(
        self, mock_get, config
    ) -> None:
        mock_get.side_effect = Exception("API down")
        provider = AccessTradeProvider(config.access_trade)
        results = provider.search_products("retinol")
        assert results == []

    @patch("httpx.Client.get")
    def test_search_products_unconfigured_returns_empty(
        self, mock_get
    ) -> None:
        provider = AccessTradeProvider(
            AffiliateSettings().access_trade
        )
        results = provider.search_products("serum")
        assert results == []
        mock_get.assert_not_called()

    @patch("httpx.Client.get")
    def test_discover_campaigns_returns_relevant(
        self, mock_get, config
    ) -> None:
        """discover_campaigns() should find beauty/skincare campaigns."""
        camps = [
            # Relevant: keyword match
            {
                "id": "1",
                "name": "Serum Vitamin C",
                "category": "68",
                "max_com": "12%",
                "merchant": "brand_a",
                "url": "",
            },
            # Relevant: category match
            {
                "id": "2",
                "name": "Some Random Product",
                "category": "E-COMMERCE",
                "max_com": "5%",
                "merchant": "shop",
                "url": "",
            },
            # Not relevant: wrong category, no keyword match
            {
                "id": "3",
                "name": "Phần mềm kế toán",
                "category": "63",
                "max_com": "20%",
                "merchant": "soft_vn",
                "url": "",
            },
        ]
        mock_get.side_effect = [
            self._mock_campaigns_response(camps),
            self._mock_empty_response(),
        ]

        provider = AccessTradeProvider(config.access_trade)
        results = provider.discover_campaigns()

        assert len(results) == 2
        names = {p.product_name for p in results}
        assert "Serum Vitamin C" in names
        assert "Some Random Product" in names
        assert "Phần mềm kế toán" not in names

    @patch("httpx.Client.get")
    def test_get_categories(self, mock_get, config) -> None:
        camps = [
            {"id": "1", "name": "A", "category": "68", "max_com": "5%", "merchant": "m", "url": ""},
            {"id": "2", "name": "B", "category": "68", "max_com": "10%", "merchant": "m", "url": ""},
            {"id": "3", "name": "C", "category": "59", "max_com": "8%", "merchant": "m", "url": ""},
        ]
        mock_get.side_effect = [
            self._mock_campaigns_response(camps),
            self._mock_empty_response(),
        ]

        provider = AccessTradeProvider(config.access_trade)
        categories = provider.get_categories()

        assert len(categories) == 2
        cat_map = {c["id"]: c["count"] for c in categories}
        assert cat_map["68"] == 2
        assert cat_map["59"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 3. ShopeeProvider
# ═══════════════════════════════════════════════════════════════════════════


class TestShopeeProvider:
    @pytest.fixture
    def config(self) -> AffiliateSettings:
        s = AffiliateSettings(enabled=True)
        s.shopee.enabled = True
        s.shopee.app_id = "test_app"
        s.shopee.secret_key = "test_secret"
        return s

    def test_is_configured_true(self, config) -> None:
        provider = ShopeeProvider(config.shopee)
        assert provider.is_configured() is True

    def test_is_configured_false(self) -> None:
        provider = ShopeeProvider(
            AffiliateSettings().shopee
        )
        assert provider.is_configured() is False

    @patch("httpx.Client.post")
    def test_search_products_parses_graphql_response(
        self, mock_post, config
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "productSearch": {
                    "products": [
                        {
                            "productId": "shopee_1",
                            "productName": "Retinol 0.5%",
                            "price": 350000,
                            "salePrice": 299000,
                            "commissionRate": 0.08,
                            "categoryName": "skincare",
                            "imageUrl": "https://img.url",
                            "affiliateUrl": "https://shopee.vn/aff/1",
                        }
                    ]
                }
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        provider = ShopeeProvider(config.shopee)
        results = provider.search_products(
            "retinol", max_results=5
        )

        assert len(results) == 1
        assert results[0].product_name == "Retinol 0.5%"
        assert results[0].commission_rate == 0.08
        assert results[0].network == "shopee"
        assert (
            results[0].affiliate_url
            == "https://shopee.vn/aff/1"
        )

    @patch("httpx.Client.post")
    def test_search_products_empty_on_failure(
        self, mock_post, config
    ) -> None:
        mock_post.side_effect = Exception("GraphQL error")
        provider = ShopeeProvider(config.shopee)
        results = provider.search_products("vitamin c")
        assert results == []

    @patch("httpx.Client.post")
    def test_unconfigured_returns_empty(
        self, mock_post
    ) -> None:
        provider = ShopeeProvider(
            AffiliateSettings().shopee
        )
        results = provider.search_products("serum")
        assert results == []
        mock_post.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# 4. AffiliateRegistry
# ═══════════════════════════════════════════════════════════════════════════


class TestAffiliateRegistry:
    @pytest.fixture
    def settings(self) -> AffiliateSettings:
        s = AffiliateSettings(enabled=True)
        s.access_trade.enabled = True
        s.access_trade.api_key = "key"
        s.access_trade.api_secret = "secret"
        s.min_commission_rate = 0.0  # Don't filter
        return s

    def test_is_enabled_true_when_provider_configured(
        self, settings
    ) -> None:
        registry = AffiliateRegistry(settings)
        # Provider is configured but mocked → is_enabled checks settings
        assert registry.is_enabled() is True

    def test_is_enabled_false_when_disabled(self) -> None:
        s = AffiliateSettings(enabled=False)
        registry = AffiliateRegistry(s)
        assert registry.is_enabled() is False

    def test_discover_all_returns_empty_when_no_providers(
        self,
    ) -> None:
        s = AffiliateSettings(enabled=False)
        registry = AffiliateRegistry(s)
        result = registry.discover_all()
        assert result == []

    def test_to_topic_candidates_converts_products(
        self, settings
    ) -> None:
        registry = AffiliateRegistry(settings)
        products = [
            AffiliateProduct(
                product_id="1",
                product_name="Kem chống nắng",
                network="accesstrade",
                price=200000,
                commission_rate=0.10,
                commission_note="AccessTrade 10.0%",
            ),
            AffiliateProduct(
                product_id="2",
                product_name="Retinol",
                network="shopee",
                price=350000,
                commission_rate=0.08,
                commission_note="Shopee 8.0%",
            ),
        ]

        candidates = registry.to_topic_candidates(
            products, niche="skincare"
        )

        # Should be 2 products × 2 angles = 4 candidates
        assert len(candidates) == 4

        # Check affiliate_offer field
        assert all(c.is_affiliate_offer for c in candidates)

        # Check network labels in reason_codes
        all_reasons = " ".join(
            " ".join(c.reason_codes) for c in candidates
        )
        assert "affiliate_network:accesstrade" in all_reasons
        assert "affiliate_network:shopee" in all_reasons

    def test_to_topic_candidates_dedup_by_name(
        self, settings
    ) -> None:
        registry = AffiliateRegistry(settings)
        products = [
            AffiliateProduct(
                product_id="1",
                product_name="Kem chống nắng",
                network="accesstrade",
                commission_rate=0.10,
            ),
            AffiliateProduct(
                product_id="2",
                product_name="Kem Chống Nắng",
                network="shopee",
                commission_rate=0.08,
            ),
        ]

        candidates = registry.to_topic_candidates(
            products, niche="skincare"
        )

        # 1 unique product × 2 angles = 2 candidates
        assert len(candidates) == 2

    def test_to_topic_candidates_includes_commission_info(
        self, settings
    ) -> None:
        registry = AffiliateRegistry(settings)
        products = [
            AffiliateProduct(
                product_id="1",
                product_name="Serum C",
                network="accesstrade",
                commission_rate=0.15,
                commission_note="AccessTrade 15.0%",
            ),
        ]

        candidates = registry.to_topic_candidates(
            products, niche="skincare"
        )

        # Commission note should appear in topics/research_queries
        assert any(
            "AccessTrade" in c.topic
            or "[AccessTrade]" in c.topic
            or "AccessTrade" in c.research_query
            for c in candidates
        )

    def test_search_all_skincare_keywords(self) -> None:
        """Test that SKINCARE_SEARCH_KEYWORDS is not empty."""
        assert len(SKINCARE_SEARCH_KEYWORDS) > 10
        assert "retinol" in SKINCARE_SEARCH_KEYWORDS
        assert "kem chống nắng" in SKINCARE_SEARCH_KEYWORDS
        assert "sunscreen" in SKINCARE_SEARCH_KEYWORDS


# ═══════════════════════════════════════════════════════════════════════════
# 5. Pipeline integration (ResearchService)
# ═══════════════════════════════════════════════════════════════════════════


class TestAffiliatePipelineIntegration:
    def test_build_brief_with_affiliate_registry(
        self,
    ) -> None:
        """Test that build_brief accepts fetch_affiliate_offers flag."""
        from fanpage_agent.affiliate.registry import (
            AffiliateRegistry,
        )
        from fanpage_agent.scraping.trend_analyzer import (
            TrendAnalyzer,
        )
        from fanpage_agent.scraping.trend_scraper import (
            TrendScraper,
        )
        from fanpage_agent.services.research import (
            ResearchService,
        )

        settings = AffiliateSettings(enabled=True)
        settings.access_trade.enabled = True
        settings.access_trade.api_key = "test"
        settings.access_trade.api_secret = "test"

        registry = AffiliateRegistry(settings)

        service = ResearchService(
            trend_scraper=TrendScraper(),
            trend_analyzer=TrendAnalyzer([]),
            affiliate_registry=registry,
        )

        # Use a mock store
        mock_store = MagicMock()
        mock_store.read_post_history.return_value = []
        mock_store.read_post_metrics.return_value = []

        brief = service.build_brief(
            store=mock_store,
            fetch_external_trends=False,
            fetch_affiliate_offers=True,
            page_context={
                "industry_focus": "skincare"
            },
        )

        # The affiliate discovery should not crash — it'll
        # log a warning because the provider's search calls
        # will fail (no real API), but that's expected.
        assert brief is not None

    def test_build_brief_accepts_registry_parameter(
        self,
    ) -> None:
        """Registry parameter in constructor doesn't break
        existing callers."""
        from fanpage_agent.services.research import (
            ResearchService,
        )

        # No registry passed — auto-creates (but with no providers configured)
        service = ResearchService()
        assert service._affiliate_registry is not None
        assert not service._affiliate_registry.is_enabled()
