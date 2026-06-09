#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import re
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Data types ─────────────────────────────────────────────────


@dataclass
class SearchResult:
    """Kết quả tìm kiếm với metadata backend."""
    title: str
    url: str
    snippet: str = ""
    engine: str = ""       # "searxng", "ddg", "vn_crawler"
    source_site: str = ""  # tên site gốc (VD: wecommit.vn)
    score: float = 0.5     # trust score 0-1


# ── Abstract backend ──────────────────────────────────────────


class SearchBackend(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        ...

    @property
    @abstractmethod
    def name(self) -> str: ...


# ── SearXNG Backend ───────────────────────────────────────────


class SearXNGBackend(SearchBackend):
    """Search qua SearXNG self-hosted (http://localhost:8899)."""

    def __init__(self, base_url: str = "http://localhost:8899", timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "searxng"

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        import httpx

        params: dict[str, Any] = {
            "q": query,
            "format": "json",
            "language": "vi",
            "categories": "general",
            "pageno": 1,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.base_url}/search", params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("SearXNG backend thất bại [%s]: %s", query[:40], exc)
            return []

        results: list[SearchResult] = []
        for item in data.get("results", [])[:max_results]:
            url = item.get("url", "")
            if not url:
                continue
            results.append(SearchResult(
                title=item.get("title", ""),
                url=url,
                snippet=item.get("content", ""),
                engine="searxng",
                source_site=urllib.parse.urlparse(url).netloc,
                score=0.55,  # base: SearXNG aggregate
            ))
        return results


# ── DuckDuckGo Backend (fallback) ─────────────────────────────


class DDGBackend(SearchBackend):
    """DuckDuckGo search — fallback khi SearXNG không trả kết quả."""

    def __init__(self, region: str = "vn-vn", timeout: int = 15):
        self.region = region
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "ddg"

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                raw = list(ddgs.text(
                    query, region=self.region,
                    safesearch="moderate", max_results=max_results,
                ))
        except Exception as exc:
            logger.warning("DDG backend thất bại [%s]: %s", query[:40], exc)
            return []

        results: list[SearchResult] = []
        for r in raw:
            url = r.get("href", "")
            if not url:
                continue
            results.append(SearchResult(
                title=r.get("title", ""),
                url=url,
                snippet=r.get("body", ""),
                engine="ddg",
                source_site=urllib.parse.urlparse(url).netloc,
                score=0.50,
            ))
        return results


# ── VN Crawler Backend ────────────────────────────────────────


_CACHE_TTL_SEC = 3600  # refresh cache mỗi giờ

# URL patterns bỏ qua (nav, utility, social)
_SKIP_HREF_PATTERNS = re.compile(
    r"^(#|javascript:|tel:|mailto:|whatsapp:|fb\.me|zalo)", re.IGNORECASE
)
# Keywords trong URL cho thấy đây là article/product content
_CONTENT_HREF_KEYWORDS = re.compile(
    r"/(bai-viet|tin-tuc|blog|news|article|san-pham|product|"
    r"chuyen-muc|danh-muc|category|tag|"
    r"[\w-]+-\d{4,})$",
    re.IGNORECASE,
)


@dataclass
class _CrawledSite:
    name: str
    url: str
    last_fetch: datetime | None = None
    articles: list[SearchResult] = field(default_factory=list)


class VNCrawlerBackend(SearchBackend):
    """Crawl nội dung từ các trang VN chuyên ngành health/beauty.

    Dùng BeautifulSoup để parse HTML thay vì regex — xử lý được
    CSS-in-JS (Next.js) và cấu trúc HTML phức tạp.

    Cache kết quả 1 giờ — không crawl lại mỗi query.
    """

    SITES: list[dict[str, str]] = [
        {"name": "Hello Bacsi", "url": "https://hellobacsi.com/"},
        {"name": "Chiaki", "url": "https://chiaki.vn/"},
        {"name": "Sức khỏe Đời sống", "url": "https://suckhoedoisong.vn/"},
        {"name": "Nhà thuốc Long Châu", "url": "https://nhathuoclongchau.com.vn/"},
        {"name": "Medlatec", "url": "https://medlatec.vn/"},
    ]

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self._sites: list[_CrawledSite] = [
            _CrawledSite(name=s["name"], url=s["url"])
            for s in self.SITES
        ]

    @property
    def name(self) -> str:
        return "vn_crawler"

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        self._refresh_cache()
        # Extract keywords from query
        keywords = {w.lower() for w in _WORD_RE.findall(query) if len(w) >= 3}

        candidates: list[SearchResult] = []
        for site in self._sites:
            for art in site.articles:
                title_keywords = {w.lower() for w in _WORD_RE.findall(art.title)}
                overlap = len(keywords & title_keywords) if keywords else 0
                if overlap > 0:
                    boosted = SearchResult(
                        title=art.title, url=art.url, snippet=art.snippet,
                        engine="vn_crawler", source_site=site.name,
                        score=min(1.0, art.score + overlap * 0.1),
                    )
                    candidates.append(boosted)
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[:max_results]

    def _refresh_cache(self) -> None:
        now = datetime.now(timezone.utc)
        for site in self._sites:
            if site.last_fetch and (now - site.last_fetch).total_seconds() < _CACHE_TTL_SEC:
                continue
            try:
                site.articles = self._fetch_site(site.url)
                site.last_fetch = now
                logger.info("VNCrawler: refresh %s → %d articles", site.name, len(site.articles))
            except Exception as exc:
                logger.warning("VNCrawler: fetch %s thất bại: %s", site.url, exc)

    def _fetch_site(self, url: str) -> list[SearchResult]:
        """Fetch trang chủ, trích xuất link bài viết bằng BeautifulSoup."""
        try:
            from scrapling import Fetcher
            page = Fetcher.get(url, timeout=self.timeout)
            if page.status != 200:
                return []
            html = str(page.html_content)
        except Exception as exc:
            logger.debug("VNCrawler: Fetcher %s — %s", url[:40], exc)
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        all_links = soup.find_all("a", href=True)

        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for a_tag in all_links:
            raw_href = a_tag.get("href", "")
            href = str(raw_href).strip() if raw_href else ""
            # Skip nav/utility links
            if _SKIP_HREF_PATTERNS.match(href):
                continue
            # Get clean text (strip all inner markup)
            title = a_tag.get_text(separator=" ", strip=True)
            if not title or len(title) < 20:
                continue
            # Skip links với title chỉ là số/icon/emoji
            text_len = len(re.sub(r"[\s\u2000-\u206F\uFE00-\uFE0F\U0001F300-\U0001FFFF]+", "", title))
            if text_len < 12:
                continue

            link = href
            if link.startswith("//"):
                link = "https:" + link
            elif link.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                link = f"{parsed.scheme}://{parsed.netloc}{link}"
            elif not link.startswith("http"):
                continue  # skip relative/protocol-relative non-http

            if link in seen_urls:
                continue
            seen_urls.add(link)

            # Normalise whitespace trong title
            title = re.sub(r"\s+", " ", title).strip()
            results.append(SearchResult(
                title=title,
                url=link,
                snippet="",
                engine="vn_crawler",
                source_site=urllib.parse.urlparse(url).netloc,
                score=0.70,
            ))

        return results


_WORD_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)


# ── MultiSourceSearchClient ────────────────────────────────────


class MultiSourceSearchClient:
    """Kết hợp nhiều search backends, merge + dedup + score kết quả.

    Strategy:
      - Chạy **tất cả** backends song song (hoặc tuần tự)
      - Merge results, dedup URL
      - Score mỗi result (có bonus cho VN site, phạt cho source quen thuộc)
      - Sort by score → return top N

    Fallback: nếu SearXNG + VN crawler cho < 3 URLs, thêm DDG.
    """

    def __init__(
        self,
        searxng_base_url: str = "http://localhost:8899",
        timeout: int = 15,
    ):
        self.timeout = timeout
        self._backends: list[SearchBackend] = [
            SearXNGBackend(base_url=searxng_base_url, timeout=timeout),
            VNCrawlerBackend(timeout=timeout),
            DDGBackend(timeout=timeout),
        ]

    def search_multiple(
        self,
        queries: list[str],
        max_per_query: int = 5,
        dedup: bool = True,
    ) -> list[SearchResult]:
        """Search multi queries + backends → merged sorted results."""
        all_results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for q in queries:
            batch: list[SearchResult] = []
            for backend in self._backends:
                if not q.strip():
                    continue
                try:
                    res = backend.search(q, max_results=max_per_query)
                    batch.extend(res)
                except Exception as exc:
                    logger.debug("Backend %s query [%s]: %s", backend.name, q[:40], exc)

            # Dedup & add
            for r in batch:
                if dedup and r.url in seen_urls:
                    continue
                seen_urls.add(r.url)
                all_results.append(r)

        # Sort: score desc, then VN crawler first, then recent-ish
        all_results.sort(key=lambda r: (-r.score, r.engine != "vn_crawler", r.title))

        # Gắn rank-based score boost (result ở vị trí đầu → cao hơn)
        for i, r in enumerate(all_results):
            position_boost = max(0.0, 1.0 - i * 0.02)
            r.score = round((r.score + position_boost) / 2, 3)

        all_results.sort(key=lambda r: -r.score)
        return all_results

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Single query search (compatible với WebSearchClient interface)."""
        results = self.search_multiple([query], max_per_query=max_results, dedup=True)
        return results[:max_results]
