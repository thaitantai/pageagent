"""PublisherAgent — publishes content to Facebook and tracks performance.

Uses FacebookAdapter to post real content and records metrics
for the PerformanceMemory system.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fanpage_agent_v2.adapters.fb_adapter import FacebookAdapter
from fanpage_agent_v2.core.agent import BaseAgent
from fanpage_agent_v2.core.types import (
    ActionPriority,
    AgentRole,
    AgentResult,
    AgentTask,
    ContentPackage,
    ContentVariant,
)


class PublisherAgent(BaseAgent):
    """Publisher — responsible for publishing approved content to Facebook.

    Handles:
    - Publishing text posts, photos, carousels
    - Tracking post IDs and permalinks
    - Recording performance metrics after publishing
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        fb: FacebookAdapter | None = None,
        performance_memory=None,
    ) -> None:
        super().__init__(config)
        self._fb: FacebookAdapter | None = None
        self._fb_error: str | None = None
        try:
            self._fb = fb or FacebookAdapter()
        except Exception as e:
            self._fb_error = str(e)
        self._memory = performance_memory

    @property
    def role(self) -> AgentRole:
        return AgentRole.PUBLISHER

    @property
    def capabilities(self) -> list[str]:
        return [
            "publish_post",
            "publish_package",
            "publish_due",
            "track_performance",
            "delete_post",
            "fetch_metrics",
        ]

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params

        # Check FB availability for publish/track/delete actions
        if action in ("publish_post", "publish_package", "publish_due",
                       "track_performance", "delete_post", "fetch_metrics"):
            if self._fb is None:
                return AgentResult(
                    task_id=task.id, success=False,
                    error=f"FacebookAdapter unavailable: {self._fb_error or 'unknown'}",
                )

        if action == "publish_post":
            return self._publish_post(
                message=params.get("message", ""),
                image_path=params.get("image_path"),
            )
        elif action == "publish_package":
            return self._publish_package(params.get("package"))
        elif action == "publish_due":
            return self._publish_post(
                message=params.get("message", "Bài viết mới từ Fanpage Agent 🎉"),
                image_path=params.get("image_path"),
            )
        elif action == "track_performance":
            return self._track_performance(
                fb_post_id=params.get("fb_post_id", ""),
                variant_id=params.get("variant_id", ""),
            )
        elif action == "delete_post":
            return self._delete_post(params.get("fb_post_id", ""))
        elif action == "fetch_metrics":
            return self._fetch_metrics(limit=params.get("limit", 10))
        return AgentResult(
            task_id=task.id, success=False, error=f"Unknown action: {action}"
        )

    def _publish_post(
        self, message: str, image_path: str | None = None,
        record_memory: bool = True,
    ) -> AgentResult:
        """Publish a single post — text or photo.

        Args:
            message: Post caption text.
            image_path: Optional local image file path.
            record_memory: If True, record post metadata in PerformanceMemory.
        """
        try:
            if image_path:
                result = self._fb.publish_photo(
                    image_path=image_path, message=message
                )
            else:
                result = self._fb.publish_post(message=message)

            fb_id = result.get("fb_post_id", "")
            permalink = result.get("permalink", "")
            success = bool(fb_id)

            # Record in performance memory when publish succeeds
            if success and self._memory and record_memory:
                self._record_simple_post(
                    message=message,
                    fb_id=fb_id,
                    permalink=permalink,
                    image_path=image_path,
                )

            return AgentResult(
                task_id=f"pub-{fb_id or 'failed'}",
                success=success,
                data={
                    "fb_post_id": fb_id,
                    "permalink": permalink,
                    "published_at": datetime.now(timezone.utc).isoformat(),
                    "image": bool(image_path),
                },
                error=None if success else f"Empty FB response: {result}",
            )
        except Exception as e:
            return AgentResult(
                task_id="pub-failed",
                success=False,
                error=f"Publish failed: {e}",
            )

    def _record_simple_post(
        self,
        message: str,
        fb_id: str,
        permalink: str,
        image_path: str | None = None,
    ) -> None:
        """Record a simple (non-package) post in PerformanceMemory."""
        from fanpage_agent_v2.core.types import ContentPackage, ContentVariant

        variant = ContentVariant(
            variant_id=fb_id,
            topic=message[:60] if message else "",
            pillar="auto_generated",
            caption=message,
            hook=message[:80] if message else "",
            cta="",
            format="image" if image_path else "text",
            tone_tags=["informal"],
        )
        package = ContentPackage(
            package_id=f"auto-{fb_id}",
            brand_id=self._fb._page_id,
            scheduled_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            scheduled_time=datetime.now(timezone.utc).strftime("%H:%M"),
            variants=[variant],
        )
        self._memory.record_publish(
            package=package,
            variant_id=fb_id,
            reach=0,
            engagements=0,
            permalink=permalink,
        )

    def _publish_package(self, package: ContentPackage | dict | None) -> AgentResult:
        """Publish the best variant from a content package."""
        if package is None:
            return AgentResult(
                task_id="pub-pkg", success=False, error="No package provided"
            )
        if isinstance(package, dict):
            # Reconstruct from dict if needed
            package = ContentPackage(**package)

        variant = package.best_variant()
        if variant is None:
            return AgentResult(
                task_id=f"pub-{package.package_id}",
                success=False,
                error=f"No variants in package {package.package_id}",
            )

        # Build the final caption
        caption_parts = [f"💡 {variant.hook}" if variant.hook else ""]
        if variant.caption:
            caption_parts.append(variant.caption)
        if variant.cta:
            caption_parts.append(variant.cta)
        if variant.hashtags:
            caption_parts.append(" ".join(
                f"#{t.lstrip('#')}" for t in variant.hashtags
            ))

        message = "\n\n".join(p for p in caption_parts if p)

        # Publish
        fb_result = self._publish_post(
            message=message,
            image_path=variant.image_path,
            record_memory=False,  # package handles its own recording below
        )

        if not fb_result.success:
            return fb_result

        # Mark variant as published
        variant.published = True
        variant.permalink = fb_result.data.get("permalink", "")
        package.winning_variant = variant
        package.status = "published"

        # Record in performance memory
        if self._memory and fb_result.success:
            self._memory.record(
                content_type=variant.pillar,
                variant_id=variant.variant_id,
                hook=variant.hook,
                format=variant.format,
                tone_tags=",".join(variant.tone_tags),
                fb_post_id=fb_result.data.get("fb_post_id", ""),
                permalink=fb_result.data.get("permalink", ""),
                published_at=fb_result.data.get("published_at", ""),
            )

        return AgentResult(
            task_id=f"pub-{package.package_id}",
            success=True,
            data={
                "package_id": package.package_id,
                "variant_id": variant.variant_id,
                "fb_post_id": fb_result.data.get("fb_post_id"),
                "permalink": fb_result.data.get("permalink"),
                "status": "published",
            },
        )

    def _track_performance(
        self, fb_post_id: str, variant_id: str
    ) -> AgentResult:
        """Fetch and record post performance metrics from Facebook."""
        if not fb_post_id:
            return AgentResult(
                task_id="track", success=False, error="No fb_post_id provided"
            )

        try:
            insights = self._fb.get_post_insights(fb_post_id)
            reach = insights.get("reach", 0)
            likes = insights.get("likes", 0)
            comments = insights.get("comments", 0)
            shares = insights.get("shares", 0)
            engagements = likes + comments + shares

            # Update performance memory
            if self._memory and variant_id:
                self._memory.update_performance(
                    variant_id=variant_id,
                    reach=reach,
                    engagements=engagements,
                )

            return AgentResult(
                task_id=f"track-{fb_post_id[:12]}",
                success=True,
                data={
                    "fb_post_id": fb_post_id,
                    "variant_id": variant_id,
                    "reach": reach,
                    "likes": likes,
                    "comments": comments,
                    "shares": shares,
                    "total_engagements": engagements,
                    "tracked_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as e:
            return AgentResult(
                task_id=f"track-{fb_post_id[:12]}",
                success=False,
                error=f"Failed to track {fb_post_id}: {e}",
            )

    def _delete_post(self, fb_post_id: str) -> AgentResult:
        """Delete a published post."""
        try:
            self._fb.delete_post(fb_post_id)
            return AgentResult(
                task_id=f"del-{fb_post_id[:12]}",
                success=True,
                data={"fb_post_id": fb_post_id, "deleted": True},
            )
        except Exception as e:
            return AgentResult(
                task_id=f"del-{fb_post_id[:12]}",
                success=False,
                error=f"Delete failed: {e}",
            )

    def _fetch_metrics(self, limit: int = 10) -> AgentResult:
        """Fetch recent page posts with engagement data."""
        try:
            posts = self._fb.get_recent_posts(limit=limit)
            return AgentResult(
                task_id="metrics",
                success=True,
                data={
                    "posts": posts,
                    "count": len(posts),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as e:
            return AgentResult(
                task_id="metrics",
                success=False,
                error=f"Fetch metrics failed: {e}",
            )
