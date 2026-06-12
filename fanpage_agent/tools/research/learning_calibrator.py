#!/usr/bin/env python3
"""Confidence calibrator — adjust confidence thresholds based on prediction errors.

Extracted from learning_optimizer.py for cleaner separation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fanpage_agent.adapters.sqlite_store import UnifiedStore

logger = logging.getLogger(__name__)


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
        baseline_name = "engagement_baseline"
        current_baseline = self._store.get_weights().get(baseline_name, 50.0)

        briefs = self._store.get_brief_feedback(since_days=30)
        if briefs:
            actuals = [
                b["engagements"] for b in briefs
                if b.get("engagements") is not None and b["engagements"] > 0
            ]
            if actuals:
                optimal_baseline = sum(actuals) / len(actuals)
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


__all__ = ["ConfidenceCalibrator"]
