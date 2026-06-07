"""Affiliate provider configuration — loads from env vars + pages.toml.

Security principle: API keys and secrets live in environment variables
(.env), never in config files tracked by git. The config file only
declares which providers are enabled and non-sensitive settings.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Env var names ────────────────────────────────────────────────────────

ENV_ACCESSTRADE_API_KEY = "ACCESSTRADE_API_KEY"
ENV_ACCESSTRADE_API_SECRET = "ACCESSTRADE_API_SECRET"
ENV_SHOPEE_AFFILIATE_APP_ID = "SHOPEE_AFFILIATE_APP_ID"
ENV_SHOPEE_AFFILIATE_SECRET_KEY = "SHOPEE_AFFILIATE_SECRET_KEY"
ENV_MASOFFER_API_KEY = "MASOFFER_API_KEY"

# ── Default config paths ──────────────────────────────────────────────────

_DEFAULT_PAGES_TOML = Path(__file__).resolve().parent.parent / "pages.toml"


@dataclass
class AccessTradeConfig:
    """AccessTrade affiliate configuration."""

    enabled: bool = False
    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://api.accesstrade.vn/v1"

    def is_configured(self) -> bool:
        return bool(self.enabled and self.api_key)


@dataclass
class ShopeeConfig:
    """Shopee Affiliate Program configuration (GraphQL API)."""

    enabled: bool = False
    app_id: str = ""
    secret_key: str = ""
    base_url: str = "https://open-api.affiliate.shopee.vn/graphql"

    def is_configured(self) -> bool:
        return bool(self.enabled and self.app_id and self.secret_key)


@dataclass
class MasOfferConfig:
    """MasOffer affiliate configuration (placeholder for future use)."""

    enabled: bool = False
    api_key: str = ""
    base_url: str = "https://masoffer.com/api/v1"

    def is_configured(self) -> bool:
        return bool(self.enabled and self.api_key)


@dataclass
class AffiliateSettings:
    """Aggregated affiliate configuration for the Fanpage Agent.

    Populated from environment variables + pages.toml at startup.
    """

    enabled: bool = False
    auto_discover: bool = True
    search_keywords: list[str] | None = None  # None = use defaults
    max_products_per_provider: int = 10
    min_commission_rate: float = 0.05  # Skip products below 5% commission
    access_trade: AccessTradeConfig = field(default_factory=AccessTradeConfig)
    shopee: ShopeeConfig = field(default_factory=ShopeeConfig)
    mas_offer: MasOfferConfig = field(default_factory=MasOfferConfig)
    # Custom providers can be added via dict
    custom_providers: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        pages_toml: Path | str | None = None,
        force_reload: bool = False,
    ) -> AffiliateSettings:
        """Load affiliate config from environment + pages.toml.

        Environment variables take precedence over config file values.
        Missing values result in disabled providers, never crashes.
        """
        _ = force_reload  # Reserved for future caching
        config_path = Path(pages_toml) if pages_toml else _DEFAULT_PAGES_TOML

        # Parse config file
        raw = cls._parse_toml(config_path)

        affiliate_raw = raw.get("affiliate", {})
        providers_raw = affiliate_raw.get("providers", {})

        # ── Env vars override file values ──
        at_api_key = os.environ.get(ENV_ACCESSTRADE_API_KEY) or ""
        at_api_secret = os.environ.get(ENV_ACCESSTRADE_API_SECRET) or ""

        shopee_app_id = os.environ.get(ENV_SHOPEE_AFFILIATE_APP_ID) or ""
        shopee_secret = os.environ.get(ENV_SHOPEE_AFFILIATE_SECRET_KEY) or ""

        masoffer_key = os.environ.get(ENV_MASOFFER_API_KEY) or ""

        # ── Build config objects ──
        at_raw = providers_raw.get("accesstrade", {})
        at_config = AccessTradeConfig(
            enabled=at_raw.get("enabled", bool(at_api_key)),
            api_key=at_api_key or at_raw.get("api_key", ""),
            api_secret=at_api_secret or at_raw.get("api_secret", ""),
            base_url=at_raw.get("base_url", AccessTradeConfig.base_url),
        )

        shopee_raw = providers_raw.get("shopee", {})
        shopee_config = ShopeeConfig(
            enabled=shopee_raw.get("enabled", bool(shopee_app_id)),
            app_id=shopee_app_id or shopee_raw.get("app_id", ""),
            secret_key=shopee_secret or shopee_raw.get("secret_key", ""),
            base_url=shopee_raw.get(
                "base_url", ShopeeConfig.base_url
            ),
        )

        mas_raw = providers_raw.get("masoffer", {})
        mas_config = MasOfferConfig(
            enabled=mas_raw.get("enabled", bool(masoffer_key)),
            api_key=masoffer_key or mas_raw.get("api_key", ""),
            base_url=mas_raw.get(
                "base_url", MasOfferConfig.base_url
            ),
        )

        custom_providers = {
            k: v
            for k, v in providers_raw.items()
            if k not in {"accesstrade", "shopee", "masoffer"}
        }

        enabled = affiliate_raw.get("enabled", True)

        return cls(
            enabled=enabled,
            auto_discover=affiliate_raw.get(
                "auto_discover", True
            ),
            search_keywords=affiliate_raw.get("search_keywords"),
            max_products_per_provider=affiliate_raw.get(
                "max_products_per_provider", 10
            ),
            min_commission_rate=affiliate_raw.get(
                "min_commission_rate", 0.05
            ),
            access_trade=at_config,
            shopee=shopee_config,
            mas_offer=mas_config,
            custom_providers=custom_providers,
        )

    @staticmethod
    def _parse_toml(path: Path) -> dict:
        """Parse a TOML file, return empty dict on failure."""
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ImportError:
                logger.warning(
                    "tomllib/tomli not available; affiliate config disabled"
                )
                return {}

        if not path.exists():
            logger.debug(
                "Affiliate config file not found: %s", path
            )
            return {}

        try:
            with path.open("rb") as f:
                return tomllib.load(f)
        except Exception as exc:
            logger.warning(
                "Failed to parse affiliate config %s: %s",
                path,
                exc,
            )
            return {}
