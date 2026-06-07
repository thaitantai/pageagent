"""Affiliate multi-provider support for the Fanpage Agent.

Provides a configurable system for discovering skincare products
from multiple affiliate networks:

- AccessTrade (accesstrade.vn)
- Shopee Affiliate Program
- Future: MasOffer, custom providers

Usage::

    from fanpage_agent.affiliate import AffiliateRegistry, AffiliateSettings

    settings = AffiliateSettings.load()
    registry = AffiliateRegistry(settings)
    candidates = registry.discover_all(niche=\"skincare\")
"""

from __future__ import annotations

from fanpage_agent.affiliate.access_trade import (
    AccessTradeProvider,
)
from fanpage_agent.affiliate.base import (
    SKINCARE_SEARCH_KEYWORDS,
    AffiliateNetwork,
    AffiliateProduct,
    AffiliateProvider,
)
from fanpage_agent.affiliate.config import (
    AccessTradeConfig,
    AffiliateSettings,
    MasOfferConfig,
    ShopeeConfig,
)
from fanpage_agent.affiliate.registry import (
    AffiliateRegistry,
)
from fanpage_agent.affiliate.shopee import ShopeeProvider

__all__ = [
    # Core
    "AffiliateRegistry",
    "AffiliateSettings",
    # Models
    "AffiliateProduct",
    "AffiliateNetwork",
    "AffiliateProvider",
    # Config models
    "AccessTradeConfig",
    "ShopeeConfig",
    "MasOfferConfig",
    # Providers
    "AccessTradeProvider",
    "ShopeeProvider",
    # Constants
    "SKINCARE_SEARCH_KEYWORDS",
]
