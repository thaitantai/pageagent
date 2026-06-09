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
import math
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


# ─── Per-goal weight limits ──────────────────────────────────────

_GOAL_WEIGHT_LIMITS: dict[str, dict[str, tuple[float, float]]] = {
    "reach": {
        "brand_relevance": (0.08, 0.38),
        "novelty": (0.12, 0.35),
        "content_potential": (0.06, 0.26),
        "source_confidence": (0.06, 0.22),
        "fanpage_fit": (0.06, 0.22),
        "customer_value": (0.04, 0.16),
        "duplication_risk_penalty": (0.01, 0.05),
    },
    "engagement": {
        "brand_relevance": (0.10, 0.40),
        "novelty": (0.06, 0.24),
        "content_potential": (0.10, 0.36),
        "source_confidence": (0.08, 0.26),
        "fanpage_fit": (0.08, 0.26),
        "customer_value": (0.06, 0.20),
        "duplication_risk_penalty": (0.02, 0.06),
    },
    "conversion": {
        "brand_relevance": (0.12, 0.40),
        "novelty": (0.04, 0.18),
        "content_potential": (0.08, 0.30),
        "source_confidence": (0.10, 0.30),
        "fanpage_fit": (0.10, 0.28),
        "customer_value": (0.08, 0.26),
        "duplication_risk_penalty": (0.04, 0.10),
    },
    "balanced": {
        "brand_relevance": (0.10, 0.40),
        "novelty": (0.06, 0.28),
        "content_potential": (0.08, 0.30),
        "source_confidence": (0.06, 0.24),
        "fanpage_fit": (0.06, 0.24),
        "customer_value": (0.04, 0.18),
        "duplication_risk_penalty": (0.01, 0.08),
    },
}


