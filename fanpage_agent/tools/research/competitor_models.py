"""Data types for competitor analysis.

Extracted from competitor_page_discovery.py for cleaner separation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContentFormat:
    """Định dạng nội dung phát hiện được."""

    type: str  # review, comparison, tutorial, ingredient_deep_dive, deal, qa, unboxing
    confidence: float  # 0.0 - 1.0
    clues: list[str] = field(default_factory=list)


@dataclass
class CompetitorProfile:
    """Hồ sơ phân tích một đối thủ."""

    name: str
    # Products focus
    products_detected: list[str] = field(default_factory=list)
    top_products: list[str] = field(default_factory=list)
    # Content angles
    angles_detected: list[str] = field(default_factory=list)
    top_angle: str = ""
    # Content formats
    formats_detected: list[ContentFormat] = field(default_factory=list)
    top_format: str = ""
    # Tone & positioning (heuristic-based)
    price_positioning: str = ""  # budget / mid / premium
    content_tone: str = ""  # educational / review / scientific / entertaining
    # Raw findings
    search_urls: list[str] = field(default_factory=list)
    findings_count: int = 0
    # Unique angle (what makes this competitor different)
    unique_angle: str = ""
    # Timestamp
    analyzed_at: str = ""


@dataclass
class CrossCompetitorInsight:
    """Cross-competitor intelligence."""

    shared_products: list[tuple[str, int]] = field(default_factory=list)
    unique_products_by_competitor: dict[str, list[str]] = field(default_factory=dict)
    gap_products: list[str] = field(default_factory=list)
    underused_formats: list[str] = field(default_factory=list)
    recommendation: str = ""


__all__ = [
    "ContentFormat",
    "CompetitorProfile",
    "CrossCompetitorInsight",
]
