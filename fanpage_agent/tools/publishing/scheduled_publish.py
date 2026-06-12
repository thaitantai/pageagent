from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from fanpage_agent.adapters.store_protocol import CalendarStore

if TYPE_CHECKING:
    from fanpage_agent.adapters.facebook_client import FacebookClient
    from fanpage_agent.models import BrandProfile
    from fanpage_agent.tools.content.image_gen import ImageTool
    from fanpage_agent.tools.content.verifier import VerifierTool

logger = logging.getLogger(__name__)


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


class ScheduledPublishTool:
    """Publishes approved items whose scheduled date has arrived."""

    def __init__(
        self,
        store: CalendarStore,
        brand_id: str,
        verifier: VerifierTool | None = None,
        brand_profile: BrandProfile | None = None,
        fb_client: FacebookClient | None = None,
        image_service: ImageTool | None = None,
    ) -> None:
        self.store = store
        self.brand_id = brand_id
        self.verifier = verifier
        self.brand_profile = brand_profile
        self.fb_client = fb_client
        self.image_service = image_service

    def publish_due(self, reference_date: str | None = None) -> ScheduledPublishResult:
        """Publish all approved/auto-approved items that are due on or before reference_date.

        Uses today's date if reference_date is not provided.
        """
        ref = reference_date or date.today().isoformat()
        # Protocol method — _read_calendar_rows() only existed on
        # LocalSheetStore and crashed the sqlite backend.
        rows = self.store.list_calendar_items()
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
                    "reason_code": "already_published",
                    "status": status,
                    "approval_status": approval_status,
                })
                continue

            # Skip not-yet-approved items
            if approval_status not in ("approved", "auto_approved"):
                result.skipped.append({
                    "calendar_id": calendar_id,
                    "reason": f"Not approved (status={approval_status})",
                    "reason_code": "approval_status_not_approved",
                    "status": status,
                    "approval_status": approval_status,
                    "next_step": "Approve the caption before scheduled-publish can publish it.",
                })
                continue

            if not row.get("final_caption_ref"):
                result.skipped.append({
                    "calendar_id": calendar_id,
                    "reason": "Missing final caption reference",
                    "reason_code": "missing_final_caption_ref",
                    "status": status,
                    "approval_status": approval_status,
                    "next_step": "Run approve-caption so the approved caption artifact is recorded.",
                })
                continue

            # Skip future items
            if item_date > ref:
                result.skipped.append({
                    "calendar_id": calendar_id,
                    "reason": f"Scheduled for {item_date}, reference is {ref}",
                    "reason_code": "scheduled_for_future",
                    "status": status,
                    "approval_status": approval_status,
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
                        except Exception as exc:
                            # Fail open — if file is unreadable, publish anyway
                            logger.warning(
                                "Tone verification skipped for %s (unreadable caption %s): %s",
                                calendar_id, caption_ref, exc,
                            )

            # Publish it ───────────────────────────────────────────────
            published_at = item_date if item_date <= ref else ref

            # Build message text from caption file if available
            message = row.get("topic", "")
            visual_brief = row.get("visual_brief", "")
            caption_file = row.get("final_caption_ref", "")
            if not caption_file:
                caption_file = row.get("draft_caption_ref", "")

            if caption_file:
                caption_path = Path(caption_file)
                if caption_path.exists():
                    try:
                        raw_text = caption_path.read_text(encoding="utf-8")
                        raw = json.loads(raw_text)
                        # Prefer the first variant's caption text
                        variants = raw.get("variants", [])
                        if variants:
                            parts = []
                            if variants[0].get("hook"):
                                parts.append(variants[0]["hook"])
                            if variants[0].get("caption"):
                                parts.append(variants[0]["caption"])
                            if variants[0].get("cta"):
                                parts.append(variants[0]["cta"])
                            message = "\n\n".join(parts)
                            # Use caption's visual_brief over row's if available
                            if variants[0].get("visual_brief"):
                                visual_brief = variants[0]["visual_brief"]
                    except Exception as exc:
                        # Fail open — fall back to topic as message
                        logger.warning(
                            "Caption file unreadable for %s (%s), falling back to topic: %s",
                            calendar_id, caption_file, exc,
                        )

            # Generate image from visual_brief if service is available
            image_path: str | None = None
            if self.image_service and visual_brief:
                try:
                    image_path = self.image_service.generate(visual_brief)
                    logger.info(
                        "Generated image for %s: %s", calendar_id, image_path
                    )
                except Exception as exc:
                    logger.error(
                        "Image generation failed for %s: %s", calendar_id, exc
                    )
                    # Fail open — post without image

            # Post to Facebook if client is configured
            post_id = ""
            post_permalink = f"https://fanpage.auto/{calendar_id}"
            if self.fb_client:
                try:
                    if image_path:
                        fb_resp = self.fb_client.post_photo(
                            image_path=image_path, message=message
                        )
                        # Graph API /photos returns post_id in the response
                        post_id = fb_resp.get("post_id", fb_resp.get("id", ""))
                    else:
                        fb_resp = self.fb_client.post_to_page(message=message)
                        post_id = fb_resp.get("id", "")

                    if post_id:
                        post_number = post_id.split("_", 1)[-1] if "_" in post_id else post_id
                        post_permalink = f"https://facebook.com/{self.fb_client.page_id}/posts/{post_number}"
                        logger.info("Published to Facebook: post_id=%s url=%s", post_id, post_permalink)
                    else:
                        logger.warning("Facebook post succeeded but no post_id returned")
                except Exception as exc:
                    logger.error("Facebook publish failed for %s: %s", calendar_id, exc)
                    # Fail open — still mark as published locally
                    result.published.append({
                        "calendar_id": calendar_id,
                        "topic": row.get("topic", ""),
                        "published_at": published_at,
                        "error": str(exc),
                    })
                    continue

            self.store.publish_calendar_item(
                calendar_id=calendar_id,
                published_at=published_at,
                permalink=post_permalink,
                reach=0,
                engagement_rate=0.0,
            )

            # Auto-track hashtags from the published caption
            import re as _re
            found_tags = _re.findall(r"#\w+", message)
            if found_tags:
                try:
                    self.store.record_hashtag_usage(
                        calendar_id=calendar_id,
                        brand_id=self.brand_id,
                        hashtags=found_tags,
                        topic=row.get("topic", ""),
                        recorded_at=published_at,
                    )
                except Exception:
                    logger.warning("Failed to record hashtags for %s", calendar_id, exc_info=True)
            result.published.append({
                "calendar_id": calendar_id,
                "topic": row.get("topic", ""),
                "published_at": published_at,
                "post_id": post_id,
                "permalink": post_permalink,
            })

        return result
