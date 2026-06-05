#!/usr/bin/env python3
"""
Weekly Analyst Report — reads memory.db + state.json + container status.
Outputs a Telegram-formatted summary. Designed for no_agent=True cron job.
"""

import json
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT / "data" / "agent" / "memory.db"
STATE_PATH = PROJECT / "data" / "agent" / "state.json"


def read_db() -> dict:
    """Return post stats from memory.db."""
    if not DB_PATH.exists():
        return {"total_posts": 0, "reach": 0, "engagements": 0, "posts": []}

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]

    stats = {"total_posts": 0, "reach": 0, "engagements": 0, "posts": []}

    if "published_posts" in tables:
        cur.execute("""
            SELECT topic, pillar, reach, engagements, engagement_rate,
                   published_at, permalink
            FROM published_posts
            ORDER BY published_at DESC
        """)
        rows = cur.fetchall()
        stats["total_posts"] = len(rows)
        for r in rows:
            stats["reach"] += (r[2] or 0)
            stats["engagements"] += (r[3] or 0)
            stats["posts"].append({
                "topic": r[0],
                "pillar": r[1],
                "reach": r[2] or 0,
                "engagements": r[3] or 0,
                "rate": r[4] or 0.0,
                "published_at": r[5],
                "permalink": r[6],
            })

    if "performance_patterns" in tables:
        cur.execute("SELECT pattern_type, value, sample_count FROM performance_patterns")
        stats["patterns"] = [{"type": r[0], "value": r[1], "count": r[2]} for r in cur.fetchall()]

    conn.close()
    return stats


def read_state() -> dict:
    """Read state.json."""
    if not STATE_PATH.exists():
        return {"tick_count": 0, "last_tick": "N/A"}
    try:
        data = json.loads(STATE_PATH.read_text())
        return {
            "tick_count": data.get("tick", 0),
            "last_tick": data.get("state", {}).get("system", {}).get("last_tick", "N/A"),
        }
    except (json.JSONDecodeError, OSError):
        return {"tick_count": 0, "last_tick": "N/A"}


def container_status() -> str:
    """Returns container up-time or error."""
    try:
        out = subprocess.run(
            ["docker", "ps", "--filter", "name=fanpage-agent",
             "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "not running"
    except Exception as e:
        return f"error: {e}"


def format_report(stats: dict, state: dict, container: str) -> str:
    """Produce a Telegram-friendly weekly summary."""
    posts = stats.get("posts", [])
    total = stats["total_posts"]
    reach = stats["reach"]
    eng = stats["engagements"]
    avg_rate = round(sum(p["rate"] for p in posts) / max(total, 1), 2) if total else 0

    # Top post
    top = max(posts, key=lambda p: p["reach"]) if posts else None

    lines = [
        "📊 **Weekly Report**",
        f"▸ container: {container}",
        f"▸ ticks: {state.get('tick_count', '?')}",
        f"",
        f"📝 **Posts**: {total}",
        f"👁 **Reach**: {reach:,}",
        f"💬 **Engagements**: {eng:,}",
        f"📈 **Avg engagement rate**: {avg_rate}%",
    ]

    if top:
        lines += [
            "",
            "🏆 **Top post this week**:",
            f"   {top['topic'][:60]}",
            f"   reach: {top['reach']:,} · eng: {top['engagements']:,}",
        ]
        if top.get("permalink"):
            lines.append(f"   🔗 {top['permalink']}")

    # Patterns
    patterns = stats.get("patterns", [])
    if patterns:
        lines.append("")
        lines.append("📌 **Learning patterns**:")
        for p in patterns:
            lines.append(f"   • {p['type']}: _{p['value'][:40]}_ (x{p['count']})")

    return "\n".join(lines)


def main():
    stats = read_db()
    state = read_state()
    container = container_status()

    # If no posts, the report is still valid (new agent)
    print(format_report(stats, state, container))


if __name__ == "__main__":
    main()
