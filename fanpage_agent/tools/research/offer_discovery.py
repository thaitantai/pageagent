"""Phát hiện offer tiềm năng từ nội dung web crawl.

Quét source documents / external trends để tìm sản phẩm được nhắc đến nhiều,
phân tích ngữ cảnh và trả về ProductTopicCandidate để OfferEvaluator đánh giá tiếp.
"""

from __future__ import annotations

import logging

from fanpage_agent.models import SourceDocument, TrendItem
from fanpage_agent.tools.research.product_topic_discovery import ProductTopicCandidate

logger = logging.getLogger(__name__)

# Từ khóa gợi ý nội dung có tính affiliate/review/comparison
_AFFILIATE_CLUE_WORDS: set[str] = {
    "review",
    "đánh giá",
    "reviewed",
    "tốt nhất",
    "best",
    "so sánh",
    "comparison",
    "vs",
    "versus",
    "mua",
    "buy",
    "giá",
    "price",
    "rẻ nhất",
    "cheapest",
    "top",
    "nên mua",
    "should buy",
    "recommend",
    "gợi ý",
    "ưu đãi",
    "deal",
    "coupon",
    "giảm giá",
    "discount",
    "trải nghiệm",
    "experience",
    "sau 30 ngày",
    "after 30 days",
    "test",
    "thử nghiệm",
    "honest review",
}

# Từ khóa sản phẩm phổ biến trong niche skincare/làm đẹp
_NICHE_PRODUCT_MARKERS: set[str] = {
    "serum",
    "retinol",
    "vitamin c",
    "niacinamide",
    "hyaluronic",
    "sunscreen",
    "kem chống nắng",
    "moisturizer",
    "kem dưỡng",
    "cleanser",
    "sữa rửa mặt",
    "toner",
    "nước hoa hồng",
    "essence",
    "ampoule",
    "face mask",
    "mặt nạ",
    "eye cream",
    "kem mắt",
    "exfoliator",
    "tẩy tế bào chết",
    "sunscreen",
    "spf",
    "peptide",
    "aha",
    "bha",
    "pha",
    "benzoyl peroxide",
    "salicylic acid",
    "glycolic acid",
    "collagen",
    "snail mucin",
    "cica",
    "centella",
    "probiotic",
    "ceramide",
    "squalane",
    "retinaldehyde",
    "adapalene",
    "tretinoin",
    "azelaic",
}

# Threshold — tối thiểu clue words để coi là có affiliate potential
_MIN_CLUE_WORDS = 2

# Số offer phát hiện tối đa mỗi lần
_MAX_DISCOVERED_OFFERS = 6


