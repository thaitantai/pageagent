"""Helper functions for ResearchTool.

Extracted from research.py for cleaner separation.
Contains standalone utility functions used in research brief building.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fanpage_agent.models import (
    CommentInboxEntry,
    ResearchEvidence,
    TrendItem,
)

logger = logging.getLogger(__name__)


def read_comments(path: str | Path | None) -> list[CommentInboxEntry]:
    """Read comments from CSV file."""
    if not path:
        return []
    file_path = Path(path)
    if not file_path.exists():
        return []
    with file_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        CommentInboxEntry(
            id=row.get("id", ""),
            post_id=row.get("post_id", ""),
            created_at=row.get("created_at", ""),
            source=row.get("source", ""),
            message=row.get("message", ""),
        )
        for row in rows
        if row.get("message")
    ]


def read_campaign_notes(path: str | Path | None) -> dict:
    """Read campaign notes from JSON file."""
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))


def dedupe(items: list[str]) -> list[str]:
    """Deduplicate list preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def keyword_overlap_score(topic: str, references: list[str]) -> float:
    """Semantic overlap score using fuzzy string matching.

    Uses difflib.SequenceMatcher for character-based similarity,
    which handles partial matches, word order, and Vietnamese text
    better than simple word-set overlap.

    If rapidfuzz is installed, uses it for faster/better results.
    """
    if not topic or not references:
        return 0.0
    topic_lower = topic.lower().strip()
    try:
        from rapidfuzz import fuzz
        scores = [
            fuzz.token_sort_ratio(topic_lower, ref.lower()) / 100.0
            for ref in references
        ]
    except ImportError:
        from difflib import SequenceMatcher
        scores = [
            SequenceMatcher(None, topic_lower, ref.lower()).ratio()
            for ref in references
        ]
    return min(1.0, max(scores))


def confidence_score(evidence: list[ResearchEvidence]) -> float:
    """Average confidence score across evidence items."""
    if not evidence:
        return 0.0
    return round(sum(item.confidence for item in evidence) / len(evidence), 3)


def quality_warnings(evidence: list[ResearchEvidence], external_trends: list[TrendItem]) -> list[str]:
    """Generate quality warnings from evidence and trends."""
    warnings: list[str] = []
    if not external_trends:
        warnings.append("Không có external_trends; Research chỉ dựa vào dữ liệu nội bộ/operator.")
    source_count = len({item.source for item in evidence if item.source})
    if source_count < 2:
        warnings.append("Evidence chưa đủ đa nguồn; cần thêm ít nhất 2 nguồn độc lập.")
    if not any(item.url for item in evidence):
        warnings.append("Evidence chưa có URL nguồn để Writer trích dẫn hoặc kiểm chứng.")
    return warnings


__all__ = [
    "read_comments",
    "read_campaign_notes",
    "dedupe",
    "keyword_overlap_score",
    "confidence_score",
    "quality_warnings",
]
