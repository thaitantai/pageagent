from __future__ import annotations

import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fanpage_agent.audit import audit
from fanpage_agent.config import Settings
from fanpage_agent.throttle import TokenBucket

logger = logging.getLogger(__name__)


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
        settings.require("fb_page_id", "fb_page_token")
        self.page_id = settings.fb_page_id
        self.api_version = settings.fb_api_version
        self._limiter = TokenBucket(capacity=180, window_sec=3600.0)  # 180 req/h

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
        import random

        import requests as _req

        self._limiter.acquire(tokens=1.0)

        with audit(
            event_type="fb.photo_upload",
            source="FacebookClient.post_photo",
            image_path=image_path[:200],
        ) as actx:
            for attempt in range(3 + 1):  # _retries=3
                url = (
                    f"{self.GRAPH_BASE}/{self.api_version}/{self.page_id}/photos"
                    f"?access_token={self.settings.fb_page_token}"
                )
                try:
                    with open(image_path, "rb") as fh:
                        resp = _req.post(
                            url, files={"source": fh}, data={"message": message}, timeout=120
                        )
                    resp.raise_for_status()
                    result = resp.json()
                    if "error" in result:
                        err = result["error"]
                        raise RuntimeError(
                            f"Facebook photo upload error {err.get('code', 0)}: {err.get('message', '')[:500]}"
                        )
                    actx["data"]["photo_id"] = result.get("id", "")
                    return result
                except (_req.exceptions.HTTPError, RuntimeError) as exc:
                    msg = str(exc)
                    is_429 = (
                        "429" in msg
                        or "rate limit" in msg.lower()
                        or "too many requests" in msg.lower()
                    )
                    if is_429 and attempt < 3:
                        delay = min(2.0 * (2**attempt), 60.0)
                        delay *= 1.0 + random.random() * 0.5
                        logger.warning(
                            "429 on photo upload, retry %d/3 in %.1fs: %s",
                            attempt + 1,
                            delay,
                            msg[:120],
                        )
                        time.sleep(delay)
                        self._limiter.acquire(tokens=1.0)
                        continue
                    if attempt >= 3:
                        actx["data"]["status"] = "exhausted"
                        actx["data"]["error"] = msg[:200]
                        continue
                    actx["data"]["status"] = "error"
                    actx["data"]["error"] = msg[:200]
                    raise
            raise RuntimeError("Photo upload failed after 3 retries")

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
        with audit(
            event_type="fb.comment_reply",
            source="FacebookClient.reply_to_comment",
            comment_id=comment_id,
        ) as actx:
            data = {"message": message, "access_token": self.settings.fb_page_token}
            result = self._request(
                "POST",
                f"/{self.api_version}/{comment_id}/comments",
                data=data,
            )
            actx["data"]["reply_id"] = result.get("id", "")
            return result

    def get_post_insights(self, post_id: str) -> dict:
        """Fetch reach + engagement insights for a single post.

        Returns aggregated dict:
            {id, message, created_time, permalink_url,
             reach, likes, comments, shares, engagements, engagement_rate}

        Reach comes from the /insights edge (post_impressions_unique).
        If insights aren't available yet (<24h old or missing perms),
        reach defaults to 0.

        Note: FB Graph API v21.0+ requires ``pageId_postId`` format.
        If ``post_id`` is bare (no underscore), we prepend ``{page_id}_``.
        """
        if "_" not in post_id:
            post_id = f"{self.page_id}_{post_id}"
        fields = (
            "message,created_time,permalink_url,shares,"
            "likes.limit(0).summary(true),comments.limit(0).summary(true)"
        )
        raw = self._request(
            "GET",
            f"/{self.api_version}/{post_id}",
            params={"fields": fields},
        )
        result = self._parse_post_insights(raw)

        # ── Fetch real reach from /insights edge ──
        # This is a separate endpoint; may fail for new posts (<24h)
        try:
            insights_raw = self._request(
                "GET",
                f"/{self.api_version}/{post_id}/insights",
                params={"metric": "post_impressions_unique,post_engaged_users"},
            )
            for item in insights_raw.get("data", []):
                name = item.get("name", "")
                values = item.get("values", [])
                val = values[-1]["value"] if values else 0
                if name == "post_impressions_unique":
                    result["reach"] = int(val)
                elif name == "post_engaged_users":
                    result["engaged_users"] = int(val)
        except RuntimeError:
            pass  # insights unavailable yet (new post) — reach stays 0

        # Recalculate engagement_rate if reach is now real
        if result.get("reach", 0) > 0:
            result["engagement_rate"] = round(
                result["engagements"] / result["reach"], 4
            )

        return result

    def get_page_posts(
        self, limit: int = 25
    ) -> list[dict]:
        """Fetch recent posts from the page with insight fields.

        Auto-paginates internally to collect up to *limit* posts.
        Returns a list of parsed insight dicts (same shape as
        get_post_insights).
        """
        fields = (
            "id,message,created_time,permalink_url,shares,"
            "likes.limit(0).summary(true),comments.limit(0).summary(true)"
        )
        all_posts: list[dict] = []
        after_cursor: str | None = None
        per_page = min(limit, 100)  # Graph API max per request

        while len(all_posts) < limit:
            params: dict = {
                "fields": fields,
                "limit": str(per_page),
                "access_token": self.settings.fb_page_token,
            }
            if after_cursor:
                params["after"] = after_cursor

            raw = self._request(
                "GET",
                f"/{self.api_version}/{self.page_id}/posts",
                params=params,
            )
            batch = raw.get("data", [])
            if not batch:
                break  # no more posts

            all_posts.extend(self._parse_post_insights(item) for item in batch)

            # Read next cursor from paging metadata
            paging = raw.get("paging") or {}
            cursors = paging.get("cursors") or {}
            after_cursor = cursors.get("after")

            if not after_cursor:
                break  # no more pages

        return all_posts[:limit]

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
    # Cross-page public API (any page_id, not just ours)
    # ------------------------------------------------------------------

    def get_public_page_info(self, page_id: str) -> dict:
        """Fetch basic info about any public Facebook page.

        Uses the authenticated page's token; the Graph API returns
        public metadata for any page a Page Access Token can see.

        Returns dict with keys: ``id``, ``name``, ``category``,
        ``description``, ``link``, ``fan_count``. Key may be absent
        if the field is not public.
        """
        return self._request(
            "GET",
            f"/{self.api_version}/{page_id}",
            params={
                "fields": "id,name,category,description,link,fan_count",
            },
        )

    def get_public_page_posts(
        self, page_id: str, limit: int = 25
    ) -> list[dict]:
        """Fetch recent posts from any public Facebook page.

        Returns the same insight-shaped dicts as :meth:`get_page_posts`,
        keyed by ``id``, ``message``, ``created_time``, ``permalink_url``,
        with like/comment/share counts.

        Parameters
        ----------
        page_id : str
            Target page ID (can be any public page).
        limit : int
            Max posts to fetch (max API limit: 100 per call).
        """
        fields = (
            "id,message,created_time,permalink_url,shares,"
            "likes.limit(0).summary(true),comments.limit(0).summary(true)"
        )
        raw = self._request(
            "GET",
            f"/{self.api_version}/{page_id}/posts",
            params={
                "fields": fields,
                "limit": str(limit),
                "access_token": self.settings.fb_page_token,
            },
        )
        data = raw.get("data", [])
        return [self._parse_post_insights(item) for item in data]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        params: dict | None = None,
        _retries: int = 3,
    ) -> dict:
        """Core HTTP helper — urllib-based, no external deps.

        Acquires a rate-limit token before each request.
        Retries on HTTP 429 (Too Many Requests) with exponential backoff.
        """
        import random

        self._limiter.acquire(tokens=1.0)

        with audit(
            event_type=f"fb.{method.lower()}",
            source="FacebookClient._request",
            path=path[:120],
        ) as actx:
            for attempt in range(_retries + 1):
                try:
                    result = self._do_request(method, path, data, params)
                    actx["data"]["status"] = "ok"
                    return result
                except RuntimeError as exc:
                    msg = str(exc)
                    is_429 = (
                        "HTTP error 429" in msg
                        or "rate limit" in msg.lower()
                        or "too many requests" in msg.lower()
                    )
                    if is_429 and attempt < _retries:
                        delay = min(2.0 * (2**attempt), 60.0)
                        delay *= 1.0 + random.random() * 0.5
                        logger.warning(
                            "429 detected, retry %d/%d in %.1fs: %s",
                            attempt + 1, _retries, delay, msg[:120],
                        )
                        time.sleep(delay)
                        continue
                    if attempt >= _retries:
                        actx["data"]["status"] = "exhausted"
                        actx["data"]["error"] = msg[:200]
                        continue
                    actx["data"]["status"] = "error"
                    actx["data"]["error"] = msg[:200]
                    raise
            raise RuntimeError(f"Request failed after {_retries} retries")

    def _do_request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Low-level HTTP call (no rate-limit, no retry)."""
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
            "reach": 0,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "engagements": engagements,
            "engagement_rate": 0.0,
        }
