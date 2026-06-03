from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fanpage_agent.config import Settings


class FacebookClient:
    """Adapter for the Facebook Graph API.

    Requires FB_PAGE_ID and FB_PAGE_TOKEN in Settings (from .env or env vars).
    Token must be a Page Access Token with publish_to_groups,
    pages_manage_posts, pages_read_engagement, pages_manage_comments
    permissions.
    """

    GRAPH_BASE = "https://graph.facebook.com"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.fb_page_id:
            raise RuntimeError("FB_PAGE_ID is required for Facebook API calls")
        if not settings.fb_page_token:
            raise RuntimeError("FB_PAGE_TOKEN is required for Facebook API calls")
        self.page_id = settings.fb_page_id
        self.api_version = settings.fb_api_version

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def post_to_page(self, message: str, link: str = "") -> dict:
        """Post a status / caption to the Facebook page.

        Returns the Graph API response containing 'id' (the post ID).
        """
        data: dict = {"message": message, "access_token": self.settings.fb_page_token}
        if link:
            data["link"] = link
        return self._request(
            "POST",
            f"/{self.api_version}/{self.page_id}/feed",
            data=data,
        )

    def post_photo(self, image_path: str, message: str = "") -> dict:
        """Post a photo to the Facebook page with optional caption.

        Uses multipart upload to the ``/{page_id}/photos`` endpoint.
        Accepts a local image file path.

        Returns the Graph API response containing ``id`` (photo ID) and
        ``post_id`` (feed post ID if published as a feed story).
        """
        import requests as _req

        url = (
            f"{self.GRAPH_BASE}/{self.api_version}/{self.page_id}/photos"
            f"?access_token={self.settings.fb_page_token}"
        )
        with open(image_path, "rb") as fh:
            resp = _req.post(url, files={"source": fh}, data={"message": message}, timeout=120)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            err = result["error"]
            raise RuntimeError(
                f"Facebook photo upload error {err.get('code', 0)}: {err.get('message', '')[:500]}"
            )
        return result

    def update_post(self, post_id: str, message: str) -> dict:
        """Update the message of an existing post (limited by Graph API)."""
        data: dict = {"message": message, "access_token": self.settings.fb_page_token}
        return self._request(
            "POST",
            f"/{self.api_version}/{post_id}",
            data=data,
        )

    def delete_post(self, post_id: str) -> dict:
        """Delete a post by ID. Returns {'success': True}."""
        params = {"access_token": self.settings.fb_page_token}
        return self._request(
            "DELETE",
            f"/{self.api_version}/{post_id}",
            data=params,
        )

    def reply_to_comment(self, comment_id: str, message: str) -> dict:
        """Reply to an existing comment on the page.

        Returns the Graph API response containing 'id'.
        """
        data = {"message": message, "access_token": self.settings.fb_page_token}
        return self._request(
            "POST",
            f"/{self.api_version}/{comment_id}/comments",
            data=data,
        )

    def get_post_insights(self, post_id: str) -> dict:
        """Fetch reach + engagement insights for a single post.

        Returns aggregated dict:
            {post_id, message, created_time, permalink_url,
             reach, impressions, likes, comments, shares, engagement_rate}
        """
        fields = (
            "message,created_time,permalink_url,shares,"
            "likes.limit(0).summary(true),comments.limit(0).summary(true)"
        )
        raw = self._request(
            "GET",
            f"/{self.api_version}/{post_id}",
            params={"fields": fields},
        )
        return self._parse_post_insights(raw)

    def get_page_posts(
        self, limit: int = 25, before: str = "", after: str = ""
    ) -> list[dict]:
        """Fetch recent posts from the page with insight fields.

        Returns a list of parsed insight dicts (same shape as
        get_post_insights).
        """
        fields = (
            "id,message,created_time,permalink_url,shares,"
            "likes.limit(0).summary(true),comments.limit(0).summary(true)"
        )
        params: dict = {
            "fields": fields,
            "limit": str(limit),
            "access_token": self.settings.fb_page_token,
        }
        if before:
            params["before"] = before
        if after:
            params["after"] = after
        raw = self._request(
            "GET",
            f"/{self.api_version}/{self.page_id}/posts",
            params=params,
        )
        data = raw.get("data", [])
        return [self._parse_post_insights(item) for item in data]

    def get_comments(
        self, post_id: str, limit: int = 25
    ) -> list[dict]:
        """Fetch comments on a post.

        Each comment dict: {id, message, from_name, created_time}.
        """
        fields = "id,message,from.fields(name),created_time"
        raw = self._request(
            "GET",
            f"/{self.api_version}/{post_id}/comments",
            params={"fields": fields, "limit": str(limit)},
        )
        results = []
        for c in raw.get("data", []):
            results.append({
                "id": c.get("id", ""),
                "message": c.get("message", ""),
                "from_name": c.get("from", {}).get("name", ""),
                "created_time": c.get("created_time", ""),
            })
        return results

    def get_conversations(self, limit: int = 10) -> list[dict]:
        """Fetch page conversations / inbox messages.

        Returns a list of conversation summaries.
        """
        fields = "id,message,from,created_time,unread"
        raw = self._request(
            "GET",
            f"/{self.api_version}/{self.page_id}/conversations",
            params={"fields": fields, "limit": str(limit)},
        )
        return raw.get("data", [])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Core HTTP helper — urllib-based, no external deps."""
        url = f"{self.GRAPH_BASE}{path}"

        # Merge access_token into params for every request
        merged_params = dict(params or {})
        if data and method == "POST":
            # POST: data dict goes in body, access_token in params (URL)
            merged_params["access_token"] = self.settings.fb_page_token
            body = urlencode(data).encode("utf-8")
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
        elif data and method == "DELETE":
            merged_params["access_token"] = self.settings.fb_page_token
            body = urlencode(data).encode("utf-8")
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
        else:
            # GET or DELETE without body data
            if "access_token" not in merged_params:
                merged_params["access_token"] = self.settings.fb_page_token
            body = None
            headers = {}

        # Append query string for any method
        if merged_params:
            url = f"{url}?{urlencode(merged_params)}"

        request = Request(url, data=body, headers=headers, method=method)

        try:
            with urlopen(request, timeout=60) as response:
                body_bytes = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Facebook HTTP error {exc.code}: {detail[:500]}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"Facebook connection error: {exc}") from exc

        try:
            parsed = json.loads(body_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Facebook returned non-JSON body: {body_bytes[:500]}"
            ) from exc

        # Graph API wraps errors in {"error": {...}}
        if "error" in parsed:
            err = parsed["error"]
            code = err.get("code", 0)
            msg = err.get("message", "unknown error")
            raise RuntimeError(f"Facebook Graph API error {code}: {msg[:500]}")

        return parsed

    @staticmethod
    def _parse_post_insights(raw: dict) -> dict:
        """Normalise a raw Graph API post response into insight dict."""
        likes_data = raw.get("likes", {}) or {}
        comments_data = raw.get("comments", {}) or {}
        shares_data = raw.get("shares", {}) or {}

        likes = likes_data.get("summary", {}).get("total_count", 0) if isinstance(likes_data, dict) else 0
        comments = comments_data.get("summary", {}).get("total_count", 0) if isinstance(comments_data, dict) else 0
        shares = shares_data.get("count", 0) if isinstance(shares_data, dict) else 0
        engagements = likes + comments + shares

        return {
            "id": raw.get("id", ""),
            "message": raw.get("message", ""),
            "created_time": raw.get("created_time", ""),
            "permalink_url": raw.get("permalink_url", ""),
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "engagements": engagements,
        }
