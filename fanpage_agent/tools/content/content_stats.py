"""Content Performance Stats — aggregate published post metrics by pillar.

Provides compact summaries the agent uses to decide which content pillars
to prioritise and which formats work best.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


def compute_content_stats(store: Any, days_back: int = 14) -> dict[str, Any]:
    """Compute content performance statistics from published items.

    Args:
        store: Store backend (LocalSheetStore or GoogleSheetsStore).
        days_back: Only include items published within this many days.

    Returns:
        Compact stats dict with pillar breakdown and top-performers.
    """
    items = store.list_calendar_items() or []
    now = datetime.now(timezone.utc)

    # Filter published + within window
    published: list[dict[str, Any]] = []
    for item in items:
        if item.get("status") != "published":
            continue
        pub_raw = item.get("published_at", "") or item.get("date", "")
        if pub_raw:
            try:
                pub_dt = _parse_dt(pub_raw)
                if (now - pub_dt).days > days_back:
                    continue
            except (ValueError, TypeError):
                pass  # include if we can't parse
        published.append(item)

    if not published:
        return {
            "total_published": 0,
            "days_back": days_back,
            "by_pillar": {},
            "top_posts": [],
            "summary": "No published items in window.",
        }

    # Aggregate by pillar
    pillar_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total_reach": 0, "total_engagements": 0, "posts": []}
    )
    for item in published:
        pillar = _normalise_pillar(item.get("pillar", "other"))
        reach = _safe_int(item.get("reach", 0))
        engagements = _safe_int(item.get("engagements", 0))

        pillar_stats[pillar]["count"] += 1
        pillar_stats[pillar]["total_reach"] += reach
        pillar_stats[pillar]["total_engagements"] += engagements
        pillar_stats[pillar]["posts"].append(
            {
                "id": item.get("calendar_id", ""),
                "topic": item.get("topic", ""),
                "date": item.get("date", ""),
                "reach": reach,
                "engagements": engagements,
            }
        )

    # Compute averages and sort
    by_pillar = {}
    for pillar, data in sorted(pillar_stats.items()):
        c = data["count"]
        by_pillar[pillar] = {
            "posts": c,
            "avg_reach": round(data["total_reach"] / c) if c else 0,
            "avg_engagement": round(data["total_engagements"] / c) if c else 0,
            "total_reach": data["total_reach"],
            "total_engagements": data["total_engagements"],
        }

    # Top 5 posts by engagement
    all_with_stats = []
    for pillar, data in pillar_stats.items():
        for p in data["posts"]:
            eng = p["engagements"]
            all_with_stats.append({**p, "pillar": pillar, "score": eng})
    all_with_stats.sort(key=lambda x: x["score"], reverse=True)

    return {
        "total_published": len(published),
        "days_back": days_back,
        "by_pillar": by_pillar,
        "top_posts": [
            {
                "topic": p["topic"][:60],
                "pillar": p["pillar"],
                "reach": p["reach"],
                "engagements": p["engagements"],
                "date": p["date"],
            }
            for p in all_with_stats[:5]
        ],
        "summary": _build_summary(by_pillar, len(published)),
    }


def _build_summary(by_pillar: dict[str, dict], total: int) -> str:
    if not by_pillar:
        return "No data."
    parts = []
    sorted_pillars = sorted(by_pillar.items(), key=lambda x: x[1]["avg_engagement"], reverse=True)
    for pillar, data in sorted_pillars:
        icon = _pillar_icon(pillar)
        parts.append(
            f"{icon}{pillar}: {data['posts']} posts, ø{data['avg_reach']} reach, ø{data['avg_engagement']} eng"
        )
    best = sorted_pillars[0]
    return (
        f"{total} posts | Best: {_pillar_icon(best[0])}{best[0]} (ø{best[1]['avg_engagement']} eng)"
    )


def _normalise_pillar(raw: str) -> str:
    raw = raw.lower().strip()
    # Map similar pillar names
    mapping = {
        "skincare routine": "skincare",
        "routine": "skincare",
        "product": "products",
        "products": "products",
        "review": "products",
        "ingredient": "ingredients",
        "ingredients": "ingredients",
        "lifestyle": "lifestyle",
        "tips": "tips",
        "myth": "mythbusting",
        "mythbusting": "mythbusting",
        "education": "education",
        "trend": "trends",
        "trends": "trends",
    }
    return mapping.get(raw, raw)


def _pillar_icon(pillar: str) -> str:
    icons = {
        "skincare": "🧴",
        "products": "🛒",
        "ingredients": "🔬",
        "lifestyle": "☀️",
        "tips": "💡",
        "mythbusting": "⚡",
        "education": "📖",
        "trends": "🔥",
    }
    return icons.get(pillar, "📌")


def _parse_dt(raw: str) -> datetime:
    raw_clean = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw_clean)
    except (ValueError, TypeError):
        pass
    # Date-only (YYYY-MM-DD) → end of day UTC
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return datetime.fromisoformat(m.group(1) + "T23:59:59+00:00")
    raise ValueError(f"Cannot parse datetime: {raw}")


def _safe_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
