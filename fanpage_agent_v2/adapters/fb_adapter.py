"""V2 Facebook adapter — wraps V1 FacebookClient for V2 agents.

Provides V2-friendly methods (publish, get_posts, get_comments)
while reusing the battle-tested V1 Graph API client.
"""
from __future__ import annotations

from typing import Any

from fanpage_agent.adapters.facebook_client import FacebookClient as _FacebookClient
from fanpage_agent_v2.adapters.settings import get_settings


class FacebookAdapter:
    """Thin wrapper around V1 FacebookClient tailored for V2 agents."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = _FacebookClient(settings)
        self._page_id = settings.fb_page_id

    # ── Publish ──────────────────────────────────────────────────

    def publish_post(self, message: str, link: str = "") -> dict[str, Any]:
        """Post a text/status to the page.

        Returns {"fb_post_id": "123_456", "permalink": "https://facebook.com/..."}
        """
        raw = self._client.post_to_page(message=message, link=link)
        fb_id: str = raw.get("id", "")
        permalink = f"https://facebook.com/{fb_id}" if fb_id else ""
        return {"fb_post_id": fb_id, "permalink": permalink}

    def publish_photo(self, image_path: str, message: str = "") -> dict[str, Any]:
        """Post a photo with optional caption."""
        raw = self._client.post_photo(image_path=image_path, message=message)
        fb_id: str = raw.get("id", "")
        post_id: str = raw.get("post_id", "")
        permalink = f"https://facebook.com/{post_id}" if post_id else ""
        return {"fb_post_id": fb_id, "fb_post_id_full": post_id, "permalink": permalink}

    # ── Insights ─────────────────────────────────────────────────

    def get_post_insights(self, fb_post_id: str) -> dict[str, Any]:
        """Fetch reach, likes, comments, shares for a post.

        Returns:
            {id, message, created_time, permalink_url, likes, comments,
             shares, engagements}
        """
        return self._client.get_post_insights(fb_post_id)

    def get_recent_posts(self, limit: int = 25) -> list[dict[str, Any]]:
        """Return recent page posts with engagement data."""
        return self._client.get_page_posts(limit=limit)

    # ── Comments ─────────────────────────────────────────────────

    def get_comments(self, fb_post_id: str, limit: int = 25) -> list[dict[str, Any]]:
        """Fetch comments on a post.

        Each comment: {id, message, from_name, created_time}
        """
        return self._client.get_comments(post_id=fb_post_id, limit=limit)

    def reply_to_comment(self, comment_id: str, message: str) -> dict[str, Any]:
        """Reply to a specific comment."""
        return self._client.reply_to_comment(comment_id=comment_id, message=message)

    # ── Delete ───────────────────────────────────────────────────

    def delete_post(self, fb_post_id: str) -> dict[str, Any]:
        """Delete a post by its Graph ID."""
        return self._client.delete_post(fb_post_id)

    # ── Conversations ────────────────────────────────────────────

    def get_conversations(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch page inbox conversations."""
        return self._client.get_conversations(limit=limit)
