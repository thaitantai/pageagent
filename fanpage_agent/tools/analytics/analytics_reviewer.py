from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.config import Settings
from fanpage_agent.tools.analytics.analytics import AnalyticsTool

AnyStore = Any  # type alias for any store implementation


class AnalyticsReviewer:
    """Pull real metrics from Facebook Graph API, cross-reference with calendar,
    record to store, and produce an analytics review."""

    def __init__(
        self,
        settings: Settings,
        fb_client: FacebookClient | None = None,
        analytics_service: AnalyticsTool | None = None,
    ) -> None:
        self.settings = settings
        self.fb_client = fb_client or FacebookClient(settings)
        self.analytics = analytics_service or AnalyticsTool()

    def run_review(
        self,
        store: Any,
        days: int = 7,
        record: bool = False,
    ) -> dict[str, Any]:
        """Fetch FB posts, match to calendar, record metrics, return review.

        Args:
            store: Store backend (local or Google Sheets).
            days: Look back N days for FB posts.
            record: If True, write matched metrics to store.

        Returns:
            Review dict with matched, unmatched, recorded_count, summary, etc.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # 1. Fetch FB posts
        fb_posts = self.fb_client.get_page_posts(limit=50)
        recent_fb_posts = [
            p for p in fb_posts
            if _parse_fb_datetime(p.get("created_time", "")) >= cutoff
        ]

        # 2. Get published calendar items
        calendar_items = store.list_calendar_items(status="published")

        # Build calendar lookup by date → list of items
        cal_by_date: dict[str, list[dict[str, str]]] = {}
        for item in calendar_items:
            item_date = item.get("date", "")
            cal_by_date.setdefault(item_date, []).append(item)

        # 3. Match FB posts to calendar items
        matched: list[dict[str, Any]] = []
        unmatched: list[dict[str, Any]] = []
        recorded_count = 0

        for fb_post in recent_fb_posts:
            fb_date = fb_post.get("created_time", "")[:10]  # "2026-06-01"
            fb_message = (fb_post.get("message") or "").strip().lower()

            matched_cal_item = self._find_best_match(
                fb_date, fb_message, cal_by_date
            )

            if matched_cal_item:
                reach = fb_post.get("reach", 0)
                likes_converted = _parse_fb_likes(fb_post.get("likes", 0))
                comments_converted = _parse_fb_likes(fb_post.get("comments", 0))
                shares_converted = _parse_fb_shares(fb_post.get("shares", 0))
                engagements_count = likes_converted + comments_converted + shares_converted

                entry = {
                    "fb_post_id": fb_post.get("id", ""),
                    "calendar_id": matched_cal_item.get("calendar_id", ""),
                    "published_at": matched_cal_item.get("published_at", "") or matched_cal_item.get("date", ""),
                    "topic": matched_cal_item.get("topic", ""),
                    "pillar": matched_cal_item.get("pillar", ""),
                    "objective": matched_cal_item.get("objective", ""),
                    "reach": reach,
                    "engagements": engagements_count,
                    "leads": 0,
                    "permalink": fb_post.get("permalink_url", ""),
                }

                if record and matched_cal_item.get("calendar_id"):
                    store.record_post_metrics(
                        calendar_id=matched_cal_item["calendar_id"],
                        reach=reach,
                        engagements=engagements_count,
                        leads=0,
                        recorded_at=now.isoformat(),
                    )
                    recorded_count += 1
                    entry["recorded"] = True
                else:
                    entry["recorded"] = False

                matched.append(entry)
            else:
                likes_converted = _parse_fb_likes(fb_post.get("likes", 0))
                comments_converted = _parse_fb_likes(fb_post.get("comments", 0))
                shares_converted = _parse_fb_shares(fb_post.get("shares", 0))
                engagements_count = likes_converted + comments_converted + shares_converted

                unmatched.append({
                    "fb_post_id": fb_post.get("id", ""),
                    "message_preview": (fb_post.get("message") or "")[:120],
                    "created_time": fb_post.get("created_time", ""),
                    "permalink": fb_post.get("permalink_url", ""),
                    "reach": _parse_int(fb_post.get("reach", 0)),
                    "engagements": engagements_count,
                })

        # 4. Build summary metrics from ALL recorded + matched data
        all_metrics = list(store.read_post_metrics())
        report = self.analytics.build_weekly_report(all_metrics)
        report_payload = report.model_dump(mode="json")

        return {
            "review_period": {
                "days": days,
                "start": cutoff.isoformat(),
                "end": now.isoformat(),
            },
            "fetched": len(recent_fb_posts),
            "matched": len(matched),
            "unmatched": len(unmatched),
            "recorded": recorded_count,
            "matched_posts": matched,
            "unmatched_posts": unmatched,
            "store_metrics_count": len(all_metrics),
            "report": report_payload,
        }

    def _find_best_match(
        self,
        fb_date: str,
        fb_message: str,
        cal_by_date: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Find the best calendar match for an FB post.

        Priority:
        1. Exact date match + message contains topic
        2. Exact date match (any item)
        3. Date ±1 day + message contains topic
        """
        candidates = cal_by_date.get(fb_date, [])
        if not candidates:
            # Try ±1 day
            fb_dt = _parse_date_safe(fb_date)
            if fb_dt is not None:
                for delta in (-1, 1):
                    neighbor = (fb_dt + timedelta(days=delta)).strftime("%Y-%m-%d")
                    candidates = cal_by_date.get(neighbor, [])
                    if candidates:
                        break

        if not candidates:
            return None

        # Prefer topic match
        for c in candidates:
            topic = (c.get("topic") or "").strip().lower()
            hook = (c.get("hook") or "").strip().lower()
            if topic and topic in fb_message:
                return c
            if hook and hook in fb_message:
                return c

        # Fall back to first candidate
        return candidates[0]


def _parse_fb_datetime(raw: str) -> datetime:
    """Parse Facebook datetime string (ISO 8601) to datetime."""
    try:
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _parse_date_safe(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _parse_fb_likes(likes_field: object) -> int:
    """Parse likes/comments/shares from FB API response (dict or bare int)."""
    if isinstance(likes_field, dict):
        return _parse_int(likes_field.get("summary", {}).get("total_count", 0))
    return _parse_int(likes_field)


def _parse_fb_shares(shares_field: object) -> int:
    """Parse shares from FB API response (dict or bare int)."""
    if isinstance(shares_field, dict):
        return _parse_int(shares_field.get("count", 0))
    return _parse_int(shares_field)


def _parse_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
