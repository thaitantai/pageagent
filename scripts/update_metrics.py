"""Update post metrics from Facebook Insights — runs daily via cron.

Fetches Facebook API reach/engagement for each published post in memory.db
and updates PerformanceMemory so pattern learning has real data.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Minimal import — no full agent bootstrap ──
from fanpage_agent.adapters.fb_adapter import FacebookAdapter
from fanpage_agent.memory.performance import PerformanceMemory


def main() -> str:
    db_path = ROOT / "data" / "agent" / "memory.db"
    memory = PerformanceMemory(db_path)

    # Get posts with zero reach still (un-tracked)
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT package_id, variant_id, permalink, published_at
           FROM published_posts
           WHERE reach = 0
           ORDER BY published_at ASC"""
    ).fetchall()
    conn.close()

    if not rows:
        return "✅ All posts already have metrics."

    try:
        fb = FacebookAdapter()
    except Exception as e:
        return f"⚠️ Cannot init FB adapter: {e}"

    updated = 0
    errors = 0
    for row in rows:
        package_id = row["package_id"]
        variant_id = row["variant_id"]
        permalink = row["permalink"]
        published_at = row["published_at"]

        # Skip posts published less than 30 minutes ago
        try:
            pub_time = datetime.fromisoformat(published_at)
        except (ValueError, TypeError):
            pub_time = datetime.now(timezone.utc)
        age_m = (datetime.now(timezone.utc) - pub_time).total_seconds() / 60
        if age_m < 30:
            continue

        # Extract fb_post_id from permalink: https://facebook.com/PAGEID_POSTID
        fb_post_id = permalink.split(".com/")[-1] if permalink else ""
        if not fb_post_id:
            errors += 1
            continue

        try:
            insights = fb.get_post_insights(fb_post_id)
            reach = int(insights.get("reach", 0))
            likes = int(insights.get("likes", 0))
            comments = int(insights.get("comments", 0))
            shares = int(insights.get("shares", 0))
            engagements = likes + comments + shares

            memory.record_metrics_update(
                package_id=package_id,
                variant_id=variant_id,
                reach=reach,
                engagements=engagements,
            )
            updated += 1
        except Exception:
            errors += 1

    summary = f"📊 Metrics update: {updated} updated, {errors} errors"
    if updated:
        summary += f" — patterns now have real engagement data"
    return summary


if __name__ == "__main__":
    result = main()
    print(result)
