"""AffiliateRegistry — manages multiple affiliate providers and integrates with the pipeline.

The registry is the entry point for all affiliate interactions. It:
  - Holds all configured providers (AccessTrade, Shopee, etc.)
  - Searches all providers in parallel for a keyword
  - Converts AffiliateProduct → ProductTopicCandidate for the pipeline
  - Filters by minimum commission rate
  - Deduplicates products across networks
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fanpage_agent.affiliate.access_trade import AccessTradeProvider
from fanpage_agent.affiliate.base import (
    SKINCARE_SEARCH_KEYWORDS,
    AffiliateProduct,
)
from fanpage_agent.affiliate.config import AffiliateSettings
from fanpage_agent.affiliate.shopee import ShopeeProvider
from fanpage_agent.tools.research.product_topic_discovery import (
    ProductTopicCandidate,
)

logger = logging.getLogger(__name__)

# ── Default price thresholds for "affordable" in skincare ────────────────
_MAX_AFFORDABLE_PRICE_VND = 500_000  # 500k VND


class AffiliateRegistry:
    """Registry of affiliate providers with pipeline integration.

    Usage::

        settings = AffiliateSettings.load()
        registry = AffiliateRegistry(settings)

        # Get all products matching a keyword across all providers
        products = registry.search_all("retinol", max_results=5)

        # Convert to pipeline-compatible ProductTopicCandidate list
        candidates = registry.to_topic_candidates(products, niche="skincare")

        # Or do both at once
        discover_all = registry.discover_all(niche="skincare")
    """

    def __init__(
        self,
        settings: AffiliateSettings | None = None,
    ) -> None:
        self._settings = settings or AffiliateSettings()
        self._providers: list[Any] = []
        self._init_providers()

    # ── Public API ─────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Return True if at least one provider is configured."""
        return (
            self._settings.enabled
            and any(
                p.is_configured() for p in self._providers
            )
        )

    def search_all(
        self,
        keyword: str,
        category_id: str | None = None,
        max_results_per_provider: int = 5,
        min_commission: float | None = None,
    ) -> list[AffiliateProduct]:
        """Search all configured providers for a keyword.

        Results are sorted by commission rate descending.
        Duplicate product names across providers are deduplicated.

        Parameters
        ----------
        keyword : str
            Search keyword (e.g. \"retinol\", \"kem chống nắng\").
        category_id : str | None
            Optional category filter (network-specific).
        max_results_per_provider : int
            Max results to fetch from each provider.
        min_commission : float | None
            Minimum commission rate (0.0–1.0). Defaults to
            settings.min_commission_rate if not set.

        Returns
        -------
        list[AffiliateProduct]
            Sorted by commission_rate descending.
        """
        if not self._settings.enabled:
            return []

        threshold = (
            min_commission
            if min_commission is not None
            else self._settings.min_commission_rate
        )
        all_products: list[AffiliateProduct] = []
        seen_names: set[str] = set()

        for provider in self._providers:
            if not provider.is_configured():
                continue
            try:
                products = provider.search_products(
                    keyword=keyword,
                    category_id=category_id,
                    max_results=max_results_per_provider,
                )
            except Exception as exc:
                logger.warning(
                    "Provider %s search failed for '%s': %s",
                    provider.name,
                    keyword,
                    exc,
                )
                continue

            for p in products:
                name_normalized = self._normalize_name(
                    p.product_name
                )
                if name_normalized in seen_names:
                    continue
                if p.commission_rate < threshold:
                    continue
                seen_names.add(name_normalized)
                all_products.append(p)

        all_products.sort(
            key=lambda p: p.commission_rate, reverse=True
        )
        return all_products

    def search_skincare_products(
        self,
        keywords: list[str] | None = None,
        max_results_per_provider: int = 5,
    ) -> list[AffiliateProduct]:
        """Search multiple skincare-related keywords across all providers.

        Uses the default SKINCARE_SEARCH_KEYWORDS list, or a custom list.

        Parameters
        ----------
        keywords : list[str] | None
            Custom search keywords. Defaults to SKINCARE_SEARCH_KEYWORDS.
        max_results_per_provider : int
            Max results per keyword per provider.

        Returns
        -------
        list[AffiliateProduct]
            Sorted by commission_rate descending, deduplicated.
        """
        kw_list = keywords or self._settings.search_keywords or SKINCARE_SEARCH_KEYWORDS
        all_products: list[AffiliateProduct] = []
        seen_names: set[str] = set()

        for kw in kw_list:
            for p in self.search_all(
                keyword=kw,
                max_results_per_provider=max_results_per_provider,
            ):
                name_norm = self._normalize_name(p.product_name)
                if name_norm not in seen_names:
                    seen_names.add(name_norm)
                    all_products.append(p)

        all_products.sort(
            key=lambda p: p.commission_rate, reverse=True
        )
        return all_products

    def discover_all(
        self,
        niche: str = "skincare",
        keywords: list[str] | None = None,
        max_results_per_provider: int = 5,
        max_total_candidates: int = 20,
    ) -> list[ProductTopicCandidate]:
        """One-shot: search all providers + convert to topic candidates.

        This is the method used by ResearchTool.build_brief().

        Parameters
        ----------
        niche : str
            Niche/industry name for topic generation (e.g. \"skincare\").
        keywords : list[str] | None
            Custom search keywords. Defaults to SKINCARE_SEARCH_KEYWORDS.
        max_results_per_provider : int
            Max results per keyword per provider.
        max_total_candidates : int
            Max ProductTopicCandidate to return.

        Returns
        -------
        list[ProductTopicCandidate]
            Candidates ready for pipeline integration.
        """
        if not self._settings.enabled:
            return []

        products = self.search_skincare_products(
            keywords=keywords,
            max_results_per_provider=max_results_per_provider,
        )
        return self.to_topic_candidates(
            products[: max_total_candidates * 2],
            niche=niche,
        )[:max_total_candidates]

    def to_topic_candidates(
        self,
        products: list[AffiliateProduct],
        niche: str = "skincare",
    ) -> list[ProductTopicCandidate]:
        """Convert AffiliateProduct list → ProductTopicCandidate list.

        Each product generates 1-2 candidates with different angles
        (education + buying_guide) so the pipeline has options.

        Parameters
        ----------
        products : list[AffiliateProduct]
            Products from any affiliate providers.
        niche : str
            Niche name for research_query generation.

        Returns
        -------
        list[ProductTopicCandidate]
        """
        candidates: list[ProductTopicCandidate] = []
        seen: set[str] = set()

        for product in products:
            name = product.product_name.strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())

            # Determine risk: expensive or medical-adjacent = medium
            risk = self._estimate_risk(product)
            relevance = self._estimate_relevance(product)
            customer_val = self._estimate_customer_value(
                product
            )

            # Reason codes
            reason_codes = [
                "affiliate_offer",
                f"affiliate_network:{product.network}",
                f"commission:{product.commission_rate:.2f}",
            ]
            if product.network_label:
                reason_codes.append(
                    f"src_network:{product.network}"
                )
            if product.category:
                reason_codes.append(
                    f"category:{product.category}"
                )
            if (
                product.effective_price
                and product.effective_price
                > _MAX_AFFORDABLE_PRICE_VND
            ):
                reason_codes.append("premium_price")

            commission_note = (
                product.commission_note
                or f"{product.network_label} "
                f"{product.commission_rate * 100:.1f}%"
            )

            research_query = (
                f"{name} {niche} review {commission_note}"
            )

            # Generate 2 angles
            for angle in ["education", "buying_guide"]:
                if angle == "education":
                    topic_name = (
                        f"{name}: {name} có thực sự hiệu quả cho {niche}? "
                        f"[{product.network_label}]"
                    )
                else:
                    topic_name = (
                        f"Cách chọn {name} phù hợp: review từ chuyên gia "
                        f"[{product.network_label}]"
                    )

                candidates.append(
                    ProductTopicCandidate(
                        topic=topic_name,
                        angle=angle,
                        product_name=name,
                        customer_pain=self._infer_pain_point(
                            name, product.category
                        ),
                        research_query=research_query,
                        product_relevance=round(
                            relevance, 3
                        ),
                        customer_value=round(customer_val, 3),
                        risk_level=risk,
                        reason_codes=list(reason_codes),
                    )
                )

        return candidates

    # ── Private helpers ────────────────────────────────────────────────

    def _init_providers(self) -> None:
        """Initialise all configured providers."""
        if not self._settings.enabled:
            return

        if self._settings.access_trade.is_configured():
            self._providers.append(
                AccessTradeProvider(
                    self._settings.access_trade
                )
            )

        if self._settings.shopee.is_configured():
            self._providers.append(
                ShopeeProvider(self._settings.shopee)
            )

        # Custom providers (future extensibility)
        for name, raw in self._settings.custom_providers.items():
            logger.info(
                "Custom affiliate provider '%s' registered "
                "but no factory available",
                name,
            )

        if self._providers:
            logger.info(
                "AffiliateRegistry: %d provider(s) configured: %s",
                len(self._providers),
                ", ".join(p.name for p in self._providers),
            )

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize product name for dedup comparison."""
        normalized = name.lower().strip()
        # Remove common suffixes like "(chính hãng)", "(xịn)"
        normalized = re.sub(
            r"\(.*?\)", "", normalized
        ).strip()
        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    @staticmethod
    def _estimate_risk(product: AffiliateProduct) -> str:
        """Estimate risk level for affiliate content."""
        if product.effective_price and product.effective_price > 1_000_000:
            return "medium"  # Expensive products need more careful claims
        name_lower = product.product_name.lower()
        high_risk_markers = [
            "retinol", "tretinoin", "adapalene", "acid",
            "peel", "lột", "trị mụn", "vitamin a",
        ]
        if any(m in name_lower for m in high_risk_markers):
            return "medium"
        return "low"

    @staticmethod
    def _estimate_relevance(product: AffiliateProduct) -> float:
        """Estimate niche relevance from product name + category."""
        name_lower = f"{product.product_name} {product.category}".lower()
        high_relevance = [
            "skincare", "chăm sóc da", "dưỡng da", "serum",
            "retinol", "vitamin c", "kem chống nắng", "sunscreen",
            "moisturizer", "kem dưỡng", "cleanser", "sữa rửa mặt",
            "toner", "mặt nạ", "face mask", "niacinamide",
        ]
        medium_relevance = [
            "mỹ phẩm", "cosmetic", "làm đẹp", "beauty",
            "dưỡng trắng", "chống lão hóa", "anti-aging",
        ]
        for marker in high_relevance:
            if marker in name_lower:
                return 0.85
        for marker in medium_relevance:
            if marker in name_lower:
                return 0.70
        return 0.55

    @staticmethod
    def _estimate_customer_value(
        product: AffiliateProduct,
    ) -> float:
        """Estimate customer value for an affiliate product."""
        if product.effective_price is None:
            return 0.60

        # Products under 200k are impulse buys
        if product.effective_price < 200_000:
            return 0.50
        # 200k–500k: reasonable purchase
        if product.effective_price < 500_000:
            return 0.70
        # Over 500k: needs justification, higher value
        if product.effective_price < 1_000_000:
            return 0.80

        return 0.65

    @staticmethod
    def _infer_pain_point(
        product_name: str, category: str
    ) -> str:
        """Infer a customer pain point from product name and category."""
        text = f"{product_name} {category}".lower()
        pain_map: list[tuple[str, str]] = [
            ("retinol", "sợ kích ứng khi mới dùng retinol"),
            ("vitamin c", "lo lắng về nồng độ vitamin C phù hợp"),
            ("sunscreen", "băn khoăn chọn kem chống nắng không bí da"),
            ("kem chống nắng", "băn khoăn chọn kem chống nắng không bí da"),
            ("niacinamide", "không biết kết hợp niacinamide với sản phẩm khác"),
            ("moisturizer", "da thiếu ẩm dù đã dùng nhiều sản phẩm"),
            ("cleanser", "sữa rửa mặt làm da khô căng sau khi rửa"),
            ("toner", "không biết có cần toner trong routine không"),
            ("acid", "sợ acid làm da bỏng rát"),
            ("mask", "mặt nạ nên dùng bao nhiêu lần/tuần"),
            ("serum", "chưa biết serum nào phù hợp với da dầu"),
            ("dưỡng trắng", "muốn dưỡng trắng nhưng sợ sản phẩm không an toàn"),
            ("chống lão hóa", "lo lắng chống lão hóa từ tuổi nào"),
        ]
        for marker, pain in pain_map:
            if marker in text:
                return pain
        return f"tìm hiểu về {product_name} trước khi mua"
