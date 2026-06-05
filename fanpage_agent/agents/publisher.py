"""PublisherAgent — publishes content to Facebook and tracks performance.

Uses FacebookAdapter to post real content and records metrics
for the PerformanceMemory system.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fanpage_agent.adapters.fb_adapter import FacebookAdapter
from fanpage_agent.core.agent import BaseAgent
from fanpage_agent.core.types import (
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
        default_page_id: str | None = None,
    ) -> None:
        super().__init__(config)
        self._fb: FacebookAdapter | None = None
        self._fb_error: str | None = None
        try:
            self._fb = fb or FacebookAdapter()
        except Exception as e:
            self._fb_error = str(e)
        self._memory = performance_memory
        self._default_page_id = default_page_id

    def _resolve_page_id(self, params: dict) -> str | None:
        """Return page_id from params, falling back to instance default."""
        return params.get("page_id") or self._default_page_id

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
            "refresh_metrics",
        ]

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params

        # Check FB availability for publish/track/delete actions
        if action in ("publish_post", "publish_package", "publish_due",
                       "track_performance", "delete_post", "fetch_metrics",
                       "refresh_metrics"):
            if self._fb is None:
                return AgentResult(
                    task_id=task.id, success=False,
                    error=f"FacebookAdapter unavailable: {self._fb_error or 'unknown'}",
                )

        if action == "publish_post":
            page_id = self._resolve_page_id(params)
            result = self._publish_post(
                message=params.get("message", ""),
                image_path=params.get("image_path"),
                page_id=page_id,
            )
            if result.success:
                self._mark_shared_done(
                    processed_designer_version=self._pipeline_version("designer"),
                    fb_post_id=result.data.get("fb_post_id", ""),
                    permalink=result.data.get("permalink", ""),
                    published_at=result.data.get("published_at", ""),
                )
            return result
        elif action == "publish_package":
            page_id = self._resolve_page_id(params)
            result = self._publish_package(params.get("package"), page_id=page_id)
            if result.success:
                self._mark_shared_done(
                    processed_designer_version=self._pipeline_version("designer"),
                    fb_post_id=result.data.get("fb_post_id", ""),
                    permalink=result.data.get("permalink", ""),
                )
            return result
        elif action == "publish_due":
            page_id = self._resolve_page_id(params)
            result = self._publish_post(
                message=params.get("message", "Bài viết mới từ Fanpage Agent 🎉"),
                image_path=params.get("image_path"),
                page_id=page_id,
            )
            if result.success:
                self._mark_shared_done(
                    processed_designer_version=self._pipeline_version("designer"),
                    fb_post_id=result.data.get("fb_post_id", ""),
                    permalink=result.data.get("permalink", ""),
                    published_at=result.data.get("published_at", ""),
                )
            return result
        elif action == "track_performance":
            page_id = self._resolve_page_id(params)
            return self._track_performance(
                fb_post_id=params.get("fb_post_id", ""),
                variant_id=params.get("variant_id", ""),
                package_id=params.get("package_id"),
                page_id=page_id,
            )
        elif action == "delete_post":
            page_id = self._resolve_page_id(params)
            return self._delete_post(params.get("fb_post_id", ""), page_id=page_id)
        elif action == "fetch_metrics":
            page_id = self._resolve_page_id(params)
            return self._fetch_metrics(limit=params.get("limit", 10), page_id=page_id)
        elif action == "refresh_metrics":
            page_id = self._resolve_page_id(params)
            return self._refresh_metrics(limit=params.get("limit", 10), page_id=page_id)
        return AgentResult(
            task_id=task.id, success=False, error=f"Unknown action: {action}"
        )

    def self_driving_tick(self) -> list[tuple[str, dict, ActionPriority]]:
        """Propose: publish designer's content, or periodic metrics refresh."""
        proposals: list[tuple[str, dict, ActionPriority]] = []

        # Check for new designer content (choreography chain)
        if self._has_upstream_data("designer", "processed_designer_version"):
            proposals.append(("publish_due", {
                "message": "Bài viết mới từ Fanpage Agent 🎉",
            }, ActionPriority.HIGH))
        elif self._should_act("refresh_metrics", 10800):
            proposals.append(("refresh_metrics", {"limit": 10}, ActionPriority.LOW))

        return proposals

    def _publish_post(
        self, message: str, image_path: str | None = None,
        record_memory: bool = True,
        page_id: str | None = None,
    ) -> AgentResult:
        """Publish a single post — text or photo.

        Args:
            message: Post caption text.
            image_path: Optional local image file path.
            record_memory: If True, record post metadata in PerformanceMemory.
            page_id: Target Facebook page ID (default: adapter default).
        """
        try:
            if image_path:
                result = self._fb.publish_photo(
                    image_path=image_path, message=message, page_id=page_id
                )
            else:
                result = self._fb.publish_post(message=message, page_id=page_id)

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
                    page_id=page_id,
                )

            return AgentResult(
                task_id=f"pub-{fb_id or 'failed'}",
                success=success,
                data={
                    "fb_post_id": fb_id,
                    "permalink": permalink,
                    "published_at": datetime.now(timezone.utc).isoformat(),
                    "image": bool(image_path),
                    "page_id": page_id or "default",
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
        page_id: str | None = None,
    ) -> None:
        """Record a simple (non-package) post in PerformanceMemory."""
        from fanpage_agent.core.types import ContentPackage, ContentVariant

        effective_brand_id = page_id or ""
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
            brand_id=effective_brand_id,
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

    def _publish_package(self, package: ContentPackage | dict | None,
                         page_id: str | None = None) -> AgentResult:
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
            page_id=page_id,
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
            self._memory.record_publish(
                package=package,
                variant_id=variant.variant_id,
                reach=0,
                engagements=0,
                permalink=fb_result.data.get("permalink", ""),
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
        self, fb_post_id: str, variant_id: str, package_id: str | None = None,
        page_id: str | None = None,
    ) -> AgentResult:
        """Fetch and record post performance metrics from Facebook."""
        if not fb_post_id:
            return AgentResult(
                task_id="track", success=False, error="No fb_post_id provided"
            )

        try:
            insights = self._fb.get_post_insights(fb_post_id, page_id=page_id)
            reach = insights.get("reach", 0)
            likes = insights.get("likes", 0)
            comments = insights.get("comments", 0)
            shares = insights.get("shares", 0)
            engagements = likes + comments + shares

            # Update performance memory
            # For simple posts, package_id defaults to auto-{fb_post_id}
            if self._memory and variant_id:
                actual_pkg_id = package_id or f"auto-{fb_post_id}"
                self._memory.record_metrics_update(
                    package_id=actual_pkg_id,
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

    def _delete_post(self, fb_post_id: str, page_id: str | None = None) -> AgentResult:
        """Delete a published post."""
        try:
            self._fb.delete_post(fb_post_id, page_id=page_id)
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

    def _refresh_metrics(self, limit: int = 10, page_id: str | None = None) -> AgentResult:
        """Fetch recent page posts and update metrics in performance memory.

        For each tracked post in memory, fetches real likes/comments/shares
        and records them via record_metrics_update.
        """
        if not self._memory:
            return AgentResult(
                task_id="metrics-refresh",
                success=False,
                error="No performance memory available",
            )
        try:
            posts = self._fb.get_recent_posts(limit=limit, page_id=page_id)
            updated = 0
            errors = 0
            for post in posts:
                post_id = post.get("id", "")
                if not post_id:
                    continue
                try:
                    self._memory.record_metrics_update(
                        package_id=post_id,
                        variant_id=post_id,
                        reach=post.get("reach", 0),
                        engagements=post.get("engagements", 0),
                    )
                    updated += 1
                except Exception:
                    errors += 1

            return AgentResult(
                task_id="metrics-refresh",
                success=True,
                data={
                    "posts_fetched": len(posts),
                    "updated": updated,
                    "errors": errors,
                    "refreshed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as e:
            return AgentResult(
                task_id="metrics-refresh",
                success=False,
                error=f"Refresh metrics failed: {e}",
            )
    def _fetch_metrics(self, limit: int = 10, page_id: str | None = None) -> AgentResult:
        """Fetch recent page posts with engagement data."""
        try:
            posts = self._fb.get_recent_posts(limit=limit, page_id=page_id)
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
