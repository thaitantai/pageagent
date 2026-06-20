"""Utility functions and constants for competitor analysis.

Extracted from competitor_page_discovery.py for cleaner separation.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fanpage_agent.tools.research.competitor_models import ContentFormat

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════

# Affiliate clue words
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
    "test",
    "thử nghiệm",
    "honest review",
}

# Skincare product markers
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

# Category keywords — để phân loại result có liên quan skincare không
_SKINCARE_CATEGORY_KEYWORDS: set[str] = {
    "skincare",
    "chăm sóc da",
    "dưỡng da",
    "làm đẹp",
    "beauty",
    "mỹ phẩm",
    "cosmetic",
    "da dầu",
    "da khô",
    "da mụn",
    "chống lão hóa",
    "anti-aging",
    "dưỡng ẩm",
    "moisturizing",
    "làm trắng",
    "brightening",
    "se khít lỗ chân lông",
    "trị mụn",
    "acne",
    "thâm nám",
    "tàn nhang",
    "chống nắng",
    "sunscreen",
    "bảo vệ da",
}

# Noise sites — URL patterns không liên quan skincare
_NOISE_DOMAIN_PATTERNS: list[re.Pattern] = [
    re.compile(r"vnexpress\.net/(suc-khoe|the-gioi|thoi-su|kinh-doanh)"),
    re.compile(r"24h\.com\.vn/(suc-khoe|tin-tuc|thoi-trang|cong-nghe-thong-tin)"),
    re.compile(r"afamily\.vn/(suc-khoe|tam-su|cuoi)"),
    re.compile(r"dantri\.com\.vn/(suc-khoe|the-gioi|van-hoa)"),
    re.compile(r"thanhnien\.vn/(suc-khoe|thoi-su|van-hoa)"),
    re.compile(r"tuoitre\.vn/(suc-khoe|thoi-su|van-hoa)"),
    re.compile(r"ngoisao\.vn"),
    re.compile(r"kenh14\.vn"),
    re.compile(r"yeah1\.com"),
    re.compile(r"webtretho\.com"),  # forum — quá nhiễu
    re.compile(r"tamsubut"),  # tâm sự
]

# Content format detection patterns
_FORMAT_PATTERNS: dict[str, list[str]] = {
    "review": [
        "review",
        "đánh giá",
        "trải nghiệm",
        "dùng thử",
        "sau khi dùng",
        "after",
        "experience",
        "honest",
    ],
    "comparison": [
        "so sánh",
        "vs",
        "versus",
        "comparison",
        "hay",
        "nên chọn",
        "which one",
        "khác nhau",
        "difference",
        "đối đầu",
        "face-off",
    ],
    "tutorial": [
        "cách dùng",
        "how to",
        "hướng dẫn",
        "guide",
        "các bước",
        "step",
        "routine",
        "quy trình",
        "tips",
        "mẹo",
        "tutorial",
    ],
    "ingredient_deep_dive": [
        "thành phần",
        "ingredient",
        "bảng thành phần",
        "incidecoder",
        "phân tích",
        "skincare decoder",
        "hoạt chất",
        "nồng độ",
        "concentration",
    ],
    "deal_promotion": [
        "deal",
        "sale",
        "giảm giá",
        "discount",
        "coupon",
        "mã",
        "voucher",
        "khuyến mãi",
        "flash sale",
        "mua 1 tặng 1",
        "free ship",
        "freeship",
    ],
    "qa": [
        "faq",
        "hỏi đáp",
        "q&a",
        "hỏi",
        "trả lời",
        "ask",
        "answer",
        "question",
        "giải đáp",
    ],
    "unboxing": [
        "unbox",
        "unboxing",
        "mở hộp",
        "open box",
        "first impression",
        "ấn tượng đầu",
    ],
}

# Query templates
_QUERY_TEMPLATES: list[str] = [
    '"{name}" skincare review',
    '"{name}" mỹ phẩm đánh giá',
    '"{name}" sản phẩm dưỡng da',
    '"{name}" thành phần skincare',
    '"{name}" serum kem chống nắng',
]

# Thresholds
_MIN_CLUE_WORDS = 2
_MAX_DISCOVERED_OFFERS = 8
_MAX_PAGES_PER_SCAN = 5
_MIN_SKINCARE_KEYWORDS = 1  # tối thiểu keyword skincare để pass filter


# ══════════════════════════════════════════════════════════
# Utility functions
# ══════════════════════════════════════════════════════════


def is_noise_url(url: str) -> bool:
    """Check if URL is from a non-skincare category."""
    return any(p.search(url) for p in _NOISE_DOMAIN_PATTERNS)


def has_skincare_context(text: str) -> bool:
    """Check if text có context skincare (ít nhất _MIN_SKINCARE_KEYWORDS keywords)."""
    text_lower = text.lower()
    count = sum(1 for kw in _SKINCARE_CATEGORY_KEYWORDS if kw in text_lower)
    return count >= _MIN_SKINCARE_KEYWORDS


def detect_content_format(title: str, snippet: str) -> "ContentFormat":
    """Phát hiện format content từ title + snippet."""
    # Lazy import to avoid circular
    from fanpage_agent.tools.research.competitor_models import ContentFormat

    combined = f"{title} {snippet}".lower()
    best_type = "general"
    best_score = 0.0
    best_clues: list[str] = []

    for fmt, patterns in _FORMAT_PATTERNS.items():
        score = 0.0
        clues: list[str] = []
        for p in patterns:
            if p in combined:
                score += 1.0
                clues.append(p)
        # Normalize by pattern count
        if patterns:
            score = score / len(patterns)
        if score > best_score:
            best_score = score
            best_type = fmt
            best_clues = clues

    return ContentFormat(
        type=best_type,
        confidence=min(1.0, best_score * 2.5),
        clues=best_clues,
    )


def estimate_price_positioning(text: str) -> str:
    """Ước lượng price positioning từ text."""
    text_lower = text.lower()
    premium_words = [
        "cao cấp",
        "premium",
        "luxury",
        "đắt",
        "xịn",
        "high-end",
        "sang trọng",
        "đẳng cấp",
    ]
    budget_words = [
        "rẻ",
        "bình dân",
        "giá tốt",
        "tiết kiệm",
        "affordable",
        "hợp túi tiền",
        "giá rẻ",
        "dưới 100k",
        "dưới 200k",
    ]
    mid_words = [
        "tầm trung",
        "giá hợp lý",
        "đáng đồng tiền",
        "worth",
        "quality price",
    ]

    premium = sum(1 for w in premium_words if w in text_lower)
    budget = sum(1 for w in budget_words if w in text_lower)
    mid = sum(1 for w in mid_words if w in text_lower)

    if premium > budget and premium > mid:
        return "premium"
    elif budget > premium and budget > mid:
        return "budget"
    else:
        return "mid"


def estimate_content_tone(text: str, format_type: str) -> str:
    """Ước lượng content tone từ text."""
    text_lower = text.lower()

    scientific_words = [
        "thành phần",
        "nghiên cứu",
        "study",
        "clinical",
        "dermatologist",
        "bác sĩ da liễu",
        "khoa học",
        "active ingredient",
        "hoạt chất",
        "nồng độ",
    ]
    educational_words = [
        "cách",
        "hướng dẫn",
        "guide",
        "tips",
        "mẹo",
        "nên",
        "không nên",
        "lưu ý",
        "cần biết",
    ]
    entertaining_words = [
        "xu hướng",
        "hot",
        "trend",
        "must-have",
        "đỉnh",
        "chất",
        "xuất sắc",
        "tuyệt vời",
    ]

    scientific = sum(1 for w in scientific_words if w in text_lower)
    educational = sum(1 for w in educational_words if w in text_lower)
    entertaining = sum(1 for w in entertaining_words if w in text_lower)

    if scientific >= 2 and scientific >= educational and scientific >= entertaining:
        return "scientific"
    elif educational >= 2 and educational >= entertaining:
        return "educational"
    elif entertaining >= 2:
        return "entertaining"
    elif format_type in ("review", "comparison"):
        return "review"
    else:
        return "educational"  # default


__all__ = [
    "is_noise_url",
    "has_skincare_context",
    "detect_content_format",
    "estimate_price_positioning",
    "estimate_content_tone",
    # Expose constants for reuse
    "_AFFILIATE_CLUE_WORDS",
    "_NICHE_PRODUCT_MARKERS",
    "_SKINCARE_CATEGORY_KEYWORDS",
    "_NOISE_DOMAIN_PATTERNS",
    "_FORMAT_PATTERNS",
    "_QUERY_TEMPLATES",
    "_MIN_CLUE_WORDS",
    "_MAX_DISCOVERED_OFFERS",
    "_MAX_PAGES_PER_SCAN",
    "_MIN_SKINCARE_KEYWORDS",
]
