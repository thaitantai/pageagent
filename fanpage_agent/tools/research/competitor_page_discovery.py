"""Phát hiện offer tiềm năng và phân tích đối thủ cùng niche qua web search.

Thay thế Facebook Graph API bằng MultiSourceSearchClient
(SearXNG → VN Crawler → DuckDuckGo) để tìm nội dung đối thủ.

Nâng cấp so với phiên bản cũ:
  - Query thông minh hơn: site-specific + product-specific
  - Lọc nhiễu: chỉ giữ content có context skincare
  - CompetitorProfile: phân tích cấu trúc từng đối thủ
  - Content format detection: review / comparison / tutorial / deal / ingredient
  - Gap & overlap analysis: sản phẩm nào chưa ai làm

NOTE: Data types đã chuyển sang competitor_models.py,
      helpers đã chuyển sang competitor_helpers.py.
      File này chỉ giữ CompetitorPageDiscoveryTool class.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fanpage_agent.tools.research.competitor_helpers import (
    _AFFILIATE_CLUE_WORDS,
    _FORMAT_PATTERNS,
    _MAX_DISCOVERED_OFFERS,
    _MAX_PAGES_PER_SCAN,
    _MIN_CLUE_WORDS,
    _NICHE_PRODUCT_MARKERS,
    _QUERY_TEMPLATES,
    is_noise_url,
    has_skincare_context,
    detect_content_format,
    estimate_price_positioning,
    estimate_content_tone,
)
from fanpage_agent.tools.research.competitor_models import (
    CompetitorProfile,
    ContentFormat,
    CrossCompetitorInsight,
)
from fanpage_agent.tools.research.product_topic_discovery import (
    ProductTopicCandidate,
)

# ── Re-export for backward compatibility ─────────────────
_ = CompetitorProfile, ContentFormat, CrossCompetitorInsight
_ = is_noise_url, has_skincare_context, detect_content_format
_ = estimate_price_positioning, estimate_content_tone

if TYPE_CHECKING:
    from fanpage_agent.scraping.multi_source_search import MultiSourceSearchClient

logger = logging.getLogger(__name__)

# Internal aliases for old call sites
_is_noise_url = is_noise_url
_has_skincare_context = has_skincare_context
_detect_content_format = detect_content_format
_estimate_price_positioning = estimate_price_positioning
_estimate_content_tone = estimate_content_tone


class CompetitorPageDiscoveryTool:
    """Phát hiện offer và phân tích đối thủ cùng niche qua web search.

    Nâng cấp:
      - Query thông minh hơn (site-specific, format-specific)
      - Lọc nhiễu (bỏ category không liên quan skincare)
      - CompetitorProfile: phân tích cấu trúc từng đối thủ
      - Content format detection
      - Cross-competitor gap & overlap analysis
    """

    def __init__(
        self,
        web_search: MultiSourceSearchClient | None = None,
    ) -> None:
        if web_search is not None:
            self._web_search = web_search
        else:
            # Competitor search: chỉ dùng SearXNG + DDG, bỏ VNCrawler
            # VNCrawler crawl site cố định (hellobacsi, chiaki...) không liên quan đối thủ
            from fanpage_agent.scraping.multi_source_search import (
                DDGBackend,
                MultiSourceSearchClient,
                SearXNGBackend,
            )

            searxng = SearXNGBackend(base_url="http://localhost:8899", timeout=10)
            ddg = DDGBackend(timeout=6)
            client = MultiSourceSearchClient()
            # Override backends: chỉ SearXNG + DDG (bỏ VNCrawler — site cố định không liên quan đối thủ)
            client._backends = [searxng, ddg]
            self._web_search = client

    # ── Public API ──────────────────────────────────────────

    def discover(
        self,
        competitor_names: list[str],
        existing_offers: list[str] | None = None,
        max_pages_to_scan: int = _MAX_PAGES_PER_SCAN,
        max_discovered_offers: int = _MAX_DISCOVERED_OFFERS,
    ) -> tuple[list[ProductTopicCandidate], list[str]]:
        """Quét web về các đối thủ, trả về offer candidates + page mới.

        Giữ interface cũ cho backward compatibility.
        """
        existing = set(existing_offers or [])
        discovered_pages: list[str] = []
        seen_pages: set[str] = set()
        candidates: list[ProductTopicCandidate] = []

        names_to_scan = competitor_names[:max_pages_to_scan]

        for name in names_to_scan:
            try:
                name_clean = name.strip().lower()
                results = self._search_competitor(name_clean)

                if not results:
                    logger.info("No content found for competitor '%s'", name)
                    continue

                for result in results:
                    text = f"{result.title} {result.snippet}".strip()
                    if not text:
                        continue

                    # Filter noise
                    if is_noise_url(result.url):
                        continue
                    if not has_skincare_context(text):
                        logger.debug(
                            "Skipping non-skincare result: %s",
                            result.title[:60],
                        )
                        continue

                    source_tag = f"web_search:{name_clean}"
                    product_candidates = self._scan_text(
                        text=text,
                        source_name=source_tag,
                    )
                    for c in product_candidates:
                        if c.product_name not in existing:
                            candidates.append(c)
                            existing.add(c.product_name)

            except Exception as exc:
                logger.warning(
                    "Failed to search competitor '%s': %s", name, exc,
                )
                continue

        candidates.sort(key=lambda c: c.product_relevance, reverse=True)
        return candidates[:max_discovered_offers], discovered_pages

    def analyze_competitors(
        self,
        competitor_names: list[str],
    ) -> tuple[list[CompetitorProfile], CrossCompetitorInsight]:
        """Phân tích chi tiết từng đối thủ → profiles + cross-competitor insights.

        Đây là API mới, sịn sò hơn discover().
        """
        from collections import Counter

        now = datetime.now(timezone.utc).isoformat(timespec="minutes")
        profiles: list[CompetitorProfile] = []

        # ── Bước 1: thu thập dữ liệu từng đối thủ ──
        for name in competitor_names:
            name_clean = name.strip().lower()
            results = self._search_competitor(name_clean)
            if not results:
                continue

            # Accumulate texts and URLs
            all_texts: list[str] = []
            urls: list[str] = []
            for r in results:
                t = f"{r.title} {r.snippet}".strip()
                if t and has_skincare_context(t) and not is_noise_url(r.url):
                    all_texts.append(t)
                    urls.append(r.url)

            # Phân tích
            profile = self._build_profile(name_clean, all_texts, urls, now)
            profiles.append(profile)

        # ── Bước 2: cross-competitor analysis ──
        insight = self._analyze_cross_competitor(profiles)

        return profiles, insight

    # ── Search ─────────────────────────────────────────────

    def _search_competitor(self, name: str) -> list:
        """Search web với queries cho một đối thủ."""
        queries = self._build_queries(name)
        all_results = self._web_search.search_multiple(
            queries=queries,
            max_per_query=4,  # Tăng từ 2 → 4 để có đủ data
            dedup=True,
        )
        return all_results

    def _build_queries(self, name: str) -> list[str]:
        """Build search queries cho một đối thủ."""
        return [q.format(name=name) for q in _QUERY_TEMPLATES]

    # ── Profile building ───────────────────────────────────

    def _build_profile(
        self,
        name: str,
        texts: list[str],
        urls: list[str],
        timestamp: str,
    ) -> CompetitorProfile:
        """Xây dựng CompetitorProfile từ list text entries."""
        from collections import Counter

        combined_text = " ".join(texts)

        # Products
        products_detected: list[str] = []
        for marker in _NICHE_PRODUCT_MARKERS:
            if marker in combined_text.lower():
                products_detected.append(marker.capitalize())

        # Count product frequency
        product_freq: Counter = Counter()
        for text in texts:
            text_lower = text.lower()
            for marker in _NICHE_PRODUCT_MARKERS:
                if marker in text_lower:
                    product_freq[marker.capitalize()] += 1

        top_products = [p for p, _ in product_freq.most_common(3)]

        # Content angles
        angles: list[str] = []
        clue_count = sum(
            1 for w in _AFFILIATE_CLUE_WORDS if w in combined_text.lower()
        )
        for text in texts:
            angle = self._detect_angle(text, clue_count)
            if angle and angle not in angles:
                angles.append(angle)

        # Content formats
        formats: list[ContentFormat] = []
        for text in texts:
            fmt = detect_content_format(text, text)
            formats.append(fmt)
        # Top format
        if formats:
            fmt_counter: Counter = Counter(f.type for f in formats)
            top_format = fmt_counter.most_common(1)[0][0] if fmt_counter else "general"
        else:
            top_format = "general"

        # Price positioning
        price_pos = estimate_price_positioning(combined_text)

        # Content tone
        tone = estimate_content_tone(combined_text, top_format)

        # Unique angle heuristic
        unique_angle = self._detect_unique_angle(combined_text, products_detected)

        return CompetitorProfile(
            name=name,
            products_detected=products_detected,
            top_products=top_products,
            angles_detected=angles,
            top_angle=angles[0] if angles else "education",
            formats_detected=formats[:3],
            top_format=top_format,
            price_positioning=price_pos,
            content_tone=tone,
            search_urls=urls[:5],
            findings_count=len(texts),
            unique_angle=unique_angle,
            analyzed_at=timestamp,
        )

    @staticmethod
    def _detect_unique_angle(text: str, products: list[str]) -> str:
        """Phát hiện angle độc đáo của đối thủ từ text."""
        text_lower = text.lower()

        # Check for unique positioning signals
        if any(w in text_lower for w in ["organic", "thiên nhiên", "natural", "thuần chay"]):
            return "natural_organic_focus"
        if any(w in text_lower for w in ["bác sĩ", "dermatologist", "clinical", "nghiên cứu"]):
            return "science_clinical_focus"
        if any(w in text_lower for w in ["hàn quốc", "korean", "k-beauty"]):
            return "korean_beauty_focus"
        if any(w in text_lower for w in ["việt nam", "sản xuất tại việt", "thuần việt"]):
            return "vietnamese_local_focus"
        if any(w in text_lower for w in ["giá rẻ", "bình dân", "affordable", "tiết kiệm"]):
            return "budget_affordable_focus"
        if any(w in text_lower for w in ["cao cấp", "premium", "luxury"]):
            return "premium_luxury_focus"
        if any(w in text_lower for w in ["review", "đánh giá", "chân thật"]):
            return "honest_review_focus"
        if any(w in text_lower for w in ["mụn", "acne", "da dầu", "da nhạy cảm"]):
            return "problem_skin_focus"

        return "general_skincare"

    # ── Cross-competitor analysis ──────────────────────────

    @staticmethod
    def _analyze_cross_competitor(
        profiles: list[CompetitorProfile],
    ) -> CrossCompetitorInsight:
        """Phân tích gap & overlap giữa các đối thủ."""
        from collections import Counter as OverlapCounter

        all_products: list[str] = []
        for p in profiles:
            all_products.extend(p.products_detected)
        product_counts: OverlapCounter = OverlapCounter(all_products)
        shared = [
            (prod, count)
            for prod, count in product_counts.most_common(10)
            if count >= 2  # xuất hiện ở ít nhất 2 đối thủ
        ]

        # Unique products per competitor
        unique_map: dict[str, list[str]] = {}
        for p in profiles:
            others_products: set[str] = set()
            for other in profiles:
                if other.name != p.name:
                    others_products.update(other.products_detected)
            unique_map[p.name] = [
                prod for prod in p.products_detected
                if prod not in others_products
            ]

        # Gap products (products no competitor covers)
        all_covered: set[str] = set(all_products)
        gap_products = [
            marker.capitalize()
            for marker in _NICHE_PRODUCT_MARKERS
            if marker.capitalize() not in all_covered
        ][:5]

        # Underused formats
        all_formats: list[str] = []
        for p in profiles:
            all_formats.extend(f.type for f in p.formats_detected)
        format_counts: OverlapCounter = OverlapCounter(all_formats)
        underused = [
            fmt for fmt in _FORMAT_PATTERNS
            if fmt not in format_counts
        ][:3]

        # Generate recommendation
        rec_parts: list[str] = []
        if shared:
            top_shared = shared[0][0]
            rec_parts.append(
                f"Top product đối thủ đều làm: {top_shared}. "
                "Cần góc nhìn khác biệt để cạnh tranh."
            )
        if gap_products:
            rec_parts.append(
                f"Sản phẩm chưa đối thủ nào khai thác: {', '.join(gap_products[:3])}. "
                "Cơ hội first-mover!"
            )
        if underused:
            rec_parts.append(
                f"Format chưa ai dùng: {', '.join(underused)}. "
                "Thử nghiệm để tạo khác biệt."
            )

        recommendation = " ".join(rec_parts) if rec_parts else (
            "Tiếp tục theo dõi đối thủ để phát hiện cơ hội mới."
        )

        return CrossCompetitorInsight(
            shared_products=shared,
            unique_products_by_competitor=unique_map,
            gap_products=gap_products,
            underused_formats=underused,
            recommendation=recommendation,
        )

    # ── Text scanning (giữ từ phiên bản cũ) ────────────────

    def _scan_text(
        self,
        text: str,
        source_name: str,
    ) -> list[ProductTopicCandidate]:
        """Quét text từ kết quả search, trả về ProductTopicCandidate."""
        if not text:
            return []
        text_lower = text.lower()

        clue_count = sum(
            1 for word in _AFFILIATE_CLUE_WORDS if word in text_lower
        )

        candidates: list[ProductTopicCandidate] = []
        for marker in _NICHE_PRODUCT_MARKERS:
            if marker not in text_lower:
                continue
            relevance = min(1.0, 0.5 + clue_count * 0.08)
            angle = self._detect_angle(text_lower, clue_count)
            customer_value = self._estimate_customer_value(text_lower, clue_count)
            risk = "medium" if clue_count < 3 else "low"

            reason_codes = [
                "auto_discovered_offer",
                "competitor_page_discovery",
            ]
            if clue_count >= _MIN_CLUE_WORDS:
                reason_codes.append("affiliate_context_detected")
            reason_codes.append(f"web_source:{source_name}")

            sentences = re.split(r"[.!?\\n]", text)
            context_sentence = ""
            for sent in sentences:
                if marker in sent.lower():
                    context_sentence = sent.strip()
                    break

            candidates.append(
                ProductTopicCandidate(
                    topic=f"{marker}: góc nhìn từ đối thủ",
                    angle=angle,
                    product_name=marker.capitalize(),
                    customer_pain="",
                    research_query=(
                        context_sentence[:120]
                        if context_sentence
                        else f"{marker} competitor review"
                    ),
                    product_relevance=round(relevance, 3),
                    customer_value=round(customer_value, 3),
                    risk_level=risk,
                    reason_codes=reason_codes,
                )
            )
        return candidates

    # ── Static helpers ──────────────────────────────────────

    @staticmethod
    def _extract_mentions(text: str) -> list[tuple[str, str]]:
        """Trích page mention từ Facebook post text."""
        fb_mention_re = re.compile(r"@\[(\d+):\d+:(.+?)\]")
        return fb_mention_re.findall(text)

    @staticmethod
    def _detect_angle(text: str, clue_count: int) -> str:
        if any(w in text for w in ["so sánh", "vs", "versus", "comparison"]):
            return "comparison"
        if any(w in text for w in ["top", "tốt nhất", "best", "nên mua"]):
            return "buying_guide"
        if clue_count >= 4 or any(w in text for w in ["trải nghiệm", "test", "sau"]):
            return "review"
        return "education"

    @staticmethod
    def _estimate_customer_value(text: str, clue_count: int) -> float:
        base = 0.4
        if clue_count >= 3:
            base += 0.15
        if any(w in text for w in ["review", "đánh giá", "trải nghiệm"]):
            base += 0.15
        if any(w in text for w in ["mẹo", "tip", "cách chọn", "hướng dẫn"]):
            base += 0.15
        if any(w in text for w in ["giá", "rẻ", "deal", "coupon"]):
            base += 0.1
        return min(1.0, base)
