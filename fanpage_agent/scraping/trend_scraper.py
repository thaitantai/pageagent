from __future__ import annotations

import logging

from scrapling.fetchers import Fetcher

from fanpage_agent.models import TrendItem
from fanpage_agent.scraping.multi_source_search import MultiSourceSearchClient

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

# Mặc định: các query tìm kiếm trend skincare/healthcare cho GenZ
DEFAULT_TREND_QUERIES: list[str] = [
    "xu hướng chăm sóc da 2026",
    "skincare routine mới nhất",
    "dưỡng da mùa hè Gen Z",
    "mẹo làm đẹp an toàn cho da dầu mụn",
    "sản phẩm dưỡng da hot nhất hiện nay",
    "thực phẩm chức năng làm đẹp da uy tín",
    "review kem chống nắng tốt nhất 2026",
    "treatment da mụn hiệu quả tại nhà",
]

# Số URL tối đa scrape mỗi query
MAX_SEARCH_URLS_PER_QUERY = 5
# Số TrendItem tối đa scrape từ mỗi URL
MAX_ITEMS_PER_URL = 5
# Tổng items tối đa từ web search
MAX_SEARCH_ITEMS_TOTAL = 30


class TrendScraper:
    """Quét trend từ web dùng Scrapling framework.

    - Dùng Fetcher (requests + TLS impersonation) cho trang tĩnh.
    - parse CSS selector/XPath → trích xuất tiêu đề, link, snippet.
    - Hỗ trợ web search (DuckDuckGo) + Scrapling scrape dynamic content.
    """

    def __init__(
        self,
        sources: list[dict[str, str]] | None = None,
        timeout: int = 15,
        web_search: MultiSourceSearchClient | None = None,
    ):
        self.sources = sources or DEFAULT_TREND_SOURCES
        self.timeout = timeout
        self._web_search = web_search or MultiSourceSearchClient()

    # ------------------------------------------------------------------
    # Existing API (kế thừa)
    # ------------------------------------------------------------------

    def fetch_all(self) -> list[TrendItem]:
        """Quét tất cả nguồn cố định, trả về danh sách TrendItem."""
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
    # NEW: Web Search → Scrape pipeline
    # ------------------------------------------------------------------

    def search_trends(
        self,
        queries: list[str] | None = None,
        max_results_per_query: int | None = None,
        max_articles: int | None = None,
    ) -> list[TrendItem]:
        """Search web → tìm URL → scrape content → trả về TrendItem.

        Flow:
          Search DuckDuckGo (query)
            → list SearchResult (title, url, snippet)
            → Scrapling fetch từng URL + get_all_text()
            → TrendItem với title, source, url, snippet

        Parameters
        ----------
        queries : list[str] | None
            Các query cần search. Mặc định: DEFAULT_TREND_QUERIES.
        max_results_per_query : int | None
            Số URL tối đa lấy từ mỗi query. Mặc định: 5.
        max_articles : int | None
            Tổng items tối đa trả về. Mặc định: 30.
        """
        queries = queries or DEFAULT_TREND_QUERIES
        max_per_q = max_results_per_query or MAX_SEARCH_URLS_PER_QUERY
        max_total = max_articles or MAX_SEARCH_ITEMS_TOTAL

        # Phase 1: Search → tìm URL
        search_results = self._web_search.search_multiple(
            queries, max_per_query=max_per_q, dedup=True
        )
        if not search_results:
            logger.info("TrendScraper: web search không có kết quả.")
            return []

        logger.info(
            "TrendScraper: web search tìm được %d URL từ %d queries",
            len(search_results),
            len(queries),
        )

        # Phase 2: Scrape từng URL
        trends: list[TrendItem] = []
        for sr in search_results:
            if len(trends) >= max_total:
                break
            try:
                # Dùng Fetcher tải trang + get_all_text()
                page = Fetcher.get(sr.url, timeout=self.timeout)
                if page.status != 200:
                    logger.debug("TrendScraper: %s HTTP %d, skip", sr.url, page.status)
                    continue

                raw_text = page.get_all_text().strip()

                # Tách thành các đoạn văn có nghĩa
                paragraphs = [p.strip() for p in raw_text.split("\n") if len(p.strip()) > 50]
                if not paragraphs:
                    # Fallback: dùng snippet từ search
                    if sr.snippet:
                        trends.append(
                            TrendItem(
                                title=sr.title,
                                source=f"web:{sr.url[:40]}",
                                url=sr.url,
                                snippet=sr.snippet[:300],
                            )
                        )
                    continue

                # Tạo TrendItem từ các đoạn đầu tiên
                for i, para in enumerate(paragraphs[:MAX_ITEMS_PER_URL]):
                    if len(trends) >= max_total:
                        break
                    trends.append(
                        TrendItem(
                            title=sr.title if i == 0 else para[:100] + "...",
                            source=f"web:{sr.url[:35]}",
                            url=sr.url,
                            snippet=para[:500],
                        )
                    )

            except Exception as exc:
                logger.debug("TrendScraper: skip URL %s — %s", sr.url[:50], exc)
                # Vẫn dùng snippet từ search nếu có
                if sr.snippet:
                    trends.append(
                        TrendItem(
                            title=sr.title,
                            source=f"web:{sr.url[:40]}",
                            url=sr.url,
                            snippet=sr.snippet[:300],
                        )
                    )

        logger.info(
            "TrendScraper: search_trends → %d TrendItem từ %d URL",
            len(trends),
            len(search_results),
        )
        return trends

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
