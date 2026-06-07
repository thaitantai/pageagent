"""Base models and protocols for multi-affiliate provider system.

Defines the contract that all affiliate providers must implement,
plus the standardised AffiliateProduct model used across the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class AffiliateNetwork(str, Enum):
    """Supported affiliate network identifiers."""

    ACCESSTRADE = "accesstrade"
    SHOPEE = "shopee"
    MASOFFER = "masoffer"
    CUSTOM = "custom"


@dataclass(frozen=True)
class AffiliateProduct:
    """A product discovered from an affiliate network.

    This is the standardised intermediate representation before conversion
    to ProductTopicCandidate for the pipeline.
    """

    product_id: str
    product_name: str
    network: AffiliateNetwork | str
    category: str = ""
    price: float | None = None
    sale_price: float | None = None
    commission_rate: float = 0.0  # e.g. 0.10 = 10%
    commission_note: str = ""
    affiliate_url: str = ""
    image_url: str = ""
    product_url: str = ""
    currency: str = "VND"
    metadata: dict = field(default_factory=dict)

    @property
    def effective_price(self) -> float | None:
        """Return sale_price if available, otherwise price."""
        return self.sale_price or self.price

    @property
    def network_label(self) -> str:
        """Human-readable network label."""
        try:
            return AffiliateNetwork(self.network).name.title()
        except ValueError:
            return str(self.network).title()


@runtime_checkable
class AffiliateProvider(Protocol):
    """Protocol that every affiliate network provider must implement.

    Each provider is responsible for:
      - Authentication (API keys, signing, etc.)
      - Product search with categories / keywords
      - Commission retrieval
      - Affiliate link generation
      - Graceful degradation when credentials are missing
    """

    # Human-readable provider name (e.g. "AccessTrade", "Shopee")
    name: str

    # Network identifier matching AffiliateNetwork enum or custom string
    network_id: str

    def is_configured(self) -> bool:
        """Return True if this provider has valid credentials configured."""
        ...

    def search_products(
        self,
        keyword: str,
        category_id: str | None = None,
        max_results: int = 10,
    ) -> list[AffiliateProduct]:
        """Search products by keyword, optionally filtered by category.

        Returns an empty list when the provider is not configured
        or the search returns no results.
        """
        ...

    def get_categories(self) -> list[dict]:
        """Return available product categories from this network.

        Each entry: {"id": "...", "name": "...", "parent_id": "..."}
        Returns empty list when the provider is not configured.
        """
        ...

    def get_commission(self, product_id: str) -> float:
        """Return commission rate (0.0–1.0) for a specific product.

        Returns 0.0 when the provider is not configured or
        the commission cannot be determined.
        """
        ...

    def generate_link(self, product_id: str) -> str:
        """Generate or return an affiliate tracking link for a product.

        Returns empty string when the provider is not configured.
        """
        ...


# ── Default skincare categories for affiliate search ──────────────────────

SKINCARE_SEARCH_KEYWORDS: list[str] = [
    "serum vitamin c",
    "retinol",
    "kem chống nắng",
    "sunscreen",
    "niacinamide",
    "kem dưỡng ẩm",
    "moisturizer",
    "sữa rửa mặt",
    "cleanser",
    "toner",
    "mặt nạ",
    "face mask",
    "dưỡng trắng",
    "chống lão hóa",
    "anti-aging",
    "tẩy tế bào chết",
    "exfoliator",
    "dầu tẩy trang",
    "nước tẩy trang",
    "micellar water",
]
