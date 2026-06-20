"""DataFetchTool — Shared Facebook → Store fetcher.

Any agent (Research, Community, Strategist) can call this to populate
post_history, post_metrics, and comment_inbox from live Facebook data.

Usage:
    service = DataFetchTool(settings, store=store)
    service.fetch_all(post_limit=90, comment_posts=20, comment_limit=25)
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.adapters.google_sheets_store import GoogleSheetsStore
from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.config import Settings

logger = logging.getLogger(__name__)


class DataFetchTool:
    """Fetch Facebook data and persist to the active store backend.

    Works with both GoogleSheetsStore and LocalSheetStore.
    Agents read from the store; this service writes to it.
    """

    def __init__(
        self,
        settings: Settings,
        fb_client: FacebookClient | None = None,
        store: GoogleSheetsStore | LocalSheetStore | None = None,
        comment_csv: str | Path | None = None,
    ) -> None:
        self.settings = settings
        self.fb = fb_client or FacebookClient(settings)
        self.store = store
        self.comment_csv = Path(comment_csv) if comment_csv else None

    # ── Public API ──────────────────────────────────────────────

    def fetch_all(
        self,
        post_limit: int = 90,
        comment_posts: int = 20,
        comment_limit: int = 25,
    ) -> dict[str, Any]:
        """Fetch posts, insights, and comments from Facebook → store.

        Returns a summary dict with counts per data type.
        """
        logger.info("DataFetch: fetching up to %d posts...", post_limit)

        try:
            posts = self.fb.get_page_posts(limit=post_limit)
        except Exception as exc:
            logger.error("DataFetch: failed to fetch posts: %s", exc)
            return {
                "status": "error",
                "error": str(exc)[:300],
                "posts_fetched": 0,
                "history_written": 0,
                "metrics_written": 0,
                "comments_fetched": 0,
            }

        if not posts:
            logger.info("DataFetch: no posts returned from Facebook.")
            return {
                "status": "ok",
                "posts_fetched": 0,
                "history_written": 0,
                "metrics_written": 0,
                "comments_fetched": 0,
            }

        # ── Write to post_history ──
        history_count = self._write_history(posts)
        # ── Write to post_metrics ──
        metrics_count = self._write_metrics(posts)

        # ── Fetch and write comments ──
        comments_count = 0
        if self.comment_csv or isinstance(self.store, LocalSheetStore):
            recent = posts[:comment_posts]
            comments_count = self._fetch_and_write_comments(recent, comment_limit)

        return {
            "status": "ok",
            "posts_fetched": len(posts),
            "history_written": history_count,
            "metrics_written": metrics_count,
            "comments_fetched": comments_count,
        }

    def fetch_post_history(self, post_limit: int = 90) -> int:
        """Fetch posts → post_history tab/CSV only. Returns rows written."""
        try:
            posts = self.fb.get_page_posts(limit=post_limit)
        except Exception as exc:
            logger.error("DataFetch: failed to fetch posts: %s", exc)
            return 0
        return self._write_history(posts)

    def fetch_post_metrics(self, post_limit: int = 90) -> int:
        """Fetch posts → post_metrics tab/CSV only. Returns rows written."""
        try:
            posts = self.fb.get_page_posts(limit=post_limit)
        except Exception as exc:
            logger.error("DataFetch: failed to fetch post metrics: %s", exc)
            return 0
        return self._write_metrics(posts)

    def fetch_comments(self, post_limit: int = 20, comment_limit: int = 25) -> int:
        """Fetch comments from recent posts → comment CSV. Returns comments fetched."""
        try:
            posts = self.fb.get_page_posts(limit=post_limit)
        except Exception as exc:
            logger.error("DataFetch: failed to fetch posts for comments: %s", exc)
            return 0
        return self._fetch_and_write_comments(posts, comment_limit)

    # ── Internal: history ───────────────────────────────────────

    def _write_history(self, posts: list[dict]) -> int:
        """Transform FB posts → HISTORY_HEADERS and write to store."""
        headers = LocalSheetStore.HISTORY_HEADERS  # ["published_at", "topic", "hook", "pillar", "objective", "permalink", "reach", "engagement_rate"]
        rows = [
            [
                p.get("created_time", ""),
                "",  # topic — unknown for FB-native posts
                "",  # hook
                "",  # pillar
                "",  # objective
                p.get("permalink_url", ""),
                str(int(p.get("reach", 0))),
                str(round(float(p.get("engagement_rate", 0.0)), 4)),
            ]
            for p in posts
        ]
        return self._write_to_tab("post_history", headers, rows)

    def _write_metrics(self, posts: list[dict]) -> int:
        """Transform FB posts → METRICS_HEADERS and write to store."""
        headers = (
            GoogleSheetsStore.METRICS_HEADERS
        )  # ["published_at", "topic", "pillar", "objective", "reach", "engagements", "leads"]
        rows = [
            [
                p.get("created_time", ""),
                "",  # topic
                "",  # pillar
                "",  # objective
                str(int(p.get("reach", 0))),
                str(int(p.get("engagements", 0))),
                "0",  # leads — unknown for FB-native posts
            ]
            for p in posts
        ]
        return self._write_to_tab("post_metrics", headers, rows)

    # ── Internal: comments ──────────────────────────────────────

    def _fetch_and_write_comments(self, posts: list[dict], comment_limit: int) -> int:
        """Fetch comments for given posts → CSV. Dedup by FB comment id."""
        # Gather all comments from FB
        all_comments: list[dict] = []
        for post in posts:
            post_id = post.get("id", "")
            if not post_id:
                continue
            try:
                comments = self.fb.get_comments(post_id, limit=comment_limit)
            except Exception as exc:
                logger.warning("DataFetch: comment fetch failed for %s: %s", post_id, exc)
                continue
            for c in comments:
                c["post_id"] = post_id
                all_comments.append(c)

        if not all_comments:
            return 0

        # Determine comment file path
        comment_path = self._resolve_comment_path()
        if comment_path is None:
            logger.warning("DataFetch: no comment path configured — skipping comment write")
            return len(all_comments)

        # Dedup and merge
        existing_ids: set[str] = set()
        existing_rows: list[dict] = []
        fieldnames = ["id", "post_id", "created_at", "source", "message"]

        if comment_path.exists():
            with comment_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_rows.append(row)
                    if row.get("id"):
                        existing_ids.add(row["id"])

        new_rows: list[dict] = []
        for c in all_comments:
            cid = c.get("id", "")
            if cid and cid in existing_ids:
                continue
            new_rows.append(
                {
                    "id": c.get("id", ""),
                    "post_id": c.get("post_id", ""),
                    "created_at": c.get("created_time", ""),
                    "source": "facebook_comment",
                    "message": c.get("message", ""),
                }
            )
            if cid:
                existing_ids.add(cid)

        if not new_rows:
            logger.info("DataFetch: no new comments to add.")
            return 0

        all_rows = existing_rows + new_rows
        with comment_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        logger.info("DataFetch: added %d new comments (total: %d)", len(new_rows), len(all_rows))
        return len(new_rows)

    # ── Internal: store-agnostic write ──────────────────────────

    def _write_to_tab(self, tab_base: str, headers: list[str], rows: list[list[str]]) -> int:
        """Write rows to the active store backend.

        * GoogleSheetsStore → bulk_load_data into ``{prefix}_{tab_base}`` tab.
        * LocalSheetStore → write to corresponding CSV file.
        """
        store = self.store
        if store is None:
            logger.warning("DataFetch: no store configured — skipping write to %s", tab_base)
            return 0

        if isinstance(store, GoogleSheetsStore):
            tab_name = store._tab_name(tab_base)
            store.ensure_tab(tab_name)
            return store.bulk_load_data(tab_name, headers, rows)

        if isinstance(store, LocalSheetStore):
            return self._write_local_csv(tab_base, headers, rows)

        logger.warning("DataFetch: unknown store type %s — skipping", type(store).__name__)
        return 0

    def _write_local_csv(self, tab_base: str, headers: list[str], rows: list[list[str]]) -> int:
        """Write rows to LocalSheetStore CSV files."""
        s = self.store
        if not isinstance(s, LocalSheetStore):
            logger.warning("DataFetch: store is not LocalSheetStore — skipping")
            return 0
        if tab_base == "post_history" and s.history_csv:
            self._write_csv(s.history_csv, headers, rows)
            return len(rows)
        if tab_base == "post_metrics" and s.metrics_csv:
            self._write_csv(s.metrics_csv, headers, rows)
            return len(rows)
        logger.warning("DataFetch: LocalSheetStore has no CSV path for '%s'", tab_base)
        return 0

    @staticmethod
    def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
        """Overwrite a CSV file with headers + rows."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

    # ── Helpers ─────────────────────────────────────────────────

    def _resolve_comment_path(self) -> Path | None:
        """Return the comment CSV path from constructor, settings, or store."""
        if self.comment_csv:
            return self.comment_csv
        store = self.store
        if isinstance(store, LocalSheetStore):
            return store.triage_csv  # triage CSV path is close enough
        # google sheets store doesn't use comment CSV — comments go to triage tab
        return None
