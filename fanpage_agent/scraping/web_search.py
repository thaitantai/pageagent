from __future__ import annotations

import logging
from typing import Any

from fanpage_agent.throttle import TokenBucket
from fanpage_agent.audit import audit

logger = logging.getLogger(__name__)

# DuckDuckGo max results per request
DDG_MAX_RESULTS = 20

# Rate limit: max 15 searches / 60 s (DDG is aggressive on 429)
DDG_LIMIT_CAPACITY = 15
DDG_LIMIT_WINDOW = 60.0


class SearchResult:
    """Kết quả tìm kiếm web đơn giản."""

    __slots__ = ("title", "url", "snippet")

    def __init__(self, title: str, url: str, snippet: str = "") -> None:
        self.title = title
        self.url = url
        self.snippet = snippet

    def to_dict(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


class WebSearchClient:
    """Web search client dùng DuckDuckGo (free, không cần API key).

    Sử dụng thư viện ``ddgs`` (DuckDuckGo Search SDK).
    Fallback: nếu SDK lỗi, dùng httpx/urllib để scrape HTML trực tiếp.

    Rate-limited to {DDG_LIMIT_CAPACITY} requests / {DDG_LIMIT_WINDOW}s.
    """

    def __init__(self, region: str = "vn-vn", safesearch: str = "moderate", timeout: int = 15):
        self.region = region
        self.safesearch = safesearch
        self.timeout = timeout
        self._limiter = TokenBucket(capacity=DDG_LIMIT_CAPACITY, window_sec=DDG_LIMIT_WINDOW)

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search DuckDuckGo, return list of SearchResult."""
        if max_results > DDG_MAX_RESULTS:
            max_results = DDG_MAX_RESULTS

        # Acquire rate-limit token before each request
        self._limiter.acquire(tokens=1.0)

        with audit(
            event_type="web.search",
            source="WebSearchClient",
            query=query[:200],
        ) as actx:
            try:
                results = self._search_ddg_sdk(query, max_results)
                actx["data"]["count"] = len(results)
                actx["data"]["method"] = "sdk"
                return results
            except Exception as exc:
                logger.warning("WebSearch: DDG SDK failed (%s), trying fallback...", exc)
                try:
                    results = self._search_ddg_html(query, max_results)
                    actx["data"]["count"] = len(results)
                    actx["data"]["method"] = "html_fallback"
                    return results
                except Exception as exc2:
                    logger.warning("WebSearch: fallback also failed: %s", exc2)
                    actx["data"]["count"] = 0
                    actx["data"]["method"] = "failed"
                    return []

    def search_multiple(
        self, queries: list[str], max_per_query: int = 5, dedup: bool = True
    ) -> list[SearchResult]:
        """Search nhiều query, gộp kết quả (dedup theo URL)."""
        seen: set[str] = set()
        results: list[SearchResult] = []
        for q in queries:
            try:
                batch = self.search(q, max_results=max_per_query)
                for r in batch:
                    if dedup and r.url in seen:
                        continue
                    seen.add(r.url)
                    results.append(r)
            except Exception as exc:
                logger.warning("WebSearch: query '%s' failed: %s", q[:60], exc)
        return results

    # ------------------------------------------------------------------
    # DuckDuckGo SDK (ddgs)
    # ------------------------------------------------------------------

    def _search_ddg_sdk(self, query: str, max_results: int) -> list[SearchResult]:
        from ddgs import DDGS

        with DDGS() as ddgs:
            raw = list(
                ddgs.text(
                    query,
                    region=self.region,
                    safesearch=self.safesearch,
                    max_results=max_results,
                )
            )
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("href", ""),
                snippet=r.get("body", ""),
            )
            for r in raw
            if r.get("href")
        ]

    # ------------------------------------------------------------------
    # Fallback: scrape DuckDuckGo HTML trực tiếp (khi SDK lỗi)
    # ------------------------------------------------------------------

    def _search_ddg_html(self, query: str, max_results: int) -> list[SearchResult]:
        import urllib.parse
        import urllib.request

        url = (
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        return self._parse_ddg_html(html, max_results)

    @staticmethod
    def _parse_ddg_html(html: str, max_results: int) -> list[SearchResult]:
        """Parse DuckDuckGo HTML response, extract search results."""
        import re

        results: list[SearchResult] = []
        # Pattern: <a rel="nofollow" class="result__a" href="...">title</a>
        #       + <a class="result__snippet" ...>snippet</a>
        link_pattern = re.compile(
            r'<a\s+rel="nofollow"\s+class="result__a"\s+href="([^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'<a\s+class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL
        )

        links = link_pattern.findall(html)
        snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippet_pattern.findall(html)]

        for i, (url, title) in enumerate(links[:max_results]):
            if not url:
                continue
            snip = snippets[i] if i < len(snippets) else ""
            results.append(
                SearchResult(
                    title=re.sub(r"<[^>]+>", "", title).strip(),
                    url=url,
                    snippet=snip,
                )
            )

        return results
