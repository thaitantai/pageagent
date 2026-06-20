#!/usr/bin/env python3
"""Self-learning engine for Research Agent — weight optimizers.

Three subsystems that together make the agent learn from experience:

1. WeightOptimizer
   - Reads variance data (predicted score vs actual engagement)
   - Computes per-weight correlation with actual performance
   - Adjusts weights using a PID-like controller (proportional to error)
   - Logs each learning run for audit

2. GoalWeightOptimizer
   - Per-goal weight optimization (reach, engagement, conversion, balanced)

NOTE: ConfidenceCalibrator → learning_calibrator.py
      DecayModel + LifecycleManager → learning_lifecycle.py
      PerformancePredictor → learning_predictor.py
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fanpage_agent.tools.research.learning_calibrator import ConfidenceCalibrator
from fanpage_agent.tools.research.learning_lifecycle import DecayModel, LifecycleManager, _exp_decay
from fanpage_agent.tools.research.learning_predictor import PerformancePredictor

# ── Re-export for backward compatibility ─────────────────
_ = ConfidenceCalibrator, DecayModel, LifecycleManager, _exp_decay, PerformancePredictor

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


__all__ = [
    "WeightOptimizer",
    "GoalWeightOptimizer",
    "ConfidenceCalibrator",
    "DecayModel",
    "LifecycleManager",
    "PerformancePredictor",
    "_exp_decay",
    "_WEIGHT_NAMES",
    "_WEIGHT_LIMITS",
    "_GOAL_WEIGHT_LIMITS",
    "_PID_KP",
    "_TARGET_ABS_CORR",
]
