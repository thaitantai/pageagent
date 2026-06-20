#!/usr/bin/env python3
"""Performance predictor — lightweight linear model for research brief engagement.

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


class PerformancePredictor:
    """Lightweight linear predictor for research brief engagement.

    Model: log(engagement+1) = slope × total_score + intercept

    Trained on historical research_briefs that have actual performance data
    (via get_brief_feedback). The model maps total_score (0-1 range) to
    predicted engagement count using a log-linear regression.
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
        mape = (
            sum(abs(preds_eng[i] - actuals_eng[i]) / max(1, actuals_eng[i]) for i in range(n)) / n
        )

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
            "drift_message": "MAPE > 40% — consider tuning weights or recalibrating"
            if drift
            else None,
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


__all__ = ["PerformancePredictor"]
