"""Append-only audit log backed by SQLite.

Usage:
    from fanpage_agent_v2.audit import audit

    # Decorator — auto-logs success/failure + duration
    @audit(event_type="post.published", source="FacebookClient")
    def publish(message): ...

    # Context manager — manual log with extra detail
    with audit(event_type="web.search", source="WebSearchClient") as ctx:
        results = search(query)
        ctx.set_data({"query": query, "count": len(results)})

    # Check recent history
    mgr = AuditManager()
    entries = mgr.list(event_type="post.published", limit=10)
"""

from __future__ import annotations

import functools
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# ── Default path: under the V2 data dir ──────────────────────────────
_DEFAULT_DATA_DIR: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..",
    "data",
    "v2",
)

AUDIT_DB_FILENAME = "audit.db"

# ── Schema ────────────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL DEFAULT (datetime('now')),
    event_type  TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    event_data  TEXT,
    success     INTEGER NOT NULL DEFAULT 1,
    duration_ms INTEGER,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_log_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts  ON audit_log(timestamp);
"""

_RETENTION_SQL = """
DELETE FROM audit_log WHERE timestamp < datetime('now', ?)
"""


# ── Data class ────────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    """One row from the audit log."""

    id: int
    timestamp: str
    event_type: str
    source: str
    event_data: dict[str, Any] | None = field(default=None)
    success: bool = True
    duration_ms: int | None = None
    error: str | None = None


# ── Manager ───────────────────────────────────────────────────────────

class AuditManager:
    """SQLite-backed append-only audit log.

    Thread-safe (per-connection, no shared connection).
    Default retention: 30 days (configurable via constructor).
    """

    def __init__(
        self,
        db_dir: str | None = None,
        retention_days: int = 30,
    ) -> None:
        data_dir = db_dir or _DEFAULT_DATA_DIR
        os.makedirs(data_dir, exist_ok=True)
        self._db_path = os.path.join(data_dir, AUDIT_DB_FILENAME)
        self._retention_days = retention_days
        self._init_db()

    # ── Public API ────────────────────────────────────────────────────

    def record(
        self,
        event_type: str,
        source: str,
        event_data: dict[str, Any] | None = None,
        success: bool = True,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> int:
        """Append a single event to the ledger.

        Returns the row ID.
        """
        data_json = json.dumps(event_data, ensure_ascii=False) if event_data else None
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO audit_log (event_type, source, event_data, success, duration_ms, error) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (event_type, source, data_json, 1 if success else 0, duration_ms, error),
            )
            row_id = cur.lastrowid or 0
        return row_id

    def list(
        self,
        event_type: str | None = None,
        source: str | None = None,
        success: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        since: str = "",
    ) -> list[AuditEntry]:
        """Query recent audit entries, newest first."""
        clauses: list[str] = []
        params: list[Any] = []

        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if success is not None:
            clauses.append("success = ?")
            params.append(1 if success else 0)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)

        where = " AND ".join(clauses) if clauses else "1"
        sql = f"SELECT id, timestamp, event_type, source, event_data, success, duration_ms, error "
        sql += f"FROM audit_log WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [self._row_to_entry(r) for r in rows]

    def count(
        self,
        event_type: str | None = None,
        source: str | None = None,
        success: bool | None = None,
        since: str = "",
    ) -> int:
        """Count matching events."""
        clauses: list[str] = []
        params: list[Any] = []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if success is not None:
            clauses.append("success = ?")
            params.append(1 if success else 0)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        where = " AND ".join(clauses) if clauses else "1"
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM audit_log WHERE {where}", params
            ).fetchone()
            return row[0] if row else 0

    def summary(self, since: str = "-24 hours") -> dict[str, int]:
        """Get event_type → count for a time window."""
        sql = """
            SELECT event_type, COUNT(*) AS cnt
            FROM audit_log
            WHERE timestamp >= datetime('now', ?)
            GROUP BY event_type
            ORDER BY cnt DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (since,)).fetchall()
        return {r[0]: r[1] for r in rows}

    def vacuum(self) -> int:
        """Purge entries older than retention_days and VACUUM.

        Returns number of rows removed.
        """
        with self._connect() as conn:
            # Count before
            before_row = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()
            before = before_row[0] if before_row else 0
            days_arg = f"-{self._retention_days} days"
            conn.execute(_RETENTION_SQL, (days_arg,))
            conn.commit()  # commit DELETE so VACUUM can run
            conn.execute("VACUUM")
            # Count after
            after_row = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()
            after = after_row[0] if after_row else 0
        removed = before - after
        if removed:
            logger.info("Audit: purged %d entries older than %d days", removed, self._retention_days)
        return removed

    # ── Internals ─────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_CREATE_TABLE)

    def _connect(self) -> sqlite3.Connection:
        """Get a fresh connection (thread-safe, no shared state)."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        # WAL mode for concurrent readers
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> AuditEntry:
        data = None
        raw = row["event_data"]
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"raw": raw}
        return AuditEntry(
            id=row["id"],
            timestamp=row["timestamp"],
            event_type=row["event_type"],
            source=row["source"],
            event_data=data,
            success=bool(row["success"]),
            duration_ms=row["duration_ms"],
            error=row["error"],
        )


# ── Convenience helpers ──────────────────────────────────────────────

@contextmanager
def audit(
    event_type: str,
    source: str,
    manager: AuditManager | None = None,
    **extra_data: Any,
) -> Iterator[dict[str, Any]]:
    """Context manager: auto-log on exit (success or error).

    Usage:
        with audit("post.published", "FacebookClient", post_id="abc") as ctx:
            publish()

    Sets ctx["data"] (dict to extend) and ctx["entry_id"] after commit.
    """
    mgr = manager or AuditManager()
    t0 = time.monotonic()
    data: dict[str, Any] = dict(extra_data)
    ctx_dict: dict[str, Any] = {"data": data, "entry_id": None}
    try:
        yield ctx_dict
        duration = int((time.monotonic() - t0) * 1000)
        ctx_dict["entry_id"] = mgr.record(
            event_type=event_type,
            source=source,
            event_data=data,
            success=True,
            duration_ms=duration,
        )
    except Exception as exc:
        duration = int((time.monotonic() - t0) * 1000)
        ctx_dict["entry_id"] = mgr.record(
            event_type=event_type,
            source=source,
            event_data=data,
            success=False,
            duration_ms=duration,
            error=str(exc)[:500],
        )
        raise


def audit_sync(
    event_type: str,
    source: str,
    manager: AuditManager | None = None,
    **extra_data: Any,
) -> int:
    """Fire-and-forget: record a single event immediately.

    Returns the entry ID.
    """
    mgr = manager or AuditManager()
    return mgr.record(
        event_type=event_type,
        source=source,
        event_data=extra_data or None,
        success=True,
    )


__all__ = [
    "AuditEntry",
    "AuditManager",
    "audit",
    "audit_sync",
]
