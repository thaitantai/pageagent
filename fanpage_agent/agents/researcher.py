"""ResearchAgent — web research using Scrapling for content brief generation.

Auto-discovers new articles from RSS feeds and category pages each tick.
Falls back to known-good URLs when discovery yields nothing.

v3 enhancements (Jun 2026):
  - Auto-discover: RSS feed parsing + category page link extraction
  - No more fixed URL lists — discovers fresh content each tick
  - Seen-articles tracker to avoid re-crawling across ticks
  - Graceful fallback chain: discover → cache → fallback URLs
"""

from __future__ import annotations

import json
import random
import re
import time
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from fanpage_agent.core.agent import BaseAgent
from fanpage_agent.core.types import ActionPriority, AgentResult, AgentRole, AgentTask

warnings.filterwarnings(
    "ignore",
    message=r"The 'strip_cdata' option.*",
    category=DeprecationWarning,
)


# ── Discovery sources ─────────────────────────────────────
# RSS feeds — parse to discover new articles automatically
RSS_FEEDS: dict[str, list[str]] = {
    "skincare_routine": [
        "https://www.healthline.com/rss/beauty-skin-care",
        "https://suckhoedoisong.vn/cham-soc-da/rss.rss",
        "https://kenh14.vn/rss/home.rss",
    ],
    "ingredient_deepdive": [
        "https://www.healthline.com/rss/beauty-skin-care",
        "https://suckhoedoisong.vn/lam-dep/rss.rss",
    ],
    "myth_busting": [
        "https://www.healthline.com/rss/beauty-skin-care",
        "https://suckhoedoisong.vn/khoe-dep/rss.rss",
    ],
    "product_review": [
        "https://www.byrdie.com/rss.xml",
        "https://www.healthline.com/rss/beauty-skin-care",
        "https://kenh14.vn/rss/home.rss",
    ],
    "genz_lifestyle": [
        "https://www.byrdie.com/rss.xml",
        "https://kenh14.vn/rss/home.rss",
    ],
    "medical_reference": [
        "https://www.healthline.com/rss/beauty-skin-care",
        "https://www.healthline.com/rss/skin-disorders",
        "https://suckhoedoisong.vn/khoe-dep/rss.rss",
    ],
}

# Category pages — crawl to extract article links
CATEGORY_SOURCES: dict[str, list[str]] = {
    "skincare_routine": [
        "https://hellobacsi.com/da-lieu/cham-soc-da/",
        "https://suckhoedoisong.vn/cham-soc-da/",
        "https://kenh14.vn/lam-dep.html",
        "https://eva.vn/dep-c58.html",
    ],
    "ingredient_deepdive": [
        "https://hellobacsi.com/da-lieu/thanh-phan-my-pham/",
        "https://nhathuoclongchau.com.vn/bai-viet",
        "https://suckhoedoisong.vn/lam-dep/",
    ],
    "myth_busting": [
        "https://suckhoedoisong.vn/lam-dep/",
        "https://eva.vn/tips-lam-dep-p1251c58.html",
    ],
    "product_review": [
        "https://hellobacsi.com/da-lieu/san-pham/",
        "https://nhathuoclongchau.com.vn/bai-viet",
        "https://kenh14.vn/lam-dep.html",
        "https://eva.vn/dep-c58.html",
    ],
    "genz_lifestyle": [
        "https://hellobacsi.com/song-khoe/cham-soc-dep/",
        "https://kenh14.vn/lam-dep.html",
        "https://eva.vn/lam-dep-moi-ngay-c291.html",
    ],
    "medical_reference": [
        "https://hellobacsi.com/da-lieu/",
        "https://nhathuoclongchau.com.vn/bai-viet",
        "https://suckhoedoisong.vn/khoe-dep/",
    ],
}

