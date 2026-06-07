"""Phát hiện offer tiềm năng từ phân tích page Facebook cùng niche.

Quét post từ các page đối thủ/cùng ngành, trích xuất sản phẩm được
nhắc đến, và tự động mở rộng danh sách page qua mention (@[page_id])
trong post.

Luồng:
1. Lấy page_id từ config (seed competitor_pages)
2. Fetch recent posts từ mỗi page qua Graph API (Page Access Token)
3. Phân tích post text để tìm product markers
4. Trích xuất page mới từ mention @[id:1:Name] — tự mở rộng
5. Trả về ProductTopicCandidate + danh sách page mới phát hiện
"""

from __future__ import annotations

import logging
import re
from typing import Protocol

from fanpage_agent.services.product_topic_discovery import (
    ProductTopicCandidate,
)

logger = logging.getLogger(__name__)

# ── Product markers tương tự offer_discovery.py ──────────────────
_AFFILIATE_CLUE_WORDS: set[str] = {
    "review", "đánh giá", "reviewed", "tốt nhất", "best",
    "so sánh", "comparison", "vs", "versus",
    "mua", "buy", "giá", "price", "rẻ nhất", "cheapest",
    "top", "nên mua", "should buy", "recommend", "gợi ý",
    "ưu đãi", "deal", "coupon", "giảm giá", "discount",
    "trải nghiệm", "experience", "sau 30 ngày",
    "test", "thử nghiệm", "honest review",
}

_NICHE_PRODUCT_MARKERS: set[str] = {
    "serum", "retinol", "vitamin c", "niacinamide", "hyaluronic",
    "sunscreen", "kem chống nắng", "moisturizer", "kem dưỡng",
    "cleanser", "sữa rửa mặt", "toner", "nước hoa hồng",
    "essence", "ampoule", "face mask", "mặt nạ",
    "eye cream", "kem mắt", "exfoliator", "tẩy tế bào chết",
    "spf", "peptide", "aha", "bha", "pha",
    "benzoyl peroxide", "salicylic acid", "glycolic acid",
    "collagen", "snail mucin", "cica", "centella",
    "probiotic", "ceramide", "squalane", "retinaldehyde",
    "adapalene", "tretinoin", "azelaic",
}

_NICHE_KEYWORDS: set[str] = {
    "skincare", "chăm sóc da", "làm đẹp", "beauty", "mỹ phẩm",
    "da liễu", "dermatology", "dưỡng da", "trị mụn",
    "chống lão hóa", "anti-aging", "dưỡng trắng",
    "sức khỏe", "health", "wellness", "sức khoẻ",
}

# Pattern để trích mention `@[page_id:1:Page Name]` từ Facebook post
_FB_MENTION_RE = re.compile(r"@\[(\d+):\d+:(.+?)\]")

# Threshold — tối thiểu clue words để coi là post có affiliate potential
_MIN_CLUE_WORDS = 2

# Số offer phát hiện tối đa mỗi lần
_MAX_DISCOVERED_OFFERS = 6

# Số page tối đa scan mỗi lần (ngăn quá tải API)
_MAX_PAGES_PER_SCAN = 5

# Số post tối đa fetch mỗi page
_MAX_POSTS_PER_PAGE = 20


class FacebookPageClient(Protocol):
    """Protocol tối thiểu mà CompetitorPageDiscoveryService cần."""

    def get_public_page_info(self, page_id: str) -> dict: ...
    def get_public_page_posts(
        self, page_id: str, limit: int
    ) -> list[dict]: ...


