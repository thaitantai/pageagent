"""AccessTrade affiliate provider implementation.

AccessTrade (accesstrade.vn) is a Vietnamese affiliate network with
products from Shopee, Tiki, Lazada, and many other merchants.
Uses REST API v1 documented at api.accesstrade.vn.

The .vn API exposes campaigns (merchant affiliate programs), not
individual products. Each campaign has a commission rate (max_com),
category, subcategory, and landing URL.

Authentication: ``Authorization: Token <api_key>`` header.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from fanpage_agent.affiliate.base import (
    AffiliateNetwork,
    AffiliateProduct,
)
from fanpage_agent.affiliate.config import AccessTradeConfig

logger = logging.getLogger(__name__)

# ── API endpoints ─────────────────────────────────────────────────────────

_CAMPAIGNS_ENDPOINT = "/campaigns"
_LINK_ENDPOINT = "/links"

# Max items per page the API supports
_MAX_LIMIT = 50

# Timeout for API calls
_REQUEST_TIMEOUT = 15.0

# ── Skincare / beauty / health keyword matching ──────────────────────────

_NICHE_KEYWORDS = [
    # Skincare & beauty (Vietnamese + English)
    "mỹ phẩm", "skincare", "beauty", "làm đẹp", "dưỡng da",
    "chăm sóc da", "serum", "kem chống nắng", "sữa rửa mặt",
    "tẩy trang", "toner", "retinol", "vitamin c", "niacinamide",
    "spf", "collagen", "tinh dầu", "dầu gội", "sữa tắm",
    "nước hoa", "mascara", "son môi", "phấn mắt",
    "thẩm mỹ", "ngọc dung", "watsons", "guardian",
    "thefaceshop", "innisfree", "hasaki",
    # Health & wellness
    "sức khỏe", "vitamin", "thực phẩm chức năng", "tpc",
    "traphaco", "suntory", "sachi",
    # General e-commerce platforms
    "shopee", "lazada", "tiki", "sendo",
]

# Category IDs that are likely e-commerce / beauty
_RELEVANT_CATEGORIES: set[str] = {
    "68",  # beauty/cosmetics (many matches)
    "18",  # health/pharmacy (Traphaco)
    "29",  # e-commerce platforms
    "E-COMMERCE",  # explicit e-commerce category
}


def _parse_commission(max_com: str | None) -> tuple[float, str]:
    """Parse commission from AccessTrade max_com field.

    Returns (rate_as_float_0_to_1, display_string).

    Examples:
        "8.4%" → (0.084, "8.4%")
        "140.000" → (0.0, "140.000 VND")  # fixed amount
        "26.4%" → (0.264, "26.4%")
        "2,5%" → (0.025, "2.5%")
        "30000" → (0.0, "30,000 VND")
        None → (0.0, "0%")
    """
    if not max_com:
        return 0.0, "0%"

    text = str(max_com).strip()

    # Percentage-based: matches "8.4%", "2,5%", "7%", "7,5%"
    pct_match = re.match(r"^([\d,.]+\d)\s*%$", text.replace(",", "."))
    if pct_match:
        val = float(pct_match.group(1))
        return val / 100, f"{val:.1f}%"

    # Check for VND amount (number with dots or plain digits)
    # e.g., "140.000", "250,000", "30000", "150.000 VND - 300.000 VND"
    vnd_match = re.match(r"^([\d.,]+)\s*(?:VND)?$", text)
    if vnd_match:
        # Take just the first number for range values
        raw = vnd_match.group(1).replace(".", "").replace(",", "")
        try:
            amount_int = int(raw)
            return 0.0, f"{amount_int:,} VND".replace(",", ".")
        except ValueError:
            pass

    # Handle range values like "150.000 VND - 300.000 VND"
    range_match = re.match(r"^([\d.,]+)\s*VND.*", text)
    if range_match:
        raw = range_match.group(1).replace(".", "")
        try:
            amount_int = int(raw)
            return 0.0, f"{amount_int:,} VND".replace(",", ".")
        except ValueError:
            pass

    return 0.0, str(max_com)


class AccessTradeProvider:
    """Provider for the AccessTrade affiliate network (Vietnam).

    Fetches campaigns (merchant programs) and converts them into
    AffiliateProduct candidates for the discovery pipeline.

    Implements the AffiliateProvider protocol. Gracefully returns
    empty results when the provider is not configured.
    """

    name = "AccessTrade"
    network_id = AffiliateNetwork.ACCESSTRADE.value

    def __init__(self, config: AccessTradeConfig) -> None:
        self._config = config
        self._client: httpx.Client | None = None
        self._cached_campaigns: list[dict] | None = None

    # ── Public API ─────────────────────────────────────────────────────

    def is_configured(self) -> bool:
        return self._config.is_configured()

    def search_products(
        self,
        keyword: str,
        category_id: str | None = None,
        max_results: int = 10,
    ) -> list[AffiliateProduct]:
        """Search campaigns by keyword matching on name + merchant.

        Falls back to niche-based discovery (discover_campaigns) when
        the keyword does not match any campaign name — this is typical
        for AccessTrade since campaigns are merchant-level names
        (e.g. "HINICE Official") that won't match specific product
        keywords like "retinol".
        """
        if not self.is_configured():
            return []
        all_camps = self._fetch_all_campaigns()
        matching = self._filter_campaigns(all_camps, keyword, category_id)
        if matching:
            return [self._campaign_to_product(c) for c in matching[:max_results]]
        # Fallback: keyword didn't match any campaign name/merchant.
        # Use niche-based discovery for broader matching.
        logger.info(
            "AccessTrade keyword '%s' matched 0 campaigns, "
            "falling back to niche discovery",
            keyword,
        )
        return self.discover_campaigns(max_results=max_results)

    def discover_campaigns(
        self,
        niche: str = "skincare",
        max_results: int = 10,
    ) -> list[AffiliateProduct]:
        """Discover campaigns relevant to a niche using keyword matching.

        Uses a built-in skincare/beauty keyword list to filter campaigns
        by name and merchant. Also includes major e-commerce platforms
        (Shopee, Lazada, Tiki) which are broadly relevant.
        """
        if not self.is_configured():
            return []
        all_camps = self._fetch_all_campaigns()
        matching = self._filter_by_niche(all_camps)
        return [self._campaign_to_product(c) for c in matching[:max_results]]

    def get_categories(self) -> list[dict]:
        """Return available campaign categories from fetched data."""
        if not self.is_configured():
            return []
        camps = self._fetch_all_campaigns()
        seen: dict[str, int] = {}
        for c in camps:
            cat = c.get("category")
            if cat:
                seen[str(cat)] = seen.get(str(cat), 0) + 1
        return [
            {"id": cid, "name": cid, "count": count}
            for cid, count in sorted(seen.items(), key=lambda x: -x[1])
        ]

    def get_commission(self, campaign_id: str) -> float:
        """Get commission rate for a campaign by its ID.

        Returns the rate as a float (0-1 range for % commission,
        0.0 for fixed-amount campaigns).
        """
        if not self.is_configured():
            return 0.0
        camps = self._fetch_all_campaigns()
        for c in camps:
            if str(c.get("id", "")) == campaign_id:
                rate, _ = _parse_commission(c.get("max_com"))
                return rate
        return 0.0

    def generate_link(self, product_id: str, click_id: str | None = None) -> str:
        """Generate a tracking link for a campaign.

        Falls back to the campaign URL if link generation is unavailable.
        """
        if not self.is_configured():
            return ""

        cid = click_id or f"fanpage-{id(self)}"
        payload = {
            "campaign_id": product_id,
            "click_id": cid,
        }

        try:
            resp = self._get_client().post(
                _LINK_ENDPOINT, json=payload
            )
            if resp.status_code == 200:
                body = self._safe_json(resp)
                if isinstance(body, dict):
                    return str(
                        body.get("short_url", body.get("url", body.get("data", "")))
                    )
            logger.info(
                "Link gen returned %s for campaign %s, using campaign URL",
                resp.status_code,
                product_id,
            )
        except Exception as exc:
            logger.warning(
                "Link gen failed for %s: %s, using campaign URL",
                product_id,
                exc,
            )

        # Fallback: return the campaign URL
        camps = self._fetch_all_campaigns()
        for c in camps:
            if str(c.get("id", "")) == product_id:
                return str(c.get("url", ""))
        return ""

    # ── Campaign fetching ──────────────────────────────────────────────

    def _fetch_all_campaigns(self) -> list[dict]:
        """Fetch ALL campaigns from the API across all pages (cached)."""
        if self._cached_campaigns is not None:
            return self._cached_campaigns
        camps: list[dict] = []
        page = 1
        while True:
            try:
                resp = self._get_client().get(
                    _CAMPAIGNS_ENDPOINT,
                    params={"limit": _MAX_LIMIT, "page": page},
                )
                resp.raise_for_status()
                body = self._safe_json(resp)
                items = body.get("data", []) if isinstance(body, dict) else []
                if not items:
                    break
                camps.extend(items)
                page += 1
            except httpx.HTTPStatusError as exc:
                logger.warning("AccessTrade page %s failed: %s", page, exc)
                break
            except Exception as exc:
                logger.warning("AccessTrade page %s error: %s", page, exc)
                break
        self._cached_campaigns = camps
        return camps

    # ── Filtering ──────────────────────────────────────────────────────

    @classmethod
    def _filter_campaigns(
        cls,
        campaigns: list[dict],
        keyword: str,
        category_id: str | None = None,
    ) -> list[dict]:
        """Filter campaigns by keyword (name/merchant) and optional category."""
        kw = keyword.lower()
        results: list[dict] = []
        for c in campaigns:
            name = (c.get("name") or "").lower()
            merchant = (c.get("merchant") or "").lower()
            match = kw in name or kw in merchant
            if category_id:
                match = match and str(c.get("category", "")) == category_id
            if match:
                results.append(c)
        return results

    @classmethod
    def _filter_by_niche(cls, campaigns: list[dict]) -> list[dict]:
        """Filter campaigns relevant to a beauty/skincare niche."""
        results: list[dict] = []
        for c in campaigns:
            name = (c.get("name") or "").lower()
            merchant = (c.get("merchant") or "").lower()
            cat = str(c.get("category", ""))
            text = name + " " + merchant

            # Check for niche keyword match
            keyword_match = any(kw in text for kw in _NICHE_KEYWORDS)

            # Check for relevant category
            cat_match = cat in _RELEVANT_CATEGORIES

            if keyword_match or cat_match:
                results.append(c)
        return results

    # ── Conversion ─────────────────────────────────────────────────────

    @classmethod
    def _campaign_to_product(cls, campaign: dict) -> AffiliateProduct:
        """Convert a raw campaign dict into an AffiliateProduct."""
        campaign_id = str(campaign.get("id", ""))
        name = str(campaign.get("name", ""))
        commission_rate, commission_str = _parse_commission(
            campaign.get("max_com")
        )
        category = str(campaign.get("category", ""))
        sub_category = str(campaign.get("sub_category", "") or "")
        full_category = f"{category}/{sub_category}" if sub_category else category

        return AffiliateProduct(
            product_id=campaign_id,
            product_name=name.strip(),
            network=AffiliateNetwork.ACCESSTRADE.value,
            category=full_category,
            price=None,
            sale_price=None,
            commission_rate=commission_rate,
            commission_note=f"AccessTrade {commission_str}",
            affiliate_url="",
            image_url=str(campaign.get("logo", "")),
            product_url=str(campaign.get("url", "")),
            currency="VND",
            metadata={
                "merchant_name": str(campaign.get("merchant", "")),
                "campaign_type": str(campaign.get("type", "")),
                "commission_raw": str(campaign.get("max_com", "")),
                "approval_status": str(campaign.get("approval", "")),
                "category_id": category,
                "sub_category_id": sub_category,
                "scope": str(campaign.get("scope", "")),
            },
        )

    # ── Internal helpers ───────────────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self._config.base_url,
                timeout=_REQUEST_TIMEOUT,
                headers={
                    "Authorization": f"Token {self._config.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        """Safely parse JSON from an httpx response.

        The AccessTrade VN API sometimes returns double-encoded JSON
        strings (the JSON is wrapped in an extra layer of quotes).
        This handles both normal and double-encoded responses.
        """
        raw = json.loads(response.text)
        if isinstance(raw, str):
            # Double-encoded: parse again
            return json.loads(raw)
        return raw

    @staticmethod
    def _to_float(value: Any) -> float | None:
        """Safely convert a value to float or None."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
