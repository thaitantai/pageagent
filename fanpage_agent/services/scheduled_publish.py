from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from fanpage_agent.adapters.sheet_store import LocalSheetStore


@dataclass
class ScheduledPublishResult:
    """Summary of what was published during a scheduled-publish run."""

    published: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)

    @property
    def published_count(self) -> int:
        return len(self.published)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    def to_dict(self) -> dict[str, object]:
        return {
            "published_count": self.published_count,
            "skipped_count": self.skipped_count,
            "published": self.published,
            "skipped": self.skipped,
        }


class ScheduledPublishService:
    """Publishes approved items whose scheduled date has arrived."""

    def __init__(self, store: LocalSheetStore, brand_id: str) -> None:
        self.store = store
        self.brand_id = brand_id

    def publish_due(self, reference_date: str | None = None) -> ScheduledPublishResult:
        """Publish all approved/auto-approved items that are due on or before reference_date.

        Uses today's date if reference_date is not provided.
        """
        ref = reference_date or date.today().isoformat()
        rows = self.store._read_calendar_rows()
        result = ScheduledPublishResult()

        for row in rows:
            calendar_id = row.get("calendar_id", "")
            approval_status = row.get("approval_status", "pending")
            status = row.get("status", "planned")
            item_date = row.get("date", "")

            # Skip already published
            if status == "published":
                result.skipped.append({
                    "calendar_id": calendar_id,
                    "reason": "Already published",
                })
                continue

            # Skip not-yet-approved items
            if approval_status not in ("approved", "auto_approved"):
                result.skipped.append({
                    "calendar_id": calendar_id,
                    "reason": f"Not approved (status={approval_status})",
                })
                continue

            # Skip future items
            if item_date > ref:
                result.skipped.append({
                    "calendar_id": calendar_id,
                    "reason": f"Scheduled for {item_date}, reference is {ref}",
                })
                continue

            # Publish it
            published_at = item_date if item_date <= ref else ref
            self.store.publish_calendar_item(
                calendar_id=calendar_id,
                published_at=published_at,
                permalink=f"https://fanpage.auto/{calendar_id}",
                reach=0,
                engagement_rate=0.0,
            )
            result.published.append({
                "calendar_id": calendar_id,
                "topic": row.get("topic", ""),
                "published_at": published_at,
            })

        return result
