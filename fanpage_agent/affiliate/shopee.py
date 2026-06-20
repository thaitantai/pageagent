"""Shopee Affiliate Program provider implementation.

Shopee Affiliate Open API uses GraphQL at:
  https://open-api.affiliate.shopee.vn/graphql

Authentication: HMAC-SHA256 signature with App ID + Secret Key.
Endpoint requires a signature generated from:
  - app_id
  - timestamp
  - access_token (empty for affiliate, we use app_id + secret only)
  - body hash

Gracefully degrades (returns empty) when credentials are not configured.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx

from fanpage_agent.affiliate.base import (
    AffiliateNetwork,
    AffiliateProduct,
)
from fanpage_agent.affiliate.config import ShopeeConfig

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15.0

# ── GraphQL operations ───────────────────────────────────────────────────

_PRODUCT_SEARCH_QUERY = """
query SearchProduct($keyword: String!, $limit: Int) {
  productSearch(keyword: $keyword, limit: $limit) {
    products {
      productId
      productName
      imageUrl
      price
      salePrice
      currency
      commission
      commissionRate
      categoryName
      affiliateUrl
      productUrl
    }
  }
}
"""

_CATEGORY_LIST_QUERY = """
query {
  categoryList(level: 1) {
    categoryId
    categoryName
    parentId
  }
}
"""

_COMMISSION_QUERY = """
query Commission($productId: String!) {
  productCommission(productId: $productId) {
    commissionRate
    commission
  }
}
"""

_LINK_GENERATION_MUTATION = """
mutation GenerateLink($productId: String!, $clickId: String) {
  generateLink(productId: $productId, clickId: $clickId) {
    shortUrl
    originalUrl
  }
}
"""


class ShopeeProvider:
    """Provider for the Shopee Affiliate Program (GraphQL API).

    Implements the AffiliateProvider protocol. Gracefully returns
    empty results when credentials are not configured.
    """

    name = "Shopee"
    network_id = AffiliateNetwork.SHOPEE.value

    def __init__(self, config: ShopeeConfig) -> None:
        self._config = config
        self._client: httpx.Client | None = None

    # ── Protocol conformance ───────────────────────────────────────────

    def is_configured(self) -> bool:
        return self._config.is_configured()

    def search_products(
        self,
        keyword: str,
        category_id: str | None = None,
        max_results: int = 10,
    ) -> list[AffiliateProduct]:
        if not self.is_configured():
            return []

        variables: dict[str, Any] = {
            "keyword": keyword,
            "limit": max_results,
        }
        if category_id:
            variables["categoryId"] = category_id

        data = self._query(_PRODUCT_SEARCH_QUERY, variables)
        products_raw = (
            data.get("productSearch", {}).get("products", []) if isinstance(data, dict) else []
        )
        return self._parse_products(products_raw)

    def get_categories(self) -> list[dict]:
        if not self.is_configured():
            return []
        data = self._query(_CATEGORY_LIST_QUERY)
        items = data.get("categoryList", []) if isinstance(data, dict) else []
        return [
            {
                "id": str(c.get("categoryId", "")),
                "name": c.get("categoryName", ""),
                "parent_id": str(c.get("parentId", "")),
            }
            for c in items
        ]

    def get_commission(self, product_id: str) -> float:
        if not self.is_configured():
            return 0.0
        data = self._query(_COMMISSION_QUERY, {"productId": product_id})
        commission_data = data.get("productCommission", {}) if isinstance(data, dict) else {}
        rate = float(commission_data.get("commissionRate", 0.0))
        return rate

    def generate_link(self, product_id: str) -> str:
        if not self.is_configured():
            return ""
        click_id = f"fanpage-{int(time.time())}"
        data = self._mutation(
            _LINK_GENERATION_MUTATION,
            {"productId": product_id, "clickId": click_id},
        )
        link_data = data.get("generateLink", {}) if isinstance(data, dict) else {}
        return str(link_data.get("shortUrl", ""))

    # ── GraphQL execution ──────────────────────────────────────────────

    def _query(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query."""
        return self._execute(query, variables)

    def _mutation(self, mutation: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL mutation."""
        return self._execute(mutation, variables)

    def _execute(self, query: str, variables: dict | None = None) -> dict:
        """Send a GraphQL request to Shopee Affiliate API."""
        if not self.is_configured():
            return {}

        body = {"query": query}
        if variables:
            body["variables"] = variables

        body_json = json.dumps(body, separators=(",", ":"))
        timestamp = str(int(time.time()))
        signature = self._sign(body_json, timestamp)

        try:
            client = self._get_client()
            resp = client.post(
                "",
                content=body_json,
                headers={
                    "Content-Type": "application/json",
                    "X-APP-ID": self._config.app_id,
                    "X-Timestamp": timestamp,
                    "X-Signature": signature,
                },
            )
            resp.raise_for_status()
            result_raw = resp.json()
            result: dict = result_raw if isinstance(result_raw, dict) else {}
            if "errors" in result:
                logger.warning("Shopee GraphQL errors: %s", result["errors"])
                return {}
            return result.get("data", {})
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Shopee GraphQL request failed (%s): %s",
                exc.response.status_code,
                exc,
            )
        except Exception as exc:
            logger.warning("Shopee GraphQL request error: %s", exc)
        return {}

    # ── Auth helpers ───────────────────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self._config.base_url,
                timeout=_REQUEST_TIMEOUT,
            )
        return self._client

    def _sign(self, body: str, timestamp: str) -> str:
        """Generate HMAC-SHA256 signature for Shopee API.

        Signature = HMAC-SHA256(
            secret_key,
            f"{app_id}{timestamp}{body_hash}"
        )
        """
        body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        message = f"{self._config.app_id}{timestamp}{body_hash}"
        return hmac.new(
            self._config.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    # ── Response parsing ───────────────────────────────────────────────

    def _parse_products(self, raw_list: list[dict]) -> list[AffiliateProduct]:
        """Convert Shopee API product list into AffiliateProduct list."""
        products: list[AffiliateProduct] = []
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue

            pid = str(raw.get("productId", ""))
            name = str(raw.get("productName", ""))
            if not pid or not name:
                continue

            commission_rate = float(raw.get("commissionRate", raw.get("commission", 0.0)))
            # Shopee returns commission_rate as decimal (e.g. 0.10 = 10%)
            commission_pct = commission_rate * 100

            products.append(
                AffiliateProduct(
                    product_id=pid,
                    product_name=name.strip(),
                    network=AffiliateNetwork.SHOPEE.value,
                    category=str(raw.get("categoryName", "")),
                    price=self._to_float(raw.get("price")),
                    sale_price=self._to_float(raw.get("salePrice")),
                    commission_rate=commission_rate,
                    commission_note=f"Shopee {commission_pct:.1f}%",
                    affiliate_url=str(raw.get("affiliateUrl", "")),
                    image_url=str(raw.get("imageUrl", "")),
                    product_url=str(raw.get("productUrl", "")),
                    currency=str(raw.get("currency", "VND")),
                    metadata={
                        "original_price": raw.get("price"),
                        "sale_price_raw": raw.get("salePrice"),
                    },
                )
            )
        return products

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
