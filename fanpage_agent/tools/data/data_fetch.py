"""Data-fetch tool: pull posts, insights, and comments from Facebook into the store.

Reconstructed 2026-06-13: the original module lived in an untracked
``tools/data/`` directory that the ``data/`` .gitignore pattern silently
excluded from version control. Behaviour is specified by
``tests/test_data_fetch.py`` and the call sites in
``cli_commands/analytics.py`` and ``tools_defs/data.py``.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.config import Settings

logger = logging.getLogger(__name__)

COMMENT_FIELDNAMES = ["id", "post_id", "created_at", "source", "message"]

# Fallbacks when the store class doesn't define the header lists.
_METRICS_HEADERS = ["published_at", "topic", "pillar", "objective", "reach", "engagements", "leads"]
_HISTORY_HEADERS = [
    "published_at", "topic", "hook", "pillar", "objective", "permalink", "reach", "engagement_rate",
]


def _topic_from_message(message: str) -> str:
    """Derive a short topic label from a post message (first line, capped)."""
    first_line = (message or "").strip().splitlines()[0] if (message or "").strip() else ""
    return first_line[:100]


class DataFetchTool:
    """Fetch posts + insights + comments from Facebook and persist to a store.

    Works with all three store backends (local CSV, Google Sheets, sqlite).
    History rows go through the store's ``_append_history_entry``; metric
    rows are upserted by ``(published_at, topic)`` — the same key
    ``record_post_metrics`` uses — via whichever row API the backend exposes.
    """

    def __init__(
        self,
        settings: Settings,
        fb_client: Any | None = None,
        store: Any | None = None,
        comment_csv: str | Path | None = None,
    ) -> None:
        self.settings = settings
        self.fb_client = fb_client or FacebookClient(settings)
        self.store = store
        self.comment_csv = Path(comment_csv) if comment_csv else None

    # ── Public API ──────────────────────────────────────────────────

    def fetch_all(
        self,
        post_limit: int = 90,
        comment_posts: int = 20,
        comment_limit: int = 25,
    ) -> dict[str, Any]:
        """Fetch posts once, then write history + metrics (+ comments).

        Returns a summary dict consumed by the CLI / agent tool layer:
        ``{status, posts_fetched, history_written, metrics_written,
        comments_fetched[, error]}``.
        """
        result: dict[str, Any] = {
            "status": "ok",
            "posts_fetched": 0,
            "history_written": 0,
            "metrics_written": 0,
            "comments_fetched": 0,
        }
        try:
            posts = self.fb_client.get_page_posts(limit=post_limit)
        except Exception as exc:
            logger.warning("DataFetchTool: failed to fetch page posts: %s", exc)
            result["status"] = "error"
            result["error"] = str(exc)[:200]
            return result

        result["posts_fetched"] = len(posts)
        result["history_written"] = self._write_history(posts)
        result["metrics_written"] = self._write_metrics(posts)

        if comment_posts > 0 and self.comment_csv is not None:
            try:
                result["comments_fetched"] = self._fetch_comments_for(
                    posts[:comment_posts], comment_limit
                )
            except Exception as exc:
                logger.warning("DataFetchTool: comment fetch failed: %s", exc)
                result["error"] = f"comment fetch failed: {exc}"[:200]
        return result

    def fetch_post_history(self, post_limit: int = 10) -> int:
        """Fetch posts and append history rows. Returns rows written."""
        return self._write_history(self.fb_client.get_page_posts(limit=post_limit))

    def fetch_post_metrics(self, post_limit: int = 10) -> int:
        """Fetch posts and upsert metric rows. Returns rows written."""
        return self._write_metrics(self.fb_client.get_page_posts(limit=post_limit))

    def fetch_comments(self, post_limit: int = 5, comment_limit: int = 25) -> int:
        """Fetch comments for recent posts, dedup by FB comment ID.

        Returns the number of NEW comments appended to ``comment_csv``.
        """
        posts = self.fb_client.get_page_posts(limit=post_limit)
        return self._fetch_comments_for(posts, comment_limit)

    # ── Internals ───────────────────────────────────────────────────

    def _write_history(self, posts: list[dict]) -> int:
        if self.store is None:
            return 0
        new_rows = [
            {
                "published_at": post.get("created_time", ""),
                "topic": _topic_from_message(post.get("message", "")),
                "hook": "",
                "pillar": "",
                "objective": "",
                "permalink": post.get("permalink_url", ""),
                "reach": str(post.get("reach", 0) or 0),
                "engagement_rate": str(post.get("engagement_rate", 0.0) or 0.0),
            }
            for post in posts
        ]
        store = self.store
        if hasattr(store, "_read_tab_as_dicts") and hasattr(store, "_replace_tab_rows"):
            # GoogleSheetsStore — replace-style write (the append API needs
            # an extra Sheets verb; replace covers create-tab too)
            tab = store._tab_name("post_history")
            rows = store._read_tab_as_dicts(tab, _HISTORY_HEADERS)
            rows.extend(new_rows)
            store._replace_tab_rows(tab, _HISTORY_HEADERS, rows)
        else:
            # LocalSheetStore / UnifiedStore
            for row in new_rows:
                store._append_history_entry(row)
        return len(new_rows)

    def _write_metrics(self, posts: list[dict]) -> int:
        if self.store is None:
            return 0
        new_rows = [self._metric_row(post) for post in posts]
        if new_rows:
            self._upsert_metric_rows(new_rows)
        return len(new_rows)

    @staticmethod
    def _metric_row(post: dict) -> dict[str, str]:
        likes = int(post.get("likes", 0) or 0)
        comments = int(post.get("comments", 0) or 0)
        shares = int(post.get("shares", 0) or 0)
        engagements = int(post.get("engagements", 0) or 0) or (likes + comments + shares)
        return {
            "published_at": post.get("created_time", ""),
            "topic": _topic_from_message(post.get("message", "")),
            "pillar": "",
            "objective": "",
            "reach": str(post.get("reach", 0) or 0),
            "engagements": str(engagements),
            "leads": "0",
        }

    def _upsert_metric_rows(self, new_rows: list[dict[str, str]]) -> None:
        """Upsert metric rows by (published_at, topic) across backends."""
        store = self.store
        if hasattr(store, "_read_metric_rows") and hasattr(store, "_write_metric_rows"):
            # LocalSheetStore (CSV)
            rows = store._read_metric_rows()
            store._write_metric_rows(self._merge_metric_rows(rows, new_rows))
        elif hasattr(store, "_read_tab_as_dicts") and hasattr(store, "_replace_tab_rows"):
            # GoogleSheetsStore
            headers = getattr(store, "METRICS_HEADERS", _METRICS_HEADERS)
            tab = store._tab_name("post_metrics")
            rows = store._read_tab_as_dicts(tab, headers)
            store._replace_tab_rows(tab, headers, self._merge_metric_rows(rows, new_rows))
        elif hasattr(store, "_conn"):
            # UnifiedStore (sqlite)
            with store._conn() as conn:
                for row in new_rows:
                    existing = conn.execute(
                        "SELECT 1 FROM post_metrics WHERE published_at=? AND topic=?",
                        (row["published_at"], row["topic"]),
                    ).fetchone()
                    if existing:
                        conn.execute(
                            "UPDATE post_metrics SET reach=?, engagements=?, leads=?"
                            " WHERE published_at=? AND topic=?",
                            (
                                int(row["reach"]),
                                int(row["engagements"]),
                                int(row["leads"]),
                                row["published_at"],
                                row["topic"],
                            ),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO post_metrics"
                            " (published_at, topic, pillar, objective, reach, engagements, leads)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                row["published_at"],
                                row["topic"],
                                row["pillar"],
                                row["objective"],
                                int(row["reach"]),
                                int(row["engagements"]),
                                int(row["leads"]),
                            ),
                        )
        else:
            raise TypeError(
                f"Store {type(store).__name__} exposes no known metric-row API"
            )

    @staticmethod
    def _merge_metric_rows(
        existing: list[dict[str, str]], new_rows: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        merged = list(existing)
        index = {
            (row.get("published_at", ""), row.get("topic", "")): row for row in merged
        }
        for row in new_rows:
            key = (row.get("published_at", ""), row.get("topic", ""))
            if key in index:
                index[key].update(row)
            else:
                merged.append(row)
                index[key] = row
        return merged

    def _fetch_comments_for(self, posts: list[dict], comment_limit: int) -> int:
        if self.comment_csv is None:
            return 0
        existing_ids: set[str] = set()
        if self.comment_csv.exists():
            with self.comment_csv.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    existing_ids.add(row.get("id", ""))

        new_rows: list[dict[str, str]] = []
        for post in posts:
            post_id = post.get("id", "")
            if not post_id:
                continue
            try:
                comments = self.fb_client.get_comments(post_id, limit=comment_limit)
            except Exception as exc:
                logger.warning(
                    "DataFetchTool: failed to fetch comments for %s: %s", post_id, exc
                )
                continue
            for comment in comments:
                comment_id = comment.get("id", "")
                if not comment_id or comment_id in existing_ids:
                    continue
                existing_ids.add(comment_id)
                new_rows.append(
                    {
                        "id": comment_id,
                        "post_id": post_id,
                        "created_at": comment.get("created_time", ""),
                        "source": "facebook_comment",
                        "message": comment.get("message", ""),
                    }
                )

        if new_rows:
            self.comment_csv.parent.mkdir(parents=True, exist_ok=True)
            file_exists = self.comment_csv.exists()
            with self.comment_csv.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=COMMENT_FIELDNAMES)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(new_rows)
        return len(new_rows)
