"""Content Queue Tool — manages the draft → queued → approved → published pipeline.

Integrates with UnifiedStore (SQLite) and FacebookClient for direct publishing.
Provides batch operations (approve/reject/publish by pillar/topic/date range).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fanpage_agent.adapters.facebook_client import FacebookClient
    from fanpage_agent.adapters.sqlite_store import UnifiedStore

logger = logging.getLogger(__name__)


@dataclass
class ContentQueueResult:
    """Result of a queue publish operation."""

    published: list[dict[str, str]] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)

    @property
    def published_count(self) -> int:
        return len(self.published)

    @property
    def failed_count(self) -> int:
        return len(self.failed)

    @property
    def total(self) -> int:
        return self.published_count + self.failed_count + len(self.skipped)

    def to_dict(self) -> dict[str, object]:
        return {
            "published_count": self.published_count,
            "failed_count": self.failed_count,
            "skipped_count": len(self.skipped),
            "published": self.published,
            "failed": self.failed,
            "skipped": self.skipped,
        }


class ContentQueueTool:
    """Manages the content queue: scheduling, approval, batch publish.

    Flow:
        1. Enqueue captions (via calendar_id) → status='queued'
        2. Approve (single or batch) → status='approved'
        3. Publish to Facebook → status='published' or 'failed'

    Dry-run mode: set dry_run=True to preview without actual FB API calls.
    """

    def __init__(
        self,
        store: UnifiedStore,
        fb_client: FacebookClient | None = None,
        dry_run: bool = False,
    ) -> None:
        self.store = store
        self.fb_client = fb_client
        self.dry_run = dry_run

    # ── Queue lifecycle ──────────────────────────────────────────

    def enqueue_from_calendar(
        self,
        calendar_id: str,
        batch_id: str = "",
        scheduled_for: str = "",
    ) -> dict[str, Any]:
        """Enqueue a calendar item (with caption) into the content queue.

        Reads the calendar item for metadata; requires either draft_caption_ref
        or final_caption_ref to exist.
        """
        items = self.store.list_calendar_items(limit=1000)
        row = None
        for item in items:
            if item.get("calendar_id") == calendar_id:
                row = item
                break
        if not row:
            return {"error": f"Calendar item {calendar_id} not found", "enqueued": False}

        caption_ref = row.get("final_caption_ref") or row.get("draft_caption_ref", "")
        caption_preview = ""
        if caption_ref:
            try:
                with open(caption_ref, encoding="utf-8") as f:
                    data = json.load(f)
                # Extract first caption text for preview
                variants = data.get("variants", []) or data.get("caption_ideas", [])
                if variants:
                    caption_preview = variants[0].get("caption_text", "") or variants[0].get("caption", "")
                    caption_preview = caption_preview[:200]
            except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Caption preview unavailable for %s (ref=%s): %s",
                    calendar_id, caption_ref, exc,
                )

        result = self.store.enqueue_calendar_item(
            calendar_id=calendar_id,
            brand_id=row.get("brand_id", ""),
            caption_ref=caption_ref,
            caption_preview=caption_preview or row.get("topic", ""),
            topic=row.get("topic", ""),
            pillar=row.get("pillar", ""),
            objective=row.get("objective", ""),
            scheduled_for=scheduled_for,
            batch_id=batch_id,
        )
        result["enqueued"] = True
        return result

    def show_queue(
        self,
        status: str | None = None,
        topic: str | None = None,
        pillar: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Show queue items with summary."""
        items = self.store.list_content_queue(
            status=status,
            topic=topic,
            pillar=pillar,
            limit=limit,
        )
        stats = self.store.get_queue_stats()
        return {
            "items": items,
            "count": len(items),
            "stats": stats,
        }

    def approve_item(
        self,
        calendar_id: str,
        approved_by: str = "admin",
    ) -> dict[str, Any]:
        """Approve a single queued item."""
        result = self.store.approve_queue_item(
            calendar_id=calendar_id, approved_by=approved_by,
        )
        if not result or result.get("queue_status") != "approved":
            return {"error": f"Could not approve {calendar_id}", "approved": False}
        # Also update calendar table to keep in sync
        now = datetime.now(timezone.utc).isoformat()
        self.store.approve_calendar_item(
            calendar_id=calendar_id,
            approved_by=approved_by,
            final_caption_ref=result.get("caption_ref", ""),
            approved_at=now,
        )
        return {"approved": True, "calendar_id": calendar_id, "item": result}

    def reject_item(
        self,
        calendar_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Reject a single queued item."""
        result = self.store.reject_queue_item(
            calendar_id=calendar_id, reason=reason,
        )
        if not result or result.get("queue_status") != "rejected":
            return {"error": f"Could not reject {calendar_id}", "rejected": False}
        return {"rejected": True, "calendar_id": calendar_id, "item": result}

    def batch_approve(
        self,
        pillar: str | None = None,
        topic: str | None = None,
        brand_id: str | None = None,
        limit: int | None = None,
        approved_by: str = "admin",
    ) -> dict[str, Any]:
        """Batch-approve queued items matching filters."""
        return self.store.batch_approve_queue(
            status="queued",
            brand_id=brand_id,
            pillar=pillar,
            topic=topic,
            approved_by=approved_by,
            limit=limit,
        )

    def batch_reject(
        self,
        pillar: str | None = None,
        topic: str | None = None,
        brand_id: str | None = None,
        reason: str = "",
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Batch-reject queued items matching filters."""
        conditions = ["queue_status = 'queued'"]
        params: list[Any] = []
        if brand_id:
            conditions.append("brand_id = ?")
            params.append(brand_id)
        if pillar:
            conditions.append("pillar = ?")
            params.append(pillar)
        if topic:
            conditions.append("topic = ?")
            params.append(topic)
        now = datetime.now(timezone.utc).isoformat()
        where = " AND ".join(conditions)
        limit_clause = f" LIMIT {limit}" if limit else ""

        with self.store._conn() as conn:
            matching = conn.execute(
                f"SELECT calendar_id FROM content_queue WHERE {where}{limit_clause}", params
            ).fetchall()
            ids = [r["calendar_id"] for r in matching]
            if not ids:
                return {"rejected_count": 0, "calendars": []}
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"""UPDATE content_queue SET queue_status='rejected',
                   rejected_reason=?, rejected_at=?, updated_at=?
                   WHERE calendar_id IN ({placeholders})""",
                [reason, now, now] + ids,
            )
        return {"rejected_count": len(ids), "calendars": ids}

    def publish_to_facebook(
        self,
        calendar_id: str,
        dry_run: bool | None = None,
    ) -> dict[str, Any]:
        """Publish a single approved queue item to Facebook.

        If dry_run=True (or self.dry_run), simulates the publish without
        calling the FB API.
        """
        is_dry_run = dry_run if dry_run is not None else self.dry_run
        items = self.store.list_content_queue(status="approved")
        row = None
        for item in items:
            if item.get("calendar_id") == calendar_id:
                row = item
                break
        if not row:
            return {"error": f"Item {calendar_id} not found or not approved", "published": False}

        # Read caption text from caption_ref
        caption_text = row.get("caption_preview", row.get("topic", ""))
        caption_ref_path = row.get("caption_ref", "")
        if caption_ref_path:
            try:
                with open(caption_ref_path, encoding="utf-8") as f:
                    data = json.load(f)
                variants = data.get("variants", []) or data.get("caption_ideas", [])
                if variants:
                    caption_text = variants[0].get("caption_text", "") or variants[0].get("caption", "")
            except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load caption ref %s: %s", caption_ref_path, exc)

        if is_dry_run or self.fb_client is None:
            # Simulate publish
            result = self.store.mark_queue_item_published(
                calendar_id=calendar_id,
                fb_post_id="dry_run_no_fb_client" if self.fb_client is None else "dry_run",
                fb_error="",
            )
            result["dry_run"] = True
            result["preview_caption"] = caption_text[:200]
            result["published"] = True
            return result

        # Real FB publish
        try:
            fb_result = self.fb_client.post_to_page(message=caption_text)
            fb_post_id = fb_result.get("id", "")
            result = self.store.mark_queue_item_published(
                calendar_id=calendar_id,
                fb_post_id=fb_post_id,
                fb_error="",
            )
            # Also update calendar table
            now = datetime.now(timezone.utc).isoformat()
            permalink = f"https://facebook.com/{self.fb_client.page_id}/posts/{fb_post_id.split('_')[-1]}"
            self.store.publish_calendar_item(
                calendar_id=calendar_id,
                published_at=now,
                permalink=permalink,
            )
            result["fb_post_id"] = fb_post_id
            result["permalink"] = permalink
            result["published"] = True
        except Exception as exc:
            err_msg = str(exc)[:500]
            result = self.store.mark_queue_item_published(
                calendar_id=calendar_id,
                fb_post_id="",
                fb_error=err_msg,
            )
            result["published"] = False
            result["error"] = err_msg
        return result

    def batch_publish_to_facebook(
        self,
        brand_id: str | None = None,
        pillar: str | None = None,
        topic: str | None = None,
        limit: int | None = None,
        dry_run: bool | None = None,
    ) -> ContentQueueResult:
        """Publish all approved queue items to Facebook."""
        items = self.store.batch_publish_queue(
            brand_id=brand_id, pillar=pillar, topic=topic, limit=limit,
        )
        result = ContentQueueResult()
        for item in items:
            cal_id = item.get("calendar_id", "")
            if not cal_id:
                continue
            pub_result = self.publish_to_facebook(
                calendar_id=cal_id, dry_run=dry_run,
            )
            if pub_result.get("published"):
                result.published.append({
                    "calendar_id": cal_id,
                    "topic": item.get("topic", ""),
                    "fb_post_id": pub_result.get("fb_post_id", ""),
                    "permalink": pub_result.get("permalink", ""),
                })
            elif pub_result.get("error"):
                result.failed.append({
                    "calendar_id": cal_id,
                    "topic": item.get("topic", ""),
                    "error": pub_result["error"],
                })
            else:
                result.skipped.append({
                    "calendar_id": cal_id,
                    "topic": item.get("topic", ""),
                    "reason": "unexpected_state",
                })
        return result
