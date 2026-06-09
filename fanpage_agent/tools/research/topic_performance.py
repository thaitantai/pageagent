#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TOPIC_FEEDBACK_DIR = Path("data/topic_feedback")
_TOPIC_FEEDBACK_FILE = _TOPIC_FEEDBACK_DIR / "performance_history.json"


class TopicPerformanceRecord:
    """Aggregated performance for a topic over time."""

    def __init__(
        self,
        topic: str,
        total_reach: int = 0,
        total_engagements: int = 0,
        total_posts: int = 0,
        avg_engagement_rate: float = 0.0,
        recent_engagement: float = 0.0,
        updated_at: str = "",
    ):
        self.topic = topic
        self.total_reach = total_reach
        self.total_engagements = total_engagements
        self.total_posts = total_posts
        self.avg_engagement_rate = avg_engagement_rate
        self.recent_engagement = recent_engagement
        self.updated_at = updated_at or datetime.now(timezone.utc).isoformat()

    @property
    def score(self) -> float:
        """Performance score 0-1 for topic boost."""
        if self.total_posts == 0:
            return 0.0
        avg_reach = self.total_reach / max(1, self.total_posts)
        # Normalize: reach > 500 is good, > 2000 is great
        reach_score = min(1.0, avg_reach / 2000.0)
        engagement_score = min(1.0, self.avg_engagement_rate / 0.08)
        recency_bonus = min(0.1, self.recent_engagement * 0.02)
        return round(max(0.0, min(1.0, reach_score * 0.45 + engagement_score * 0.35 + recency_bonus)), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "total_reach": self.total_reach,
            "total_engagements": self.total_engagements,
            "total_posts": self.total_posts,
            "avg_engagement_rate": self.avg_engagement_rate,
            "recent_engagement": self.recent_engagement,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TopicPerformanceRecord:
        return cls(**data)


class TopicPerformanceStore:
    """Persist topic performance across research sessions.

    Updated by Analyst sau mỗi publish cycle.
    Read by ResearchTool để boost topic scores.
    """

    def __init__(self, file_path: str | Path | None = None):
        self._file_path = Path(file_path or _TOPIC_FEEDBACK_FILE)
        self._records: dict[str, TopicPerformanceRecord] = {}
        self._load()

    # ── Public API ─────────────────────────────────────────────

    def get_top_topics(self, limit: int = 5, min_score: float = 0.3) -> list[str]:
        """Trả về topic có score cao nhất."""
        sorted_records = sorted(self._records.values(), key=lambda r: r.score, reverse=True)
        return [r.topic for r in sorted_records if r.score >= min_score][:limit]

    def get_topic_boost(self, topic: str, default: float = 0.0) -> float:
        """Boost factor (0-0.15) cho topic nếu đã từng chạy tốt."""
        record = self._records.get(topic)
        if not record:
            return default
        return min(0.15, record.score * 0.15)

    def record_published(
        self,
        topic: str,
        reach: int,
        engagements: int,
        engagement_rate: float,
    ) -> None:
        """Ghi nhận kết quả sau publish (gọi từ Analyst)."""
        now = datetime.now(timezone.utc).isoformat()
        if topic in self._records:
            existing = self._records[topic]
            existing.total_reach += max(0, reach)
            existing.total_engagements += max(0, engagements)
            existing.total_posts += 1
            # Rolling average
            existing.avg_engagement_rate = (
                existing.avg_engagement_rate * (existing.total_posts - 1) + engagement_rate
            ) / existing.total_posts
            existing.recent_engagement = engagement_rate
            existing.updated_at = now
        else:
            self._records[topic] = TopicPerformanceRecord(
                topic=topic,
                total_reach=max(0, reach),
                total_engagements=max(0, engagements),
                total_posts=1,
                avg_engagement_rate=engagement_rate,
                recent_engagement=engagement_rate,
                updated_at=now,
            )
        self._save()

    def all_topics(self) -> dict[str, TopicPerformanceRecord]:
        return dict(self._records)

    # ── Internal ───────────────────────────────────────────────

    def _load(self) -> None:
        if not self._file_path.exists():
            self._records = {}
            return
        try:
            data = json.loads(self._file_path.read_text(encoding="utf-8"))
            self._records = {
                topic: TopicPerformanceRecord.from_dict(rec)
                for topic, rec in data.items()
            }
        except (json.JSONDecodeError, IOError, TypeError) as exc:
            logger.warning("TopicPerformanceStore: load failed — %s", exc)
            self._records = {}

    def _save(self) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_path.write_text(
            json.dumps(
                {topic: rec.to_dict() for topic, rec in self._records.items()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
