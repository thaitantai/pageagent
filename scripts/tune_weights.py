#!/usr/bin/env python3
"""Tune dynamic scoring weights based on actual performance data.

Reads research_briefs + post_metrics from agent.db, computes correlation
between each sub-score and actual engagement/leads, then adjusts weights.

Usage:
    python scripts/tune_weights.py                    # dry-run: show suggested changes
    python scripts/tune_weights.py --apply            # apply suggestions to DB
    python scripts/tune_weights.py --min-samples=5    # override min sample size
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

# ── Resolve project root ──────────────────────────────────────────
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from fanpage_agent.adapters.sqlite_store import UnifiedStore

# Weights to tune (ordered by category)
WEIGHT_NAMES = [
    "brand_relevance",
    "novelty",
    "content_potential",
    "source_confidence",
    "fanpage_fit",
    "customer_value",
    "duplication_risk_penalty",
]

# Bounds to keep weights from going extreme
WEIGHT_BOUNDS: dict[str, tuple[float, float]] = {
    "brand_relevance": (0.10, 0.40),
    "novelty": (0.05, 0.30),
    "content_potential": (0.08, 0.30),
    "source_confidence": (0.05, 0.25),
    "fanpage_fit": (0.05, 0.25),
    "customer_value": (0.03, 0.20),
    "duplication_risk_penalty": (0.01, 0.08),
}

# Safe step size per tuning cycle
MAX_ADJUSTMENT = 0.03


def compute_correlation(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mean_x) ** 2 for x in xs)) * math.sqrt(
        sum((y - mean_y) ** 2 for y in ys)
    )
    return round(num / den, 4) if den > 0 else 0.0


def load_feedback(store: UnifiedStore, since_days: int = 30) -> list[dict]:
    """Load briefs that were published + have actual metrics."""
    return store.get_brief_feedback(since_days=since_days)


def analyze_weight(
    name: str, briefs: list[dict], current_weight: float
) -> dict:
    """Analyze one weight: correlation, signal, suggested new value."""
    sub_key = name  # matches field name in research_briefs row
    scores: list[float] = []
    actuals: list[float] = []

    for b in briefs:
        sub_score = b.get(sub_key, 0) or 0
        # Use engagement as actual performance signal
        actual = (b.get("engagements", 0) or 0) / 50.0  # normalize: 50 eng = 1.0
        if sub_score > 0 and actual >= 0:
            scores.append(sub_score)
            actuals.append(min(1.0, actual))

    correlation = compute_correlation(scores, actuals) if len(scores) >= 3 else 0.0
    sample_size = len(scores)

    # Determine adjustment direction
    if sample_size < 3 or abs(correlation) < 0.1:
        direction = "stable"
        delta = 0.0
    elif correlation > 0.3:
        direction = "increase"
        delta = min(MAX_ADJUSTMENT, correlation * 0.05)
    elif correlation < -0.1:
        direction = "decrease"
        delta = -min(MAX_ADJUSTMENT, abs(correlation) * 0.05)
    else:
        direction = "stable"
        delta = 0.0

    suggested = max(
        WEIGHT_BOUNDS[name][0],
        min(WEIGHT_BOUNDS[name][1], current_weight + delta),
    )

    return {
        "weight_name": name,
        "current_weight": round(current_weight, 4),
        "suggested_weight": round(suggested, 4),
        "delta": round(suggested - current_weight, 4),
        "correlation": correlation,
        "sample_size": sample_size,
        "direction": direction,
    }


def print_report(results: list[dict]) -> None:
    """Print a human-readable tuning report."""
    print("=" * 72)
    print("  Weight Tuning Report")
    print("=" * 72)
    print(f"  {'Weight':<28} {'Current':>8} {'Suggested':>10} {'Δ':>8}  {'Corr':>6}  {'Samples':>7}  Signal")
    print("  " + "-" * 72)

    for r in results:
        arrow = {
            "increase": "▲",
            "decrease": "▼",
            "stable": "─",
        }.get(r["direction"], "?")

        print(
            f"  {r['weight_name']:<28}"
            f" {r['current_weight']:>8.4f}"
            f" {r['suggested_weight']:>10.4f}"
            f" {r['delta']:>+8.4f}"
            f" {r['correlation']:>+6.3f}"
            f" {r['sample_size']:>7d}"
            f"  {arrow}"
        )

    print("=" * 72)
    adjust_count = sum(1 for r in results if abs(r["delta"]) > 0.0001)
    print(f"  {adjust_count} weight(s) with suggested adjustments.")
    print()


def apply_weights(store: UnifiedStore, results: list[dict]) -> None:
    """Write suggested weights back to the learned_weights table."""
    updated = 0
    for r in results:
        if abs(r["delta"]) > 0.0001:
            store.update_weight(
                weight_name=r["weight_name"],
                new_weight=r["suggested_weight"],
                correlation_7d=r["correlation"],
                correlation_30d=r["correlation"],
            )
            updated += 1

    print(f"✅ Applied {updated} weight adjustment(s) to learned_weights.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Tune dynamic scoring weights")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply suggested weight changes to DB (default: dry-run)",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=30,
        help="Days of brief feedback data to analyze (default: 30)",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=3,
        help="Minimum samples per weight for adjustment (default: 3)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Override agent.db path",
    )
    args = parser.parse_args()

    store = UnifiedStore(db_path=args.db_path)

    briefs = load_feedback(store, since_days=args.since_days)
    if not briefs:
        print("📭 No published briefs with metrics found.")
        print("   → Run fanpage-agent record-post-metrics first.")
        print("   → Or publish some posts then fetch metrics.")
        return 1

    current_weights = store.get_weights()
    print(f"\n📊 Analyzing {len(briefs)} published brief(s) across "
          f"{len(briefs)} post(s)...")

    results: list[dict] = []
    for name in WEIGHT_NAMES:
        current = current_weights.get(name, 0.15)
        result = analyze_weight(name, briefs, current)

        # Skip if too few samples
        if result["sample_size"] < args.min_samples:
            result["direction"] = "stable"
            result["suggested_weight"] = result["current_weight"]
            result["delta"] = 0.0

        results.append(result)

    results.sort(key=lambda r: abs(r["correlation"]), reverse=True)
    print_report(results)

    if args.apply:
        apply_weights(store, results)
        # Show updated state
        updated = store.get_weights()
        print("📋 Current weights in DB:")
        for name in WEIGHT_NAMES:
            print(f"  {name:<28} {updated.get(name, 0):>8.4f}")
    else:
        print("💡 Dry-run mode. Use --apply to persist changes.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