# Fallback — known-good article URLs used only when discovery yields nothing
FALLBACK_SOURCES: dict[str, list[str]] = {
    "skincare_routine": [
        "https://suckhoedoisong.vn/quy-trinh-cham-soc-da-co-ban-cho-nguoi-moi-bat-dau-169230316.htm",
        "https://nhathuoclongchau.com.vn/bai-viet/cham-soc-da-mat-dung-cach-tai-nha.html",
        "https://www.healthline.com/health/beauty-skin-care/skin-care-routine",
        "https://eva.vn/dep/cach-cham-soc-da-mat-dung-cach-theo-tung-loai-da-c58a616833.html",
    ],
    "ingredient_deepdive": [
        "https://suckhoedoisong.vn/retinol-va-nhung-dieu-can-biet-khi-su-dung-169220801.htm",
        "https://nhathuoclongchau.com.vn/bai-viet/vitamin-c-cho-da-mat-loi-ich-va-cach-dung.html",
        "https://www.healthline.com/health/beauty-skin-care/skin-care-ingredients-explained",
        "https://eva.vn/dep/retinol-la-gi-tac-dung-cua-retinol-trong-cham-soc-da-c58a616822.html",
    ],
    "myth_busting": [
        "https://www.healthline.com/health/beauty-skin-care/skin-care-myths-debunked",
        "https://www.healthline.com/health/beauty-skin-care/myths",
        "https://suckhoedoisong.vn/nhung-quan-niem-sai-lam-ve-cham-soc-da-169231025.htm",
    ],
    "product_review": [
        "https://suckhoedoisong.vn/top-5-kem-chong-nang-tot-nhat-cho-da-dau-mun-169230408.htm",
        "https://www.byrdie.com/best-sunscreens-for-face-4687968",
        "https://kenh14.vn/top-kem-chong-nang-tot-nhat-2026.htm",
    ],
    "genz_lifestyle": [
        "https://www.healthline.com/health/beauty-skin-care/skincare-tips-for-teens",
        "https://www.byrdie.com/teen-skincare-routine-5186912",
        "https://kenh14.vn/genz-skincare-routine-don-gian.htm",
    ],
    "medical_reference": [
        "https://suckhoedoisong.vn/phac-do-dieu-tri-mun-trung-ca-theo-y-hoc-169230622.htm",
        "https://nhathuoclongchau.com.vn/bai-viet/cach-phan-biet-cac-loai-mun-thuong-gap.html",
        "https://www.healthline.com/health/skin/acne",
        "https://www.healthline.com/health/beauty-skin-care/how-to-get-rid-of-acne-scars",
        "https://nhathuoclongchau.com.vn/bai-viet/dieu-tri-mun-trung-ca.html",
    ],
}

# Time to wait between fetches (seconds)
REQUEST_DELAY = 1.5

# TTL for cached content (seconds = 24 hours)
CACHE_TTL = 24 * 3600

# Max articles to crawl per pillar per tick
MAX_URLS_PER_PILLAR_PER_TICK = 2

# Max articles to discover per pillar per tick (from RSS + category pages)
MAX_DISCOVER_PER_PILLAR = 10

# Max seen-articles before cleanup
MAX_SEEN_ARTICLES = 5000


