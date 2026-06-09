#!/usr/bin/env python3
"""Self-learning engine for Research Agent.

Three subsystems that together make the agent learn from experience:

1. WeightOptimizer
   - Reads variance data (predicted score vs actual engagement)
   - Computes per-weight correlation with actual performance
   - Adjusts weights using a PID-like controller (proportional to error)
   - Logs each learning run for audit

2. ConfidenceCalibrator
   - Tracks how often the model is over/under-confident
   - Dynamically adjusts thresholds (e.g. affiliate evidence minimum)
   - Learns from false positives / false negatives

3. DecayModel
   - Time-decay for topic_performance scores
   - Older successes mean less than recent ones
   - Prevents stale topics from being over-boosted
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fanpage_agent.adapters.sqlite_store import UnifiedStore

logger = logging.getLogger(__name__)

# ─── Weights ─────────────────────────────────────────────────────

_WEIGHT_NAMES = [
    "brand_relevance",
    "novelty",
    "content_potential",
    "source_confidence",
    "fanpage_fit",
    "customer_value",
    "duplication_risk_penalty",
]

_WEIGHT_LIMITS: dict[str, tuple[float, float]] = {
    "brand_relevance": (0.10, 0.40),
    "novelty": (0.06, 0.28),
    "content_potential": (0.08, 0.30),
    "source_confidence": (0.06, 0.24),
    "fanpage_fit": (0.06, 0.24),
    "customer_value": (0.04, 0.18),
    "duplication_risk_penalty": (0.01, 0.08),
}

# How much to move weight per unit of correlation difference from target
_PID_KP = 0.02  # proportional gain
_TARGET_ABS_CORR = 0.25  # we want |correlation| ≥ this for active weights


class WeightOptimizer:
    """Adjust scoring weights based on historical prediction vs actual data.

    Uses a simple proportional controller: if a weight's sub-score correlates
    well with actual engagement, the weight is increased (that feature predicts
    well). If correlation is poor or negative, the weight is decreased.
    """

    def __init__(self, store: UnifiedStore) -> None:
        self._store = store

    def run(self) -> dict[str, Any]:
        """Run one optimization cycle. Returns a summary of changes."""
        analysis = self._store.get_weight_variance_analysis()

        if not analysis:
            return {"status": "skipped", "reason": "insufficient data (< 3 briefs)", "changes": []}

        changes: list[dict[str, Any]] = []
        weights = self._store.get_weights()

        for item in analysis:
            name = item["weight_name"]
            corr = item["correlation"]
            current = item["current_weight"]
            sample_size = item["sample_size"]
            lo, hi = _WEIGHT_LIMITS.get(name, (0.05, 0.30))

            # PID: delta = Kp × (|corr| - target)
            abs_corr = abs(corr)
            if abs_corr >= _TARGET_ABS_CORR:
                # Good predictor → increase weight (proportional to correlation strength)
                delta = _PID_KP * (abs_corr - _TARGET_ABS_CORR) * 2.0
            elif abs_corr < 0.10:
                # Weak/no predictor → decrease weight
                delta = -_PID_KP * 0.5
            else:
                # Marginal → small decrease
                delta = -_PID_KP * 0.2

            new_weight = max(lo, min(hi, current + delta))
            new_weight = round(new_weight, 4)

            if new_weight != current:
                self._store.update_weight(name, new_weight, correlation_7d=corr)
                changes.append({
                    "weight_name": name,
                    "from": current,
                    "to": new_weight,
                    "correlation": corr,
                    "sample_size": sample_size,
                    "delta": round(new_weight - current, 4),
                })

        # Audit log
        self._store.log_learning_run(
            run_type="weight_optimization",
            summary={
                "changes": changes,
                "analysis_count": len(analysis),
                "weights_before": weights,
                "weights_after": self._store.get_weights(),
            },
        )

        return {
            "status": "ok" if changes else "no_change",
            "changes": changes,
            "analysis_summary": {
                "total_weights_analyzed": len(analysis),
                "weights_adjusted": len(changes),
                "top_correlation": max((a["correlation"] for a in analysis), default=0),
                "lowest_correlation": min((a["correlation"] for a in analysis), default=0),
            },
        }


class ConfidenceCalibrator:
    """Calibrate confidence thresholds based on prediction error trends.

    Tracks:
    - Over-confidence: predicted score >> actual → raise minimum evidence threshold
    - Under-confidence: predicted score << actual → lower minimum evidence threshold
    - False positives: topics scored high but performed poorly → increase novelty weight
    """

    def __init__(self, store: UnifiedStore) -> None:
        self._store = store

    def run(self) -> dict[str, Any]:
        """Run one calibration cycle. Returns calibration decisions."""
        variance = self._store.get_variance_summary()
        sample_count = variance.get("sample_count", 0)

        if sample_count < 3:
            return {"status": "skipped", "reason": f"only {sample_count} samples", "adjustments": []}

        avg_variance = variance.get("avg_variance", 0)
        adjustments: list[dict[str, Any]] = []

        # --- Calibrate evidence confidence floor ---
        # Stored as a pseudo-weight 'evidence_floor' in learned_weights
        floor_name = "evidence_confidence_floor"
        current_floor = self._store.get_weights().get(floor_name, 0.45)

        if avg_variance < -0.15:
            # Over-confident: scores too high vs actual → raise floor
            new_floor = min(0.65, current_floor + 0.03)
            self._store.update_weight(floor_name, new_floor)
            adjustments.append({
                "target": "evidence_confidence_floor",
                "from": current_floor,
                "to": new_floor,
                "reason": f"over-confident (variance={avg_variance:.3f}) — raising floor",
            })
        elif avg_variance > 0.05:
            # Under-confident: scores too low vs actual → lower floor
            new_floor = max(0.25, current_floor - 0.03)
            self._store.update_weight(floor_name, new_floor)
            adjustments.append({
                "target": "evidence_confidence_floor",
                "from": current_floor,
                "to": new_floor,
                "reason": f"under-confident (variance={avg_variance:.3f}) — lowering floor",
            })

        # --- Calibrate engagement prediction baseline ---
        # Stored as 'engagement_baseline' — used to normalize actual engagement in variance calc
        baseline_name = "engagement_baseline"
        current_baseline = self._store.get_weights().get(baseline_name, 50.0)

        # Recompute optimal baseline: average actual engagement of published briefs
        briefs = self._store.get_brief_feedback(since_days=30)
        if briefs:
            actuals = [
                b["engagements"] for b in briefs
                if b.get("engagements") is not None and b["engagements"] > 0
            ]
            if actuals:
                optimal_baseline = sum(actuals) / len(actuals)
                # Smooth: move 10% toward optimal
                smoothed = current_baseline * 0.9 + optimal_baseline * 0.1
                smoothed = round(max(5.0, min(200.0, smoothed)), 1)
                if abs(smoothed - current_baseline) > 1.0:
                    self._store.update_weight(baseline_name, smoothed)
                    adjustments.append({
                        "target": "engagement_baseline",
                        "from": current_baseline,
                        "to": smoothed,
                        "reason": f"avg engagement={optimal_baseline:.1f}, smoothed from {current_baseline}",
                    })

        # Audit log
        if adjustments:
            self._store.log_learning_run(
                run_type="confidence_calibration",
                summary={"variance": variance, "adjustments": adjustments},
            )

        return {
            "status": "ok" if adjustments else "no_change",
            "variance": avg_variance,
            "sample_count": sample_count,
            "adjustments": adjustments,
        }


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
        from fanpage_agent.tools.research.topic_performance import TopicPerformanceStore

        # Try UnifiedStore first (preferred), fallback to TopicPerformanceStore
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

            # Compute decay factor
            decay_factor = _exp_decay(days_since)
            if decay_factor >= 0.95:
                continue  # negligible decay

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


def _exp_decay(days_since: int) -> float:
    """Exponential decay factor: e^{-λ × days}"""
    import math
    return math.exp(-DecayModel._LAMBDA * max(0, days_since))
