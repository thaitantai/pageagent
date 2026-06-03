from __future__ import annotations

import logging
from typing import List

from scrapling.fetchers import Fetcher

from fanpage_agent.models import TrendItem

logger = logging.getLogger(__name__)

# Mặc định: các nguồn trend cho skincare/healthcare GenZ
# Đã verify thực tế — CSS selector chính xác cho từng site
DEFAULT_TREND_SOURCES: list[dict[str, str]] = [
    {
        "name": "VnExpress - Sức khỏe",
        "url": "https://vnexpress.net/suc-khoe",
        "selector": "h3.title-news a",
    },
    {
        "name": "24h - Làm đẹp",
        "url": "https://www.24h.com.vn/lam-dep-c145.html",
        "selector": "h3 a",
    },
    {
        "name": "24h - Sức khỏe",
        "url": "https://www.24h.com.vn/suc-khoe-c62.html",
        "selector": "h3 a",
    },
    {
        "name": "Afamily - Sức khỏe",
        "url": "https://afamily.vn/suc-khoe.chn",
        "selector": "h3 a",
    },
]


class TrendScraper:
    """Quét trend từ web dùng Scrapling framework.

    - Dùng Fetcher (requests + TLS impersonation) cho trang tĩnh.
    - parse CSS selector/XPath → trích xuất tiêu đề, link, snippet.
    """

    def __init__(self, sources: list[dict[str, str]] | None = None, timeout: int = 15):
        self.sources = sources or DEFAULT_TREND_SOURCES
        self.timeout = timeout

    def fetch_all(self) -> list[TrendItem]:
        """Quét tất cả nguồn, trả về danh sách TrendItem."""
        trends: list[TrendItem] = []
        for source in self.sources:
            try:
                items = self._fetch_source(source)
                trends.extend(items)
            except Exception as exc:
                logger.warning("TrendScraper: bỏ qua nguồn '%s' — %s", source.get("name", "?"), exc)
        return trends

    def fetch(self, url: str, name: str = "custom", selector: str = "") -> list[TrendItem]:
        """Quét một URL bất kỳ.

        Parameters
        ----------
        url : str
            URL cần quét.
        name : str
            Tên nguồn (mặc định "custom").
        selector : str
            CSS selector để trích xuất item (mặc định "" → fallback text splitting).
        """
        source = {"name": name, "url": url, "selector": selector}
        return self._fetch_source(source)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_source(self, source: dict[str, str]) -> list[TrendItem]:
        name = source.get("name", "?")
        url = source.get("url", "")
        selector = source.get("selector", "")

        if not url:
            return []

        page = Fetcher.get(url, timeout=self.timeout)
        if page.status != 200:
            logger.warning("TrendScraper: %s trả về HTTP %s", name, page.status)
            return []

        items: list[TrendItem] = []

        # — 1. CSS selector cụ thể (ưu tiên)
        if selector:
            elements = page.css(selector)
            for el in elements[:20]:
                title = (el.css("::text").get() or "").strip()
                link = el.css("::attr(href)").get() or ""
                if title:
                    items.append(TrendItem(title=title, source=name, url=link, snippet=""))

        # — 2. fallback: lấy text toàn trang + split thành đoạn
        if not items:
            raw = page.get_all_text().strip()
            paragraphs = [p.strip() for p in raw.split("\n") if len(p.strip()) > 30]
            for i, para in enumerate(paragraphs[:10]):
                items.append(
                    TrendItem(
                        title=para[:120],
                        source=name,
                        url="",
                        snippet=para[:300],
                    )
                )
            if items:
                logger.info("TrendScraper: fallback text-mode cho %s — %d items", name, len(items))

        return items
