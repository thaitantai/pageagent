"""Metrics Auto-Fetch Service (P4).

Automatically fetches Facebook insights for published posts that are
missing metrics data. Runs as a standalone scan or as a cron job lane.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.config import Settings


class MetricsAutoFetchTool:
    """Scan published calendar items, fetch missing metrics from FB API.

    Strategy:
      1. List published calendar items.
      2. Filter to those missing metrics (reach is 0, None, or empty).
      3. If item has a permalink, extract FB post_id and call get_post_insights.
      4. Record metrics back to store.
    """

    def __init__(
        self,
        settings: Settings,
        fb_client: FacebookClient | None = None,
    ) -> None:
        self.settings = settings
        self.fb_client = fb_client or FacebookClient(settings)

    def auto_fetch(self, store: Any, days_back: int = 30) -> dict[str, Any]:
        """Fetch missing metrics for published items.

        Args:
            store: Store backend (LocalSheetStore or GoogleSheetsStore).
            days_back: Only process items published within this many days.

        Returns:
            Dict with scan results.
        """
        now = datetime.now(timezone.utc)

        # 1. Get published items
        calendar_items = store.list_calendar_items(status="published")
        if not calendar_items:
            return {
                "scanned": 0,
                "missing_metrics": 0,
                "fetched": 0,
                "recorded": 0,
                "errors": 0,
                "items": [],
                "message": "No published items found.",
            }

        # 2. Filter to items missing metrics + within window
        missing_items = []
        for item in calendar_items:
            published_at = item.get("published_at", "") or item.get("date", "")
            if published_at:
                try:
                    pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    if (now - pub_dt).days > days_back:
                        continue
                except (ValueError, TypeError):
                    pass  # include if we can't parse

            reach_raw = item.get("reach")
            has_metrics = reach_raw is not None and str(reach_raw).strip() not in ("", "0", "0.0")
            if not has_metrics:
                missing_items.append(item)

        if not missing_items:
            return {
                "scanned": len(calendar_items),
                "missing_metrics": 0,
                "fetched": 0,
                "recorded": 0,
                "errors": 0,
                "items": [],
                "message": "All published items already have metrics.",
            }

        # 3. Fetch metrics for each
        results: list[dict[str, Any]] = []
        fetched = 0
        recorded = 0
        errors = 0

        for item in missing_items:
            permalink = item.get("permalink", "") or ""
            result = {
                "calendar_id": item.get("calendar_id", ""),
                "topic": item.get("topic", ""),
                "date": item.get("date", ""),
                "permalink": permalink,
                "status": "skipped",
                "detail": "",
            }

            post_id = self._extract_post_id(permalink)
            if not post_id:
                result["status"] = "skipped"
                result["detail"] = "No permalink or post_id"
                results.append(result)
                continue

            try:
                insights = self.fb_client.get_post_insights(post_id)
            except Exception as exc:
                result["status"] = "error"
                result["detail"] = str(exc)[:200]
                errors += 1
                results.append(result)
                continue

            reach = self._safe_int(insights.get("reach", 0))
            likes = self._safe_int(insights.get("likes", 0))
            comments = self._safe_int(insights.get("comments", 0))
            shares = self._safe_int(insights.get("shares", 0))
            engagements = likes + comments + shares

            try:
                store.record_post_metrics(
                    calendar_id=item.get("calendar_id", ""),
                    reach=reach,
                    engagements=engagements,
                    leads=0,
                    recorded_at=now.isoformat(),
                )
                result["status"] = "recorded"
                result["detail"] = f"reach={reach}, engagements={engagements}"
                fetched += 1
                recorded += 1
            except Exception as exc:
                result["status"] = "error"
                result["detail"] = f"store error: {exc}"[:200]
                errors += 1

            results.append(result)

        return {
            "scanned": len(calendar_items),
            "missing_metrics": len(missing_items),
            "fetched": fetched,
            "recorded": recorded,
            "errors": errors,
            "items": results,
            "message": f"Fetched {fetched} / {len(missing_items)} missing metrics (errors: {errors}).",
        }

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_post_id(permalink: str) -> str:
        """Extract Facebook post ID from permalink URL.

        Handles:
          - https://facebook.com/pgid/posts/postnum
          - https://www.facebook.com/permalink.php?story_fbid=...
          - bare post ID
        """
        if not permalink:
            return ""

        # Bare ID pattern (numeric)
        if permalink.isdigit():
            return permalink

        # /posts/123456789 pattern
        m = re.search(r"/posts/(\d+)", permalink)
        if m:
            return m.group(1)

        # permalink.php?story_fbid=123456789
        m = re.search(r"story_fbid=(\d+)", permalink)
        if m:
            return m.group(1)

        # /pgid/posts/postnum pattern
        parts = permalink.rstrip("/").split("/")
        if len(parts) >= 3 and parts[-2] == "posts":
            return parts[-1]

        return ""

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0