class GoalWeightOptimizer:
    """Adjust per-goal scoring weights based on variance analysis.

    Each goal type (reach, engagement, conversion, balanced) has its own
    weight set with limits tailored to that objective. The optimizer runs
    independently per goal, looking only at published briefs whose topics
    are assigned to that goal.
    """

    def __init__(self, store: UnifiedStore) -> None:
        self._store = store

    def run(self, goal_type: str) -> dict[str, Any]:
        """Run optimization for a specific goal type. Returns changes summary."""
        if goal_type not in self._store.GOAL_TYPES:
            return {"status": "skipped", "reason": f"unknown goal type: {goal_type}", "changes": []}

        analysis = self._store.get_goal_weight_variance_analysis(goal_type)
        if not analysis:
            return {"status": "skipped", "reason": f"insufficient data for goal '{goal_type}'", "changes": []}

        changes: list[dict[str, Any]] = []
        limits = _GOAL_WEIGHT_LIMITS.get(goal_type, _GOAL_WEIGHT_LIMITS["balanced"])

        for item in analysis:
            name = item["weight_name"]
            corr = item["correlation"]
            current = item["current_weight"]
            sample_size = item["sample_size"]
            lo, hi = limits.get(name, (0.05, 0.30))

            # PID: delta = Kp × (|corr| - target)
            abs_corr = abs(corr)
            if abs_corr >= _TARGET_ABS_CORR:
                delta = _PID_KP * (abs_corr - _TARGET_ABS_CORR) * 2.0
            elif abs_corr < 0.10:
                delta = -_PID_KP * 0.5
            else:
                delta = -_PID_KP * 0.2

            new_weight = max(lo, min(hi, current + delta))
            new_weight = round(new_weight, 4)

            if new_weight != current:
                self._store.update_goal_weight(goal_type, name, new_weight, correlation_7d=corr)
                changes.append({
                    "weight_name": name,
                    "from": current,
                    "to": new_weight,
                    "correlation": corr,
                    "sample_size": sample_size,
                    "goal_type": goal_type,
                    "delta": round(new_weight - current, 4),
                })

        # Audit log
        self._store.log_learning_run(
            run_type=f"goal_weight_optimization_{goal_type}",
            summary={
                "goal_type": goal_type,
                "changes": changes,
                "analysis_count": len(analysis),
            },
        )

        return {
            "status": "ok" if changes else "no_change",
            "goal_type": goal_type,
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
                    from datetime import datetime, timezone
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
                    from datetime import datetime, timezone
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


# ─── Performance Predictor ──────────────────────────────────────

class PerformancePredictor:
    """Lightweight linear predictor for research brief engagement.

    Model: log(engagement+1) = slope × total_score + intercept

    Trained on historical research_briefs that have actual performance data
    (via get_brief_feedback). The model maps total_score (0-1 range) to
    predicted engagement count using a log-linear regression.

    Tracks prediction quality:
    - MAE: mean absolute error in engagement count
    - MAPE: mean absolute percentage error (drift alert when > 40%)
    - R²: coefficient of determination
    - sample_count: number of data points used for training
    - drift: True when MAPE exceeds drift threshold
    """

    def __init__(self, store: "UnifiedStore") -> None:
        self._store = store
        self._slope = 0.6
        self._intercept = 0.3
        self._trained = False

    # ── Public API ──────────────────────────────────────────────

    def train(self, force_recompute: bool = False) -> dict[str, Any]:
        """Train the predictor on historical data.

        Returns a report dict with status, metrics, and model params.
        """
        briefs = self._store.get_brief_feedback(since_days=90)
        if len(briefs) < 5:
            return {"status": "skipped", "reason": f"insufficient data ({len(briefs)} briefs)"}

        # Filter to briefs with actual engagement > 0
        pairs: list[tuple[float, float]] = []
        for b in briefs:
            eng = b.get("engagements", 0)
            score = b.get("brief_score", 0)
            if eng is not None and eng > 0 and score > 0:
                pairs.append((score, math.log(eng + 1)))
        if len(pairs) < 5:
            return {"status": "skipped", "reason": f"insufficient engaged briefs ({len(pairs)})"}

        # Linear regression: log(eng+1) = a × score + b
        n = len(pairs)
        X = [p[0] for p in pairs]
        y = [p[1] for p in pairs]
        mean_x = sum(X) / n
        mean_y = sum(y) / n

        num = sum((X[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        den = sum((X[i] - mean_x) ** 2 for i in range(n))
        slope = num / den if abs(den) > 1e-10 else 0.6
        intercept = mean_y - slope * mean_x

        self._slope = slope
        self._intercept = intercept
        self._trained = True

        # Compute metrics
        predictions_log = [slope * x + intercept for x in X]
        actuals_eng = [math.exp(yp) - 1 for yp in y]
        preds_eng = [max(0, math.exp(p) - 1) for p in predictions_log]

        mae = sum(abs(preds_eng[i] - actuals_eng[i]) for i in range(n)) / n
        mape = sum(
            abs(preds_eng[i] - actuals_eng[i]) / max(1, actuals_eng[i])
            for i in range(n)
        ) / n

        mean_actual = sum(actuals_eng) / n
        ss_res = sum((actuals_eng[i] - preds_eng[i]) ** 2 for i in range(n))
        ss_tot = sum((actuals_eng[i] - mean_actual) ** 2 for i in range(n))
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-10 else 0.0

        drift = mape > 0.40

        state = {
            "params": {"slope": round(slope, 4), "intercept": round(intercept, 4)},
            "metrics": {
                "mae": round(mae, 2),
                "mape": round(mape, 4),
                "r2": round(r2, 4),
            },
            "drift": drift,
            "drift_message": "MAPE > 40% — consider tuning weights or recalibrating" if drift else None,
            "sample_count": n,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }

        self._store.save_predictor_state(state)
        self._store.log_learning_run(
            run_type="predictor_training",
            summary=state,
        )
        return {
            "status": "ok",
            **state,
        }

    def predict(self, total_score: float) -> dict[str, Any]:
        """Predict engagement for a given total_score (0-1)."""
        if not self._trained:
            state = self._store.get_predictor_state()
            if state and state.get("params"):
                self._slope = state["params"]["slope"]
                self._intercept = state["params"]["intercept"]
                self._trained = True

        log_pred = self._slope * max(0.0, min(1.0, total_score)) + self._intercept
        predicted_engagement = max(0, math.exp(log_pred) - 1)

        # Confidence: based on how far score is from training distribution
        confidence = min(1.0, max(0.1, total_score / 0.8))

        return {
            "predicted_engagement": round(predicted_engagement, 1),
            "log_prediction": round(log_pred, 4),
            "confidence": round(confidence, 2),
        }

    def get_quality(self) -> dict[str, Any]:
        """Return current predictor quality metrics (read from store)."""
        state = self._store.get_predictor_state()
        if not state:
            return {
                "status": "untrained",
                "mae": None,
                "mape": None,
                "r2": None,
                "sample_count": 0,
                "drift": False,
                "message": "Predictor chưa được train. Chạy 'fanpage-agent learn --predict'.",
            }
        return {
            "status": "trained",
            "mae": state.get("metrics", {}).get("mae"),
            "mape": state.get("metrics", {}).get("mape"),
            "r2": state.get("metrics", {}).get("r2"),
            "sample_count": state.get("sample_count", 0),
            "drift": state.get("drift", False),
            "drift_message": state.get("drift_message"),
            "trained_at": state.get("trained_at"),
        }

    def detect_concept_drift(self) -> bool:
        """Check if current predictor is drifting (MAPE > 40%)."""
        return self.get_quality().get("drift", False)