class OfferDiscoveryTool:
    """Phát hiện offer tiềm năng từ nội dung web đã crawl.

    Phân tích source documents và external trends để tìm sản phẩm
    có khả năng là affiliate offer, dựa trên:
    - Từ khóa sản phẩm trong niche
    - Ngữ cảnh review/comparison/buying guide
    - Tần suất xuất hiện
    """

    def discover(
        self,
        source_documents: list[SourceDocument] | None = None,
        external_trends: list[TrendItem] | None = None,
        existing_offers: list[str] | None = None,
        max_offers: int = _MAX_DISCOVERED_OFFERS,
    ) -> list[ProductTopicCandidate]:
        """Quét nội dung crawl và trả về offer candidates mới.

        Parameters
        ----------
        source_documents : list[SourceDocument] | None
            Source documents từ SourceRegistry.
        external_trends : list[TrendItem] | None
            Trend items từ web search / RSS.
        existing_offers : list[str] | None
            Danh sách product_name đã có, để tránh trùng.
        max_offers : int
            Số offer tối đa trả về.

        Returns
        -------
        list[ProductTopicCandidate]
            Các offer candidate mới chưa có trong existing_offers.
        """
        existing = set(existing_offers or [])

        raw_candidates: list[ProductTopicCandidate] = []

        # Quét source documents
        for doc in source_documents or []:
            candidates = self._scan_text(
                text=doc.content,
                title=doc.title,
                url=doc.url,
                source_name=doc.source_name,
            )
            for c in candidates:
                if c.product_name not in existing:
                    raw_candidates.append(c)
                    existing.add(c.product_name)

        # Quét external trends
        for item in external_trends or []:
            candidates = self._scan_text(
                text=item.title,
                title=item.title,
                url=item.url or "",
                source_name=item.source or "web_search",
            )
            for c in candidates:
                if c.product_name not in existing:
                    raw_candidates.append(c)
                    existing.add(c.product_name)

        # Gom các candidate trùng sản phẩm, lấy score cao nhất
        merged = self._merge_candidates(raw_candidates)
        merged.sort(key=lambda c: c.product_relevance, reverse=True)
        return merged[:max_offers]

    def _scan_text(
        self,
        text: str,
        title: str,
        url: str,
        source_name: str,
    ) -> list[ProductTopicCandidate]:
        """Quét một đoạn text, trả về ProductTopicCandidate cho mỗi sản phẩm phát hiện."""
        if not text:
            return []
        text_lower = text.lower()

        clue_count = sum(1 for word in _AFFILIATE_CLUE_WORDS if word in text_lower)

        candidates: list[ProductTopicCandidate] = []
        for marker in _NICHE_PRODUCT_MARKERS:
            if marker not in text_lower:
                continue
            # Tính score dựa trên số clue words
            relevance = min(1.0, 0.5 + clue_count * 0.08)
            # Xác định angle dựa trên clue words
            angle = self._detect_angle(text_lower, clue_count)
            # Tính customer value
            customer_value = self._estimate_customer_value(text_lower, clue_count)
            # Risk level: sản phẩm skincare = medium risk mặc định (dễ bị claim sai)
            risk = "medium" if clue_count < 3 else "low"
            # Research query từ title gốc
            research_query = title[:120] if title else marker

            reason_codes = ["auto_discovered_offer", "web_crawl_discovery"]
            if clue_count >= _MIN_CLUE_WORDS:
                reason_codes.append("affiliate_context_detected")

            candidates.append(
                ProductTopicCandidate(
                    topic=f"{marker}: góc nhìn từ chuyên gia",
                    angle=angle,
                    product_name=marker.capitalize(),
                    customer_pain="",
                    research_query=research_query,
                    product_relevance=round(relevance, 3),
                    customer_value=round(customer_value, 3),
                    risk_level=risk,
                    reason_codes=reason_codes,
                )
            )
        return candidates

    @staticmethod
    def _detect_angle(text: str, clue_count: int) -> str:
        """Phát hiện angle content từ clue words."""
        if any(word in text for word in ["so sánh", "vs", "versus", "comparison"]):
            return "comparison"
        if any(word in text for word in ["top", "tốt nhất", "best", "nên mua"]):
            return "buying_guide"
        if clue_count >= 4 or any(word in text for word in ["trải nghiệm", "test", "sau"]):
            return "review"
        return "education"

    @staticmethod
    def _estimate_customer_value(text: str, clue_count: int) -> float:
        """Ước lượng customer value dựa trên context."""
        base = 0.5
        if clue_count >= 3:
            base += 0.15
        if any(word in text for word in ["review", "đánh giá", "trải nghiệm"]):
            base += 0.15
        if any(word in text for word in ["mẹo", "tip", "cách chọn", "hướng dẫn"]):
            base += 0.15
        if any(word in text for word in ["giá", "rẻ", "deal", "coupon"]):
            base += 0.1
        return min(1.0, base)

    @staticmethod
    def _merge_candidates(
        candidates: list[ProductTopicCandidate],
    ) -> list[ProductTopicCandidate]:
        """Gom các candidate trùng product_name, giữ score cao nhất và gộp reason_codes."""
        merged: dict[str, ProductTopicCandidate] = {}
        for c in candidates:
            existing = merged.get(c.product_name)
            if existing is None:
                merged[c.product_name] = c
            elif c.product_relevance > existing.product_relevance:
                merged[c.product_name] = c
        return list(merged.values())
