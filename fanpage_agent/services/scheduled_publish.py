from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from fanpage_agent.adapters.sheet_store import LocalSheetStore

if TYPE_CHECKING:
    from fanpage_agent.models import BrandProfile, CaptionPackage
    from fanpage_agent.services.verifier import VerifierService


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

    def __init__(
        self,
        store: LocalSheetStore,
        brand_id: str,
        verifier: VerifierService | None = None,
        brand_profile: BrandProfile | None = None,
    ) -> None:
        self.store = store
        self.brand_id = brand_id
        self.verifier = verifier
        self.brand_profile = brand_profile

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

            # Optional tone verification — defense in depth
            if self.verifier and self.brand_profile:
                caption_ref = row.get("final_caption_ref", "")
                if caption_ref:
                    caption_path = Path(caption_ref)
                    if caption_path.exists():
                        try:
                            raw = json.loads(caption_path.read_text(encoding="utf-8"))
                            # Import only at runtime when needed
                            from fanpage_agent.models import CaptionPackage as _CaptionPackage
                            package = _CaptionPackage.model_validate(raw)
                            v_result = self.verifier.verify_caption_package(
                                self.brand_profile, package,
                            )
                            if not v_result.passed:
                                issues = "; ".join(v_result.issues[:3])
                                result.skipped.append({
                                    "calendar_id": calendar_id,
                                    "reason": f"Tone verification failed: {issues}",
                                })
                                continue
                        except Exception:
                            # Fail open — if file is unreadable, publish anyway
                            pass

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