class ResearchAgent(BaseAgent):
    """Research agent — scrapes public web sources for content intelligence.

    Uses Scrapling's Fetcher (HTTP requests with TLS fingerprint spoofing)
    to bypass basic anti-bot protections on public blogs.

    Auto-discovers new articles from RSS feeds and category pages each tick.
    Falls back to known-good URLs when discovery yields nothing.

    Two extraction modes:
      1. LLM mode (default if LLMAdapter available) — DeepSeek extracts findings
      2. Heuristic mode (fallback) — keyword + headline pattern matching

    Features:
      - Auto-discover: RSS feed parsing + category page link extraction
      - In-memory TTL cache: avoids re-fetching same URL within 6 hours
      - Seen-articles tracker: never re-crawls the same article across ticks
      - Discovery cooldown: doesn't re-fetch RSS/category pages too frequently
      - Polite delay (1.5s) between fetches
      - Graceful fallback chain: discover -> cache -> fallback URLs
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        sources: dict[str, list[str]] | None = None,
        max_articles_per_pillar: int = 2,
        llm=None,
    ) -> None:
        super().__init__(config)
        # sources param kept for backward compat — used as fallback only now
        self._fallback = sources or FALLBACK_SOURCES
        self._max_per_pillar = max_articles_per_pillar
        self._scrapling_available = False
        self._llm = llm

        # ── In-memory TTL cache ──
        self._cache: dict[str, dict] = {}

        # ── Seen-articles tracker (persists across ticks) ──
        self._seen_articles: set[str] = set()

        # ── Discovery cache (avoids re-pinging RSS/category pages too often) ──
        # {source_url: {"last_fetched": float, "success": bool}}
        self._discovery_cache: dict[str, dict] = {}

        # Discovery cooldown: don't re-fetch RSS/category pages within 30 min
        self._discovery_cooldown = 30 * 60

    @property
    def role(self) -> AgentRole:
        return AgentRole.RESEARCHER

    @property
    def capabilities(self) -> list[str]:
        return ["research_trends", "crawl_source", "get_source_list"]

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params

        if action == "research_trends":
            result = self._research_trends(
                pillars=params.get("pillars", list(self._get_all_pillars())),
            )
            if result.success:
                self._mark_shared_done(
                    brief=result.data.get("brief", {}),
                    source_count=result.data.get("source_count", 0),
                    finding_count=result.data.get("finding_count", 0),
                )
                # Clear pipeline trigger so next tick doesn't re-trigger
                if self._bus:
                    self._bus.shared_state["pipeline_trigger"] = False
            return result
        elif action == "crawl_source":
            return self._crawl_source(params.get("url", ""))
        elif action == "get_source_list":
            return self._get_source_list()
        return AgentResult(
            task_id=task.id, success=False, error=f"Unknown action: {action}"
        )

    def self_driving_tick(self) -> list[tuple[str, dict, ActionPriority]]:
        """Propose research every 2 hours, or when pipeline trigger is active."""
        proposals: list[tuple[str, dict, ActionPriority]] = []
        if self._should_pipeline_act("research_trends", 7200):
            proposals.append(("research_trends", {"pillars": []}, ActionPriority.MEDIUM))
        return proposals

    # ── Public API ────────────────────────────────────────────────

    def _get_all_pillars(self) -> set[str]:
        """Get the union of all pillar names from all source dicts."""
        pillars: set[str] = set()
        for d in (self._fallback, RSS_FEEDS, CATEGORY_SOURCES):
            for k in d:
                pillars.add(k)
        return pillars

    def _research_trends(self, pillars: list[str]) -> AgentResult:
        """Crawl research sources and return structured brief.

        Pipeline for each pillar:
          1. Auto-discover new articles from RSS feeds + category pages
          2. Filter out already-seen articles
          3. Mark new articles as seen
          4. Crawl a subset (up to max_per_pillar)
          5. If no new articles discovered this tick, rotate through fallback pool
          6. Extract findings from fetched content
        """
        self._ensure_scrapling()
        brief: dict[str, Any] = {
            "sources_checked": [],
            "findings": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "discovery": {
                "new_articles_discovered": 0,
                "fallback_used": False,
            },
        }

        for pillar in pillars:
            # Step 1: Discover new articles from RSS + category pages
            discovered = self._discover_articles_for_pillar(pillar)
            brief["discovery"]["new_articles_discovered"] += len(discovered)

            # Step 2: Filter unseen and crawl subset
            new_articles = [u for u in discovered if u not in self._seen_articles]
            if new_articles:
                for url in new_articles:
                    self._seen_articles.add(url)

                to_crawl = new_articles[:min(self._max_per_pillar, MAX_URLS_PER_PILLAR_PER_TICK)]

                for url in to_crawl:
                    content = self._fetch_text(url)
                    brief["sources_checked"].append({
                        "url": url,
                        "pillar": pillar,
                        "fetched": content is not None,
                        "length": len(content) if content else 0,
                        "from_cache": self._is_from_cache(url),
                        "from_discovery": True,
                    })
                    if content:
                        extracted = self._extract_findings(content, pillar)
                        brief["findings"].extend(extracted)

            # Step 3: Fallback — if nothing crawled from discovery, use fallback pool
            pillar_fetched = [s for s in brief["sources_checked"]
                              if s["pillar"] == pillar and s["fetched"]]
            if not pillar_fetched:
                fallback_urls = self._fallback.get(pillar, [])
                if fallback_urls:
                    brief["discovery"]["fallback_used"] = True
                    idx = hash(time.asctime()) % len(fallback_urls)
                    urls_to_try = fallback_urls[idx:] + fallback_urls[:idx]
                    tried = 0
                    for url in urls_to_try:
                        if tried >= MAX_URLS_PER_PILLAR_PER_TICK:
                            break
                        if url in self._seen_articles:
                            continue
                        content = self._fetch_text(url)
                        self._seen_articles.add(url)
                        brief["sources_checked"].append({
                            "url": url,
                            "pillar": pillar,
                            "fetched": content is not None,
                            "length": len(content) if content else 0,
                            "from_cache": self._is_from_cache(url),
                            "from_discovery": False,
                        })
                        tried += 1
                        if content:
                            extracted = self._extract_findings(content, pillar)
                            brief["findings"].extend(extracted)

        # ── Nâng cấp dedup: URL + chủ đề tương tự ──────────────
        seen_topics: set[str] = set()
        seen_urls: set[str] = set()
        unique_findings = []
        for f in brief["findings"]:
            key = f.get("topic", "")[:50].lower().strip()
            source_url = f.get("source_url", "") or ""
            # Skip nếu topic hoặc URL đã thấy
            if key and key not in seen_topics and source_url not in seen_urls:
                if key:
                    seen_topics.add(key)
                if source_url:
                    seen_urls.add(source_url)
                unique_findings.append(f)
        brief["findings"] = unique_findings

        # Cleanup seen_articles if too large
        if len(self._seen_articles) > MAX_SEEN_ARTICLES:
            self._seen_articles = set(list(self._seen_articles)[-MAX_SEEN_ARTICLES:])

        return AgentResult(
            task_id="research-trends",
            success=True,
            data={
                "brief": brief,
                "source_count": len(brief["sources_checked"]),
                "finding_count": len(brief["findings"]),
            },
        )

    def _discover_articles_for_pillar(self, pillar: str) -> list[str]:
        """Discover new article URLs for a given pillar.

        Tries (in order):
          1. RSS feeds mapped to this pillar
          2. Category pages mapped to this pillar

        Returns a deduplicated list of article URLs.
        RSS feeds are re-checked every 30 min; category pages every 30 min.
        """
        discovered: list[str] = []

        # 1. RSS feeds
        for feed_url in RSS_FEEDS.get(pillar, []):
            if self._is_discovery_on_cooldown(feed_url):
                continue
            articles = self._parse_rss_feed(feed_url)
            if articles:
                self._update_discovery_cache(feed_url, True)
                for url, title in articles:
                    discovered.append(url)
            else:
                self._update_discovery_cache(feed_url, False)

        # 2. Category pages
        for cat_url in CATEGORY_SOURCES.get(pillar, []):
            if self._is_discovery_on_cooldown(cat_url):
                continue
            articles = self._parse_category_page(cat_url)
            if articles:
                self._update_discovery_cache(cat_url, True)
                for url, title in articles:
                    discovered.append(url)
            else:
                self._update_discovery_cache(cat_url, False)

        # Deduplicate (preserve order)
        return list(dict.fromkeys(discovered))

    # ── RSS parsing ─────────────────────────────────────────────

    def _parse_rss_feed(self, feed_url: str) -> list[tuple[str, str]]:
        """Parse RSS 2.0 or Atom feed, return list of (url, title).

        Uses xml.etree.ElementTree (stdlib, no extra dependency).
        Handles both RSS 2.0 (<rss><channel><item>) and
        Atom (<feed><entry>) formats with and without namespaces.
        """
        raw = self._fetch_raw(feed_url, timeout=10)
        if not raw:
            return []

        articles: list[tuple[str, str]] = []
        try:
            root = ET.fromstring(raw)

            # ── RSS 2.0 ──
            if root.tag == "rss" or root.tag.endswith("}rss"):
                channel = root.find("channel")
                if channel is not None:
                    for item in channel.iter("item"):
                        link = self._get_xml_text(item, "link")
                        title = self._get_xml_text(item, "title")
                        if link and title:
                            articles.append((link.strip(), title.strip()))

            # ── Atom ──
            elif root.tag == "feed" or "feed" in root.tag:
                ns = "http://www.w3.org/2005/Atom"
                tag_entry = f"{{{ns}}}entry" if "{" in root.tag else "entry"
                tag_title = f"{{{ns}}}title" if "{" in root.tag else "title"
                for entry in root.iter(tag_entry):
                    # Atom: <link href="..." />
                    link_elem = entry.find(f"{{{ns}}}link") if "{" in root.tag else entry.find("link")
                    title_elem = entry.find(tag_title)
                    if link_elem is not None and title_elem is not None:
                        href = link_elem.get("href")
                        title = title_elem.text
                        if href and title:
                            articles.append((href.strip(), title.strip()))

        except ET.ParseError:
            pass

        return articles[:MAX_DISCOVER_PER_PILLAR]

    # ── Category page parsing ───────────────────────────────────

    def _parse_category_page(self, category_url: str) -> list[tuple[str, str]]:
        """Crawl a category/listing page and extract article links.

        Uses Scrapling (v0.4.8+) to fetch HTML, then tries multiple strategies:
          1. <article> tags with <a> inside (semantic HTML)
          2. CSS classes like .post-item, .entry-title, .card, etc.
          3. Generic <a> with article-like URL patterns
        """
        raw = self._fetch_raw(category_url, timeout=15)
        if not raw:
            return []

        articles: list[tuple[str, str]] = []
        try:
            from scrapling import Selector
            doc = Selector(content=raw)
            seen_urls: set[str] = set()

            def _extract_from_elements(container) -> list[tuple[str, str]]:
                """Extract (url, title) from link elements inside a container."""
                result = []
                links = container.css("a") if hasattr(container, "css") else container.find("a") or []
                if not isinstance(links, list):
                    links = [links]
                for a in links:
                    href = a.attrib.get("href", "")
                    text = (a.text or "").strip()
                    if not text and hasattr(a, "css"):
                        # Fallback: get text from direct children (no <a> wrapper case)
                        children_text = [c.strip() for c in (a.css("::text") if hasattr(a, "css") else []) if isinstance(c, str) and c.strip()]
                        text = " ".join(children_text) if children_text else ""
                    if href and text and len(text) > 10:
                        full_url = self._resolve_url(category_url, href)
                        if full_url and full_url not in seen_urls:
                            seen_urls.add(full_url)
                            result.append((full_url, text))
                return result

            # Strategy 1: <article> tags
            articles_found = doc.css("article")
            for article_elem in articles_found:
                articles.extend(_extract_from_elements(article_elem))
            if articles:
                return articles[:MAX_DISCOVER_PER_PILLAR]

            # Strategy 2: common post container CSS selectors
            for selector in [
                ".post-item", ".entry-title", ".card",
                ".post-title", ".post-link", ".article-item",
                ".news-item", ".list-item", ".story",
                ".item", "h2", "h3",
            ]:
                elems = doc.css(selector)
                for elem in elems:
                    link = elem.css("a")
                    if link:
                        articles.extend(_extract_from_elements(elem))
                    else:
                        # The element itself might be a link
                        href = elem.attrib.get("href", "") if hasattr(elem, "attrib") else ""
                        text = (elem.text or "").strip()
                        if href and text and len(text) > 10:
                            full_url = self._resolve_url(category_url, href)
                            if full_url and full_url not in seen_urls:
                                seen_urls.add(full_url)
                                articles.append((full_url, text))
                if articles:
                    break

            if articles:
                return articles[:MAX_DISCOVER_PER_PILLAR]

            # Strategy 3: any link with article-like URL patterns
            if not articles:
                article_patterns = [
                    "/bai-viet/", "/article", "/bai-viet",
                    "/cham-soc-da", "/cham-soc-dep",
                    "/lam-dep", "/my-pham",
                    "/skincare", "-skin-", "skin-care",
                    "/suc-khoe", "/song-khoe",
                    "/dep/", "/tips-",
                    ".chn", ".html", ".htm",  # Vietnamese article extensions
                ]
                all_links = doc.css("a")
                for a in all_links:
                    href = a.attrib.get("href", "")
                    text = (a.text or "").strip()
                    if not text and hasattr(a, "css"):
                        children_text = [c.strip() for c in (a.css("::text") if hasattr(a, "css") else []) if isinstance(c, str) and c.strip()]
                        text = " ".join(children_text) if children_text else ""
                    if href and text and len(text) > 10:
                        full_url = self._resolve_url(category_url, href)
                        if full_url and full_url not in seen_urls:
                            if any(p in full_url for p in article_patterns):
                                seen_urls.add(full_url)
                                articles.append((full_url, text))

        except Exception:
            pass

        return articles[:MAX_DISCOVER_PER_PILLAR]

    # ── XML helpers ────────────────────────────────────────────

    @staticmethod
    def _get_xml_text(parent: ET.Element, tag: str) -> str | None:
        """Get text content of a child element by tag name.

        Tries without namespace first, then with Atom namespace.
        """
        elem = parent.find(tag)
        if elem is not None and elem.text:
            return elem.text
        # Try with Atom namespace
        ns = "http://www.w3.org/2005/Atom"
        local = tag.split("}")[-1]  # strip any existing namespace
        elem = parent.find(f"{{{ns}}}{local}")
        if elem is not None and elem.text:
            return elem.text
        return None

    @staticmethod
    def _resolve_url(base: str, href: str) -> str | None:
        """Resolve a potentially relative URL against a base URL."""
        if not href or href.startswith("#") or href.startswith("javascript:"):
            return None
        if href.startswith("http://") or href.startswith("https://"):
            return href.split("?")[0].split("#")[0]
        # Relative URL — join with base
        from urllib.parse import urljoin
        result = urljoin(base, href)
        return result.split("?")[0].split("#")[0] if result else None

    # ── Discovery cache ────────────────────────────────────────

    def _is_discovery_on_cooldown(self, source_url: str) -> bool:
        """Check if we should skip re-checking this discovery source."""
        entry = self._discovery_cache.get(source_url)
        if entry is None:
            return False
        elapsed = time.time() - entry["last_fetched"]
        if entry.get("success"):
            # Successful sources: check every 30 min
            return elapsed < self._discovery_cooldown
        else:
            # Failed sources: retry every 5 min
            return elapsed < 300

    def _update_discovery_cache(self, source_url: str, success: bool) -> None:
        self._discovery_cache[source_url] = {
            "last_fetched": time.time(),
            "success": success,
        }

    # ── Fetching ───────────────────────────────────────────────

    def _fetch_raw(self, url: str, timeout: int = 15) -> str | None:
        """Fetch raw response body bytes, decode to string.

        Used for RSS XML parsing and category page HTML parsing.
        Returns None on failure (network error, timeout, empty body).
        """
        if not self._scrapling_available:
            return None
        try:
            import scrapling  # type: ignore[import-untyped]
            time.sleep(REQUEST_DELAY)
            p = scrapling.Fetcher.get(url, timeout=timeout)
            if p.status == 200 and len(p.body) > 200:
                try:
                    return p.body.decode("utf-8")
                except UnicodeDecodeError:
                    return p.body.decode("latin-1")
            return None
        except Exception:
            return None

    def _ensure_scrapling(self) -> None:
        if not self._scrapling_available:
            try:
                import scrapling  # noqa: F401
                self._scrapling_available = True
            except ImportError:
                self._scrapling_available = False

    # ── Content caching ────────────────────────────────────────

    def _get_cached(self, url: str) -> str | None:
        entry = self._cache.get(url)
        if entry and (time.time() - entry["fetched_at"]) < CACHE_TTL:
            return entry["text"]
        return None

    def _set_cached(self, url: str, text: str, pillar: str) -> None:
        self._cache[url] = {
            "text": text,
            "fetched_at": time.time(),
            "pillar": pillar,
        }
        if len(self._cache) > 100:
            now = time.time()
            stale = [k for k, v in self._cache.items()
                     if (now - v["fetched_at"]) > CACHE_TTL]
            for k in stale:
                del self._cache[k]

    def _is_from_cache(self, url: str) -> bool:
        return url in self._cache

    def _fetch_text(self, url: str) -> str | None:
        """Fetch a URL and return clean (stripped) text.

        Uses cache if available. Caches successful fetches.
        Returns None on failure.
        """
        cached = self._get_cached(url)
        if cached:
            return cached
        if not self._scrapling_available:
            return None
        try:
            import scrapling  # type: ignore[import-untyped]
            time.sleep(REQUEST_DELAY)
            p = scrapling.Fetcher.get(url, timeout=15)
            if p.status == 200 and len(p.body) > 200:
                text = p.get_all_text()
                self._set_cached(url, text, "discovered")
                return text
            return None
        except Exception:
            return None

    # ── Extraction ─────────────────────────────────────────────

    def _extract_findings(self, text: str, pillar: str) -> list[dict[str, str | int]]:
        if self._llm:
            return self._llm_extract(text, pillar)
        return self._heuristic_extract(text, pillar)

    def _llm_extract(self, text: str, pillar: str) -> list[dict[str, str | int]]:
        try:
            system_prompt = (
                "Bạn là chuyên gia research nội dung skincare. "
                "Nhiệm vụ: từ đoạn text blog đã crawl, trích xuất các chủ đề, "
                "thành phần, xu hướng đáng chú ý liên quan đến pillar "
                f"'{pillar}' của fanpage skincare GenZ."
            )
            truncated = text[:8000]
            user_prompt = f"""Đoạn text từ blog skincare:

