"""V2 Facebook adapter — wraps V1 FacebookClient for V2 agents.

Supports multi-page (per-fb_adapter) via PageRegistry.
Each method accepts an optional ``page_id`` parameter.
"""

from __future__ import annotations

from typing import Any

from fanpage_agent.adapters.facebook_client import FacebookClient as _FacebookClient
from fanpage_agent_v2.adapters.page_registry import PageRegistry, get_registry
from fanpage_agent_v2.adapters.settings import get_settings


class FacebookAdapter:
    """Thin wrapper around V1 FacebookClient, with multi-page support.

    Maintains a dict of page_id → FacebookClient for efficient reuse.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._registry: PageRegistry = get_registry(settings)
        self._clients: dict[str, _FacebookClient] = {}
        self._default_page_id = self._registry.default_page_id or settings.fb_page_id

    # ── Client lifecycle ─────────────────────────────────────────

    def _get_client(self, page_id: str | None = None) -> _FacebookClient:
        """Get or create a FacebookClient for the given page_id."""
        pid = page_id or self._default_page_id
        if pid in self._clients:
            return self._clients[pid]

        cfg = self._registry.get(pid)
        from config import Settings as _Settings

        fake_settings = _Settings(
            fb_page_id=cfg.page_id,
            fb_page_token=cfg.page_token,
            fb_api_version=cfg.api_version,
        )
        client = _FacebookClient(fake_settings)
        self._clients[pid] = client
        return client

    # ── Publish ──────────────────────────────────────────────────

    def publish_post(
        self, message: str, link: str = "", page_id: str | None = None
    ) -> dict[str, Any]:
        """Post a text/status to the page.

        Returns {"fb_post_id": "123_456", "permalink": "https://facebook.com/..."}
        """
        client = self._get_client(page_id)
        raw = client.post_to_page(message=message, link=link)
        fb_id: str = raw.get("id", "")
        permalink = f"https://facebook.com/{fb_id}" if fb_id else ""
        return {"fb_post_id": fb_id, "permalink": permalink}

    def publish_photo(
        self, image_path: str, message: str = "", page_id: str | None = None
    ) -> dict[str, Any]:
        """Post a photo with optional caption."""
        client = self._get_client(page_id)
        raw = client.post_photo(image_path=image_path, message=message)
        fb_id: str = raw.get("id", "")
        post_id: str = raw.get("post_id", "")
        permalink = f"https://facebook.com/{post_id}" if post_id else ""
        return {"fb_post_id": fb_id, "fb_post_id_full": post_id, "permalink": permalink}

    # ── Insights ─────────────────────────────────────────────────

    def get_post_insights(
        self, fb_post_id: str, page_id: str | None = None
    ) -> dict[str, Any]:
        """Fetch reach, likes, comments, shares for a post."""
        client = self._get_client(page_id)
        return client.get_post_insights(fb_post_id)

    def get_recent_posts(
        self, limit: int = 25, page_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return recent page posts with engagement data."""
        client = self._get_client(page_id)
        return client.get_page_posts(limit=limit)

    # ── Comments ─────────────────────────────────────────────────

    def comment_on_post(
        self, fb_post_id: str, message: str, page_id: str | None = None
    ) -> dict[str, Any]:
        """Comment on a post (can be used to self-reply on own post)."""
        client = self._get_client(page_id)
        return client.reply_to_comment(comment_id=fb_post_id, message=message)

    def get_comments(
        self, fb_post_id: str, limit: int = 25, page_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch comments on a post."""
        client = self._get_client(page_id)
        return client.get_comments(post_id=fb_post_id, limit=limit)

    def reply_to_comment(
        self, comment_id: str, message: str, page_id: str | None = None
    ) -> dict[str, Any]:
        """Reply to a specific comment."""
        client = self._get_client(page_id)
        return client.reply_to_comment(comment_id=comment_id, message=message)

    # ── Delete ───────────────────────────────────────────────────

    def delete_post(
        self, fb_post_id: str, page_id: str | None = None
    ) -> dict[str, Any]:
        """Delete a post by its Graph ID."""
        client = self._get_client(page_id)
        return client.delete_post(fb_post_id)

    # ── Conversations ────────────────────────────────────────────

    def get_conversations(
        self, limit: int = 10, page_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch page inbox conversations."""
        client = self._get_client(page_id)
        return client.get_conversations(limit=limit)

    # ── Registry access ──────────────────────────────────────────

    @property
    def registry(self) -> PageRegistry:
        return self._registry

    @property
    def available_pages(self) -> list[str]:
        return self._registry.all_page_ids
