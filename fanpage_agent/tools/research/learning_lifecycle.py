#!/usr/bin/env python3
"""Topic lifecycle management and score decay.

Extracted from learning_optimizer.py for cleaner separation.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fanpage_agent.adapters.sqlite_store import UnifiedStore

logger = logging.getLogger(__name__)


class DecayModel:
    """Time-based decay for topic performance scores.

    A topic that performed well 60 days ago should have less boost
    than one that performed well 3 days ago.

    Decay function: decayed_score = score × exp(-λ × days_since_update)
    λ (lambda) controls how fast the memory fades.
    """

    # Half-life: score decays to 50% after HL days
    _HALF_LIFE_DAYS = 21.0
    _LAMBDA = 0.693 / _HALF_LIFE_DAYS  # ln(2) / HL

    def __init__(self, store: UnifiedStore) -> None:
        self._store = store

    def run(self, force_decay: bool = False) -> dict[str, Any]:
        """Apply decay to topic_performance records. Returns decay summary."""

        tp = self._store.get_topic_performance()
        if not tp:
            return {"status": "skipped", "reason": "no topic performance data", "decayed_topics": 0}

        now = datetime.now(timezone.utc)
        decayed: list[dict[str, Any]] = []

        for record in tp:
            topic = record["topic"]
            try:
                updated = datetime.fromisoformat(record["updated_at"])
            except (ValueError, TypeError):
                continue
            days_since = (now - updated).days
            if days_since < 3 and not force_decay:
                continue

            decay_factor = _exp_decay(days_since)
            if decay_factor >= 0.95:
                continue

            new_avg_rate = round(record["avg_engagement_rate"] * decay_factor, 4)
            self._store.update_topic_performance_decay(topic, new_avg_rate, decay_factor)

            decayed.append({
                "topic": topic,
                "days_since_update": days_since,
                "decay_factor": round(decay_factor, 3),
                "avg_eng_rate_before": record["avg_engagement_rate"],
                "avg_eng_rate_after": new_avg_rate,
            })

        if decayed:
            self._store.log_learning_run(
                run_type="topic_decay",
                summary={"decayed_count": len(decayed), "topics": [d["topic"] for d in decayed]},
            )

        return {
            "status": "ok" if decayed else "no_decay_needed",
            "decayed_topics": len(decayed),
            "total_topics": len(tp),
            "details": decayed[:20],
        }


class LifecycleManager:
    """Manage topic lifecycle transitions.

    Lifecycle stages: explore → active → mature → retire

    Transitions:
    - publish-based: explore→active (≥3 posts), active→mature (≥8 posts)
    - inactivity-based: mature→retire (>60d inactive), explore→retire (>90d never published)
    - revival: retire→active (published again)
    """

    def __init__(self, store: UnifiedStore) -> None:
        self._store = store

    def run(self, force: bool = False) -> dict[str, Any]:
        """Run auto-transition scan. Returns summary of transitions."""
        transitions = self._store.auto_transition_lifecycles(force=force)
        status = "ok" if transitions else "no_change"

        if transitions:
            self._store.log_learning_run(
                run_type="lifecycle_transition",
                summary={"transitions": transitions},
            )

        return {
            "status": status,
            "transitions": transitions,
            "transition_count": len(transitions),
        }

    def get_lifecycle_report(self) -> dict[str, Any]:
        """Get full lifecycle report for all topics."""
        records = self._store.get_all_lifecycles()
        by_stage: dict[str, list[dict[str, Any]]] = {
            s: [] for s in self._store.LIFE_CYCLE_STAGES
        }
        for rec in records:
            s = rec["stage"]
            days_since = 0
            if rec.get("last_published_at"):
                try:
                    last = datetime.fromisoformat(rec["last_published_at"])
                    days_since = (datetime.now(timezone.utc) - last).days
                except (ValueError, TypeError):
                    pass
            entry = {
                "topic": rec["topic"],
                "stage": rec["stage"],
                "total_posts": rec["total_posts"],
                "first_published": rec["first_published_at"][:10] if rec["first_published_at"] else "",
                "last_published": rec["last_published_at"][:10] if rec["last_published_at"] else "",
                "days_since_publish": days_since,
                "days_in_stage": 0,
            }
            if rec.get("entered_stage_at"):
                try:
                    entered = datetime.fromisoformat(rec["entered_stage_at"])
                    entry["days_in_stage"] = (datetime.now(timezone.utc) - entered).days
                except (ValueError, TypeError):
                    pass
            by_stage[s].append(entry)
        return {
            "total_topics": len(records),
            "by_stage": {s: {"count": len(by_stage[s]), "topics": by_stage[s]}
                         for s in self._store.LIFE_CYCLE_STAGES},
            "active_topics": len(by_stage["active"]),
            "explore_topics": len(by_stage["explore"]),
            "mature_topics": len(by_stage["mature"]),
            "retired_topics": len(by_stage["retire"]),
        }


def _exp_decay(days_since: int) -> float:
    """Exponential decay factor: e^{-λ × days}"""
    return math.exp(-DecayModel._LAMBDA * max(0, days_since))


__all__ = ["DecayModel", "LifecycleManager", "_exp_decay"]