{truncated}

Hãy trích xuất tối đa 5 findings (chủ đề/thành phần/xu hướng) quan trọng nhất.

Output JSON:
{{{{
  "findings": [
    {{{{
      "pillar": "{pillar}",
      "topic": "chủ đề ngắn gọn (tối đa 100 ký tự)",
      "key_points": "1-2 câu tóm tắt nội dung chính",
      "relevance": 1-5  (mức độ liên quan đến skincare GenZ, 5 là cao nhất),
      "source_type": "trend|ingredient|tip|myth|product"
    }}}}
  ]
}}}}

Chỉ trả về JSON, không markdown."""
            data = self._llm.generate_json(
                system_prompt, user_prompt,
                max_tokens=1000, temperature=0.3,
            )
            findings = data.get("findings", [])
            for f in findings:
                f["pillar"] = pillar
            return findings[:10]
        except Exception:
            return self._heuristic_extract(text, pillar)

    def _heuristic_extract(self, text: str, pillar: str) -> list[dict[str, str | int]]:
        findings: list[dict[str, str | int]] = []
        lines = text.split("\n")
        ingredients = [
            "vitamin c", "retinol", "niacinamide", "hyaluronic",
            "aha", "bha", "salicylic", "glycolic", "peptide",
            "ceramide", "sunscreen", "kem chống nắng",
            "dưỡng ẩm", "moisturizer", "serum",
            "tretinoin", "azelaic", "benzoyl peroxide",
            "squalane", "niacinamid", "alpha arbutin",
        ]
        skip_words = [
            "đăng ký", "subscribe", "đăng nhập",
            "tất cả", "xem thêm", "xem tất",
            "quảng cáo", "advertisement", "cookie",
            "để lại", "bình luận", "comment",
        ]
        for line in lines:
            line = line.strip()
            if not line or len(line) < 20 or len(line) > 200:
                continue
            if any(skip in line.lower() for skip in skip_words):
                continue
            if line.endswith(("?", "!", ":", "…", ".")):
                findings.append({"pillar": pillar, "topic": line[:120], "source_type": "headline", "relevance": 3})
                continue
            if any(ing in line.lower() for ing in ingredients):
                findings.append({"pillar": pillar, "topic": line[:120], "source_type": "ingredient_mention", "relevance": 4})
                continue
            if re.search(r"\d+", line) and any(kw in line.lower() for kw in ["cách", "bước", "lợi ích", "tác dụng", "mẹo", "tips", "bí quyết", "nguyên nhân"]):
                findings.append({"pillar": pillar, "topic": line[:120], "source_type": "tip", "relevance": 3})
        seen: set[str] = set()
        unique = []
        for f in findings[:20]:
            key = f.get("topic", "")[:30]
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique[:15]

    # ── Legacy public API ──────────────────────────────────────

    def _crawl_source(self, url: str) -> AgentResult:
        self._ensure_scrapling()
        content = self._fetch_text(url)
        if not content:
            return AgentResult(
                task_id=f"crawl-{url[:40]}",
                success=False,
                error=f"Failed to fetch {url}",
            )
        return AgentResult(
            task_id=f"crawl-{url[:40]}",
            success=True,
            data={"url": url, "content": content[:5000]},
        )

    def _get_source_list(self) -> AgentResult:
        return AgentResult(
            task_id="source-list",
            success=True,
            data={
                "rss_feeds": {p: urls for p, urls in RSS_FEEDS.items()},
                "category_pages": {p: urls for p, urls in CATEGORY_SOURCES.items()},
                "fallback_urls": {p: urls for p, urls in self._fallback.items()},
                "seen_articles_count": len(self._seen_articles),
                "cache_entries": len(self._cache),
                "discovery_cache_entries": len(self._discovery_cache),
            },
        )

    def get_cache_stats(self) -> dict[str, Any]:
        now = time.time()
        entries = len(self._cache)
        fresh = sum(1 for v in self._cache.values()
                    if (now - v["fetched_at"]) < CACHE_TTL)
        return {
            "total_entries": entries,
            "fresh_entries": fresh,
            "stale_entries": entries - fresh,
            "ttl_seconds": CACHE_TTL,
            "seen_articles": len(self._seen_articles),
            "discovery_cache_entries": len(self._discovery_cache),
        }