class CompetitorPageDiscoveryService:
    """Phát hiện offer từ phân tích post của page Facebook cùng niche.

    Quét competitor/niche pages để phát hiện sản phẩm đang được nói đến,
    đồng thời tự mở rộng danh sách page qua mention (@[page_id]) trong post.

    Parameters
    ----------
    fb_client : FacebookPageClient | None
        Client để gọi Graph API. Nếu None, chỉ parse mention mà không fetch.
    """

    def __init__(
        self, fb_client: FacebookPageClient | None = None
    ) -> None:
        self._fb_client = fb_client

    def discover(
        self,
        competitor_page_ids: list[str],
        existing_offers: list[str] | None = None,
        max_pages_to_scan: int = _MAX_PAGES_PER_SCAN,
        max_posts_per_page: int = _MAX_POSTS_PER_PAGE,
        max_discovered_offers: int = _MAX_DISCOVERED_OFFERS,
    ) -> tuple[list[ProductTopicCandidate], list[str]]:
        """Quét competitor pages, trả về offer candidates + page mới.

        Parameters
        ----------
        competitor_page_ids : list[str]
            Danh sách page_id seed từ config.
        existing_offers : list[str] | None
            Product name đã có để tránh trùng.
        max_pages_to_scan : int
            Tối đa page scan mỗi lần chạy.
        max_posts_per_page : int
            Tối đa post fetch mỗi page.
        max_discovered_offers : int
            Tối đa offer candidate trả về.

        Returns
        -------
        tuple[list[ProductTopicCandidate], list[str]]
            Tuple gồm: (offer candidates mới, page IDs mới phát hiện).
        """
        existing = set(existing_offers or [])
        discovered_pages: list[str] = []
        seen_pages: set[str] = set(competitor_page_ids)
        candidates: list[ProductTopicCandidate] = []

        # Giới hạn số page scan để tránh quá tải API
        pages_to_scan = competitor_page_ids[:max_pages_to_scan]

        if self._fb_client is None:
            logger.warning(
                "CompetitorPageDiscoveryService: no fb_client provided, "
                "cannot fetch posts"
            )
            return [], []

        for page_id in pages_to_scan:
            try:
                posts = self._fb_client.get_public_page_posts(
                    page_id, limit=max_posts_per_page
                )
            except Exception as exc:
                logger.warning(
                    "Failed to fetch posts from page %s: %s",
                    page_id, exc,
                )
                continue

            for post in posts:
                message = post.get("message", "") or ""
                if not message:
                    continue

                # 1. Scan product mentions
                product_candidates = self._scan_text(
                    text=message,
                    source_name=f"fb_competitor:{page_id}",
                )
                for c in product_candidates:
                    if c.product_name not in existing:
                        candidates.append(c)
                        existing.add(c.product_name)

                # 2. Extract new page mentions (self-discover)
                new_pages = self._extract_mentions(message)
                for mention_id, mention_name in new_pages:
                    if mention_id not in seen_pages:
                        seen_pages.add(mention_id)
                        discovered_pages.append(mention_id)
                        logger.info(
                            "Discovered new niche page: %s (%s)",
                            mention_name, mention_id,
                        )

        # Sort candidates by relevance
        candidates.sort(
            key=lambda c: c.product_relevance, reverse=True
        )
        return candidates[:max_discovered_offers], discovered_pages

    def _scan_text(
        self,
        text: str,
        source_name: str,
    ) -> list[ProductTopicCandidate]:
        """Quét text post, trả về ProductTopicCandidate cho mỗi sản phẩm.

        Sử dụng logic tương tự OfferDiscoveryService._scan_text() nhưng
        gắn source là fb_competitor để phân biệt nguồn.
        """
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
            customer_value = self._estimate_customer_value(
                text_lower, clue_count
            )
            risk = "medium" if clue_count < 3 else "low"

            reason_codes = [
                "auto_discovered_offer",
                "competitor_page_discovery",
            ]
            if clue_count >= _MIN_CLUE_WORDS:
                reason_codes.append("affiliate_context_detected")
            reason_codes.append(f"fb_source:{source_name}")

            # Lấy câu chứa marker làm research_query mẫu
            sentences = re.split(r"[.!?\n]", text)
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

    @staticmethod
    def _extract_mentions(text: str) -> list[tuple[str, str]]:
        """Trích page mention từ Facebook post text.

        Facebook mention format: @[page_id:1:Page Name]

        Returns
        -------
        list[tuple[str, str]]
            List of (page_id, page_name) pairs.
        """
        return _FB_MENTION_RE.findall(text)

    @staticmethod
    def _detect_angle(text: str, clue_count: int) -> str:
        """Phát hiện angle content từ clue words."""
        if any(
            word in text
            for word in [
                "so sánh", "vs", "versus", "comparison",
            ]
        ):
            return "comparison"
        if any(
            word in text
            for word in [
                "top", "tốt nhất", "best", "nên mua",
            ]
        ):
            return "buying_guide"
        if clue_count >= 4 or any(
            word in text
            for word in ["trải nghiệm", "test", "sau"]
        ):
            return "review"
        return "education"

    @staticmethod
    def _estimate_customer_value(text: str, clue_count: int) -> float:
        """Ước lượng customer value từ post context."""
        base = 0.4
        if clue_count >= 3:
            base += 0.15
        if any(
            word in text
            for word in ["review", "đánh giá", "trải nghiệm"]
        ):
            base += 0.15
        if any(
            word in text
            for word in ["mẹo", "tip", "cách chọn", "hướng dẫn"]
        ):
            base += 0.15
        if any(
            word in text
            for word in ["giá", "rẻ", "deal", "coupon"]
        ):
            base += 0.1
        return min(1.0, base)
