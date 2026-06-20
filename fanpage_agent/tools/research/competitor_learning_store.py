"""Helper functions for competitor learning persistence and conversion.

Extracted from competitor_learning_engine.py for cleaner separation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Candidates → competitor promotion threshold (total_score)
_AUTO_PROMOTE_MIN_SCORE = 3.0

# Discovery search queries (chained from existing competitor names)
_DISCOVERY_QUERIES: list[str] = [
    'thương hiệu skincare như "{name}"',
]

# Minimum score per mention (each time a candidate is found)
_CANDIDATE_MENTION_SCORE = 1.0


def profile_to_dict(profile: Any) -> dict[str, Any]:
    """Convert CompetitorProfile dataclass to dict."""
    return {
        "name": profile.name,
        "top_products": profile.top_products,
        "price_positioning": profile.price_positioning,
        "content_tone": profile.content_tone,
        "top_format": profile.top_format,
        "unique_angle": profile.unique_angle,
        "findings_count": profile.findings_count,
        "search_urls": profile.search_urls,
        "analyzed_at": profile.analyzed_at,
    }


def insight_to_gaps(insight: Any) -> list[dict[str, Any]]:
    """Convert CrossCompetitorInsight to gap DB records."""
    gaps: list[dict[str, Any]] = []
    for g in insight.gap_products:
        gaps.append(
            {
                "gap_type": "product",
                "gap_name": g,
                "description": f"Sản phẩm chưa đối thủ nào khai thác: {g}",
                "opportunity_level": "high",
            }
        )
    for f in insight.underused_formats:
        gaps.append(
            {
                "gap_type": "format",
                "gap_name": f,
                "description": f"Format nội dung chưa ai dùng: {f}",
                "opportunity_level": "medium",
            }
        )
    return gaps


def extract_next_topics(profile: Any, insight: Any) -> list[str]:
    """Từ profile + insight → gợi ý topic nên khai thác."""
    topics: list[str] = []
    # Gap products → topics
    for g in insight.gap_products[:3]:
        topics.append(f"{g} — góc nhìn từ đối thủ")
    # Underused formats
    for f in insight.underused_formats[:2]:
        topic = f"Khám phá format {f} — nội dung từ đối thủ"
        if topic not in topics:
            topics.append(topic)
    # Products only this competitor covers
    for p in profile.products_detected[:3]:
        topic = f"{p}: góc nhìn từ đối thủ"
        if topic not in topics:
            topics.append(topic)
    return topics[:5]


def extract_brand_names(
    text: str,
    known_names: set[str],
) -> list[tuple[str, float]]:
    """Trích xuất tên brand tiềm năng từ text search result.

    Heuristic-based: tìm uppercase phrases, brand-like patterns.
    """
    candidates: list[tuple[str, float]] = []

    # Pattern: "X vs Y" / "X hay Y" / "X và Y"
    comparison_matches = re.findall(
        r"(?:vs|versus|hay|và|so sánh|comparison|vs\.)\s+([A-ZÀ-Ỹ][A-Za-zÀ-ỹ0-9\s]{2,30}?)",
        text,
        re.IGNORECASE,
    )
    for m in comparison_matches:
        m_clean = m.strip().rstrip(".,;!")
        if m_clean and m_clean.lower() not in known_names:
            candidates.append((m_clean, 1.5))

    # Pattern: brand-like words (capitalized, 2+ words)
    brand_pattern = re.findall(
        r"((?:[A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s|$)){2,4})",
        text,
    )
    seen: set[str] = set()
    for bp in brand_pattern:
        bp_clean = bp.strip()
        bp_lower = bp_clean.lower()
        if bp_lower in known_names or bp_lower in seen:
            continue
        # Skip common words
        if bp_lower in ("skincare", "beauty", "review", "makeup", "cosmetic"):
            continue
        if len(bp_clean) < 4:
            continue
        # Check if skincare-related
        if any(kw in bp_lower for kw in ("skin", "beauty", "care", "cosmetic", "herbal")):
            candidates.append((bp_clean, 1.0))
            seen.add(bp_lower)

    # Dedup by name
    deduped: dict[str, float] = {}
    for name, score in candidates:
        deduped[name] = max(deduped.get(name, 0), score)

    return sorted(deduped.items(), key=lambda x: x[1], reverse=True)


__all__ = [
    "profile_to_dict",
    "insight_to_gaps",
    "extract_next_topics",
    "extract_brand_names",
    "_AUTO_PROMOTE_MIN_SCORE",
    "_DISCOVERY_QUERIES",
    "_CANDIDATE_MENTION_SCORE",
]
