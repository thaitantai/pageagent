"""Unified SQLite Store — single source of truth for all sub-agents.

Replaces LocalSheetStore (CSV) + TopicPerformanceStore (JSON) + GoogleSheetsStore.
Backward-compatible with the LocalSheetStore interface so StoreAdapter works unchanged.

Schema covers:
- calendar        → content planning & publishing
- post_history    → published post snapshots
- post_metrics    → performance per post (reach, engagements, leads)
- triage_items    → community comment/inbox triage
- hashtag_usage   → hashtag performance tracking
- topic_performance → aggregated topic stats (replaces TopicPerformanceStore)
- research_briefs → brief scores for feedback loop
- learned_weights → dynamic scoring weights
"""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from fanpage_agent.models import (
    CommunityTriageItem,
    PostHistoryEntry,
    PostMetric,
    WeeklyPlan,
)

logger = logging.getLogger(__name__)

# Resolve DB path relative to this file (fanpage-agent project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "agent" / "agent.db"

_SCHEMA_SQL = """
-- Content Calendar
CREATE TABLE IF NOT EXISTS calendar (
    calendar_id TEXT PRIMARY KEY,
    brand_id TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    pillar TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    angle TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL DEFAULT '',
    hook TEXT NOT NULL DEFAULT '',
    cta TEXT NOT NULL DEFAULT '',
    visual_brief TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned',
    approval_status TEXT NOT NULL DEFAULT 'pending',
    approved_by TEXT NOT NULL DEFAULT '',
    final_caption_ref TEXT NOT NULL DEFAULT '',
    draft_caption_ref TEXT NOT NULL DEFAULT '',
    campaign_tag TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    permalink TEXT NOT NULL DEFAULT '',
    reach INTEGER NOT NULL DEFAULT 0,
    engagement_rate REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Published post history (snapshot when published)
CREATE TABLE IF NOT EXISTS post_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    published_at TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    hook TEXT NOT NULL DEFAULT '',
    pillar TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL DEFAULT '',
    permalink TEXT NOT NULL DEFAULT '',
    reach INTEGER NOT NULL DEFAULT 0,
    engagement_rate REAL NOT NULL DEFAULT 0.0
);

-- Post metrics (updated later from FB API)
CREATE TABLE IF NOT EXISTS post_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    published_at TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    pillar TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL DEFAULT '',
    reach INTEGER NOT NULL DEFAULT 0,
    engagements INTEGER NOT NULL DEFAULT 0,
    leads INTEGER NOT NULL DEFAULT 0
);

-- Community triage
CREATE TABLE IF NOT EXISTS triage_items (
    triage_id TEXT PRIMARY KEY,
    brand_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'medium',
    recommended_action TEXT NOT NULL DEFAULT '',
    draft_reply TEXT NOT NULL DEFAULT '',
    escalation_required INTEGER NOT NULL DEFAULT 0,
    requires_human_approval INTEGER NOT NULL DEFAULT 0,
    matched_rules TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    assigned_to TEXT NOT NULL DEFAULT '',
    approved_by TEXT NOT NULL DEFAULT '',
    rejected_reason TEXT NOT NULL DEFAULT '',
    reply_sent_at TEXT NOT NULL DEFAULT '',
    reply_permalink TEXT NOT NULL DEFAULT '',
    resolved_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Hashtag usage tracking
CREATE TABLE IF NOT EXISTS hashtag_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id TEXT NOT NULL,
    brand_id TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    hashtags TEXT NOT NULL DEFAULT '',
    reach INTEGER NOT NULL DEFAULT 0,
    engagements INTEGER NOT NULL DEFAULT 0,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Topic performance (replaces TopicPerformanceStore JSON)
CREATE TABLE IF NOT EXISTS topic_performance (
    topic TEXT PRIMARY KEY,
    total_reach INTEGER NOT NULL DEFAULT 0,
    total_engagements INTEGER NOT NULL DEFAULT 0,
    total_posts INTEGER NOT NULL DEFAULT 0,
    avg_engagement_rate REAL NOT NULL DEFAULT 0.0,
    recent_engagement REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Research briefs (feedback loop: predicted vs actual)
CREATE TABLE IF NOT EXISTS research_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL,
    brand_id TEXT NOT NULL DEFAULT '',
    calendar_id TEXT DEFAULT '',
    topic TEXT NOT NULL,
    total_score REAL NOT NULL DEFAULT 0,
    brand_relevance REAL NOT NULL DEFAULT 0,
    novelty REAL NOT NULL DEFAULT 0,
    content_potential REAL NOT NULL DEFAULT 0,
    source_confidence REAL NOT NULL DEFAULT 0,
    fanpage_fit REAL NOT NULL DEFAULT 0,
    customer_value REAL NOT NULL DEFAULT 0,
    risk_penalty REAL NOT NULL DEFAULT 0,
    was_published INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Learned weights (dynamic weight tuning)
CREATE TABLE IF NOT EXISTS learned_weights (
    weight_name TEXT PRIMARY KEY,
    current_weight REAL NOT NULL,
    correlation_7d REAL NOT NULL DEFAULT 0,
    correlation_30d REAL NOT NULL DEFAULT 0,
    sample_since TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_calendar_date ON calendar(date);
CREATE INDEX IF NOT EXISTS idx_calendar_status ON calendar(status);
CREATE INDEX IF NOT EXISTS idx_post_history_date ON post_history(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_post_metrics_date ON post_metrics(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_triage_status ON triage_items(status);
CREATE INDEX IF NOT EXISTS idx_rbrief_generated ON research_briefs(generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rbrief_topic ON research_briefs(topic);

-- Learning runs (audit log for self-learning)
CREATE TABLE IF NOT EXISTS learning_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,
    executed_at TEXT NOT NULL DEFAULT (datetime('now')),
    summary TEXT NOT NULL DEFAULT '{}'
);
"""


class UnifiedStore:
    """SQLite-backed unified store for all fanpage-agent data.

    Interface-compatible with LocalSheetStore methods so it can be swapped
    in via store_factory.build_store().
    """

    # Same HEADERS as LocalSheetStore for consistency
    HEADERS = [
        "brand_id", "calendar_id", "date", "pillar", "objective", "topic",
        "angle", "format", "hook", "cta", "visual_brief", "status",
        "approval_status", "approved_by", "final_caption_ref", "draft_caption_ref",
        "campaign_tag", "notes", "last_updated", "published_at", "permalink",
        "reach", "engagement_rate",
    ]
    TRIAGE_HEADERS = [
        "triage_id", "brand_id", "created_at", "source", "message", "category",
        "priority", "recommended_action", "draft_reply", "escalation_required",
        "requires_human_approval", "matched_rules", "status", "assigned_to",
        "approved_by", "rejected_reason", "reply_sent_at", "reply_permalink",
        "resolved_at", "last_updated",
    ]
    HISTORY_HEADERS = [
        "published_at", "topic", "hook", "pillar", "objective",
        "permalink", "reach", "engagement_rate",
    ]
    METRICS_HEADERS = [
        "published_at", "topic", "pillar", "objective",
        "reach", "engagements", "leads",
    ]
    HASHTAG_HEADERS = [
        "calendar_id", "brand_id", "topic", "hashtags",
        "reach", "engagements", "recorded_at",
    ]

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or _DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        # Seed default weights if empty
        self._seed_default_weights()

    # ── Connection helpers ───────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        try:
            with self._conn() as conn:
                conn.executescript(_SCHEMA_SQL)
                self._migrate_schema(conn)
        except sqlite3.DatabaseError as exc:
            logger.warning("UnifiedStore: DB init failed — %s", exc)
            raise

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """Add columns that may be missing on older databases."""
        try:
            conn.execute("ALTER TABLE research_briefs ADD COLUMN updated_at TEXT NOT NULL DEFAULT (datetime('now'))")
        except sqlite3.OperationalError:
            pass  # column already exists

    def _seed_default_weights(self) -> None:
        defaults = {
            "brand_relevance": 0.25,
            "novelty": 0.16,
            "content_potential": 0.18,
            "source_confidence": 0.14,
            "fanpage_fit": 0.14,
            "customer_value": 0.10,
            "duplication_risk_penalty": 0.03,
            "evidence_confidence_floor": 0.45,
            "engagement_baseline": 50.0,
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            for name, weight in defaults.items():
                conn.execute(
                    """INSERT OR IGNORE INTO learned_weights
                       (weight_name, current_weight, correlation_7d, sample_since, updated_at)
                       VALUES (?, ?, 0, ?, ?)""",
                    (name, weight, now, now),
                )

    # ═══════════════════════════════════════════════════════════════
    # Calendar
    # ═══════════════════════════════════════════════════════════════

    def append_plan(self, brand_id: str, plan: WeeklyPlan) -> None:
        rows: list[dict[str, str | int | float]] = []
        for index, day in enumerate(plan.days, start=1):
            rows.append({
                "calendar_id": f"{plan.plan_title}-{index}",
                "brand_id": brand_id,
                "date": day.date,
                "pillar": day.pillar,
                "objective": day.objective,
                "topic": day.topic,
                "angle": day.angle,
                "format": day.format,
                "hook": day.hook,
                "cta": day.cta,
                "visual_brief": day.visual_brief,
                "status": "planned",
                "approval_status": "pending",
            })
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            for row in rows:
                conn.execute(
                    """INSERT OR REPLACE INTO calendar
                       (calendar_id, brand_id, date, pillar, objective, topic,
                        angle, format, hook, cta, visual_brief,
                        status, approval_status, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row["calendar_id"], row["brand_id"], row["date"],
                        row["pillar"], row["objective"], row["topic"],
                        row["angle"], row["format"], row["hook"], row["cta"],
                        row["visual_brief"], row["status"], row["approval_status"],
                        now,
                    ),
                )

    def list_calendar_items(
        self,
        brand_id: str | None = None,
        status: str | None = None,
        approval_status: str | None = None,
        date: str | None = None,
        metrics_pending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        conditions: list[str] = []
        params: list[Any] = []
        if brand_id:
            conditions.append("brand_id = ?")
            params.append(brand_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if approval_status:
            conditions.append("approval_status = ?")
            params.append(approval_status)
        if date:
            conditions.append("date = ?")
            params.append(date)
        if metrics_pending:
            conditions.append("reach = 0")
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        limit_clause = f" LIMIT {limit}" if limit else ""
        sql = f"SELECT * FROM calendar{where} ORDER BY date ASC{limit_clause}"

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def approve_calendar_item(
        self,
        calendar_id: str,
        approved_by: str,
        final_caption_ref: str,
        approved_at: str,
    ) -> dict[str, str]:
        return self._update_calendar_status(
            calendar_id, approved_by, final_caption_ref, approved_at,
            approval_status="approved", status="approved",
        )

    def reject_calendar_item(
        self, calendar_id: str, reason: str, rejected_at: str,
    ) -> dict[str, str]:
        with self._conn() as conn:
            conn.execute(
                """UPDATE calendar SET status='needs_revision',
                   approval_status='rejected', notes=?, updated_at=?
                   WHERE calendar_id=?""",
                (reason, rejected_at, calendar_id),
            )
            row = conn.execute(
                "SELECT * FROM calendar WHERE calendar_id=?", (calendar_id,)
            ).fetchone()
        return dict(row) if row else {}

    def publish_calendar_item(
        self,
        calendar_id: str,
        published_at: str,
        permalink: str,
        reach: int = 0,
        engagement_rate: float = 0.0,
    ) -> dict[str, str]:
        with self._conn() as conn:
            conn.execute(
                """UPDATE calendar SET status='published', published_at=?,
                   permalink=?, reach=?, engagement_rate=?, updated_at=?
                   WHERE calendar_id=?""",
                (published_at, permalink, reach, engagement_rate,
                 published_at, calendar_id),
            )
            row = conn.execute(
                "SELECT * FROM calendar WHERE calendar_id=?", (calendar_id,)
            ).fetchone()
            if row:
                self._append_history_entry(dict(row), conn=conn)
        return dict(row) if row else {}

    def attach_draft_caption_ref(
        self, calendar_id: str, caption_ref: str, updated_at: str,
    ) -> dict[str, str]:
        with self._conn() as conn:
            conn.execute(
                """UPDATE calendar SET draft_caption_ref=?, updated_at=?
                   WHERE calendar_id=?""",
                (caption_ref, updated_at, calendar_id),
            )
            row = conn.execute(
                "SELECT * FROM calendar WHERE calendar_id=?", (calendar_id,)
            ).fetchone()
        return dict(row) if row else {}

    def check_calendar_gaps(
        self,
        brand_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        max_gap_days: int = 3,
    ) -> list[dict[str, object]]:
        from datetime import date as _date
        from datetime import timedelta

        conditions = ["status IN ('planned', 'approved', 'published')"]
        params: list[Any] = []
        if brand_id:
            conditions.append("brand_id = ?")
            params.append(brand_id)

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT date FROM calendar WHERE {' AND '.join(conditions)}",
                params,
            ).fetchall()

        today = _date.today()
        start = _date.fromisoformat(start_date) if start_date else today
        end = _date.fromisoformat(end_date) if end_date else today + timedelta(days=14)

        scheduled: set[_date] = set()
        for r in rows:
            raw = r["date"]
            if raw:
                try:
                    scheduled.add(_date.fromisoformat(raw))
                except ValueError:
                    pass

        gaps: list[dict[str, object]] = []
        gap_start: _date | None = None
        cursor = start
        while cursor <= end:
            if cursor not in scheduled:
                if gap_start is None:
                    gap_start = cursor
            else:
                if gap_start is not None:
                    gap_days = (cursor - gap_start).days
                    if gap_days > max_gap_days:
                        gaps.append({
                            "start_date": gap_start.isoformat(),
                            "end_date": (cursor - timedelta(days=1)).isoformat(),
                            "gap_days": gap_days,
                        })
                    gap_start = None
            cursor += timedelta(days=1)

        if gap_start is not None:
            gap_days = (end - gap_start).days + 1
            if gap_days > max_gap_days:
                gaps.append({
                    "start_date": gap_start.isoformat(),
                    "end_date": end.isoformat(),
                    "gap_days": gap_days,
                })
        return gaps

    def _update_calendar_status(
        self, calendar_id, approved_by, final_caption_ref, approved_at,
        approval_status="approved", status="approved",
    ) -> dict[str, str]:
        with self._conn() as conn:
            conn.execute(
                """UPDATE calendar SET approval_status=?, status=?,
                   approved_by=?, final_caption_ref=?, updated_at=?
                   WHERE calendar_id=?""",
                (approval_status, status, approved_by, final_caption_ref,
                 approved_at, calendar_id),
            )
            row = conn.execute(
                "SELECT * FROM calendar WHERE calendar_id=?", (calendar_id,)
            ).fetchone()
        return dict(row) if row else {}

    # ═══════════════════════════════════════════════════════════════
    # Post history
    # ═══════════════════════════════════════════════════════════════

    def read_post_history(self, limit: int = 30) -> list[PostHistoryEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM post_history ORDER BY published_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            PostHistoryEntry(
                published_at=r["published_at"],
                topic=r["topic"],
                hook=r["hook"],
                pillar=r["pillar"],
                objective=r["objective"],
                permalink=r["permalink"],
                reach=r["reach"],
                engagement_rate=r["engagement_rate"],
            )
            for r in rows
        ]

    def _append_history_entry(
        self, row: dict[str, Any], conn: sqlite3.Connection | None = None,
    ) -> None:
        executor = conn if conn else self._conn()
        close = conn is None
        try:
            executor.execute(
                """INSERT INTO post_history
                   (published_at, topic, hook, pillar, objective, permalink, reach, engagement_rate)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row.get("published_at", ""),
                    row.get("topic", ""),
                    row.get("hook", ""),
                    row.get("pillar", ""),
                    row.get("objective", ""),
                    row.get("permalink", ""),
                    int(row.get("reach", 0)),
                    float(row.get("engagement_rate", 0.0)),
                ),
            )
        finally:
            if close:
                executor.close()

    # ═══════════════════════════════════════════════════════════════
    # Post metrics
    # ═══════════════════════════════════════════════════════════════

    def read_post_metrics(self) -> list[PostMetric]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM post_metrics ORDER BY published_at DESC"
            ).fetchall()
        return [
            PostMetric(
                published_at=r["published_at"],
                topic=r["topic"],
                pillar=r["pillar"],
                objective=r["objective"],
                reach=r["reach"],
                engagements=r["engagements"],
                leads=r["leads"],
            )
            for r in rows
        ]

    def record_post_metrics(
        self,
        calendar_id: str,
        reach: int,
        engagements: int,
        leads: int,
        recorded_at: str,
    ) -> dict[str, dict[str, str]]:
        with self._conn() as conn:
            # Update calendar
            engagement_rate = round((engagements / reach), 2) if reach > 0 else 0.0
            conn.execute(
                "UPDATE calendar SET reach=?, engagement_rate=?, updated_at=? WHERE calendar_id=?",
                (reach, engagement_rate, recorded_at, calendar_id),
            )
            cal_row = conn.execute(
                "SELECT * FROM calendar WHERE calendar_id=?", (calendar_id,)
            ).fetchone()

            # Upsert post_metrics
            published_at = cal_row["published_at"] if cal_row else ""
            topic = cal_row["topic"] if cal_row else ""
            pillar = cal_row["pillar"] if cal_row else ""
            obj = cal_row["objective"] if cal_row else ""
            existing = conn.execute(
                "SELECT id FROM post_metrics WHERE published_at=? AND topic=?",
                (published_at, topic),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE post_metrics SET reach=?, engagements=?, leads=?,
                       pillar=?, objective=? WHERE id=?""",
                    (reach, engagements, leads, pillar, obj, existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO post_metrics
                       (published_at, topic, pillar, objective, reach, engagements, leads)
                       VALUES (?,?,?,?,?,?,?)""",
                    (published_at, topic, pillar, obj, reach, engagements, leads),
                )

            # ═══ Feedback loop: update topic_performance + link research_briefs ═══
            if topic:
                self._record_topic_performance(conn, topic, reach, engagements, engagement_rate)
                self._mark_briefs_for_topic(conn, topic, calendar_id)

        return {
            "calendar": dict(cal_row) if cal_row else {},
            "metric": {
                "published_at": published_at,
                "topic": topic,
                "reach": str(reach),
                "engagements": str(engagements),
                "leads": str(leads),
            },
        }

    def _record_topic_performance(
        self,
        conn: sqlite3.Connection,
        topic: str,
        reach: int,
        engagements: int,
        engagement_rate: float,
    ) -> None:
        """Update topic_performance table (inline, within existing transaction)."""
        existing = conn.execute(
            "SELECT * FROM topic_performance WHERE topic=?", (topic,)
        ).fetchone()
        if existing:
            tp = existing["total_posts"]
            new_avg = (existing["avg_engagement_rate"] * tp + engagement_rate) / (tp + 1)
            conn.execute(
                """UPDATE topic_performance
                   SET total_reach=total_reach+?, total_engagements=total_engagements+?,
                       total_posts=total_posts+1, avg_engagement_rate=?,
                       recent_engagement=?, updated_at=?
                   WHERE topic=?""",
                (max(0, reach), max(0, engagements), new_avg, engagement_rate,
                 datetime.now(timezone.utc).isoformat(), topic),
            )
        else:
            conn.execute(
                """INSERT INTO topic_performance
                   (topic, total_reach, total_engagements, total_posts,
                    avg_engagement_rate, recent_engagement, updated_at)
                   VALUES (?, ?, ?, 1, ?, ?, ?)""",
                (topic, max(0, reach), max(0, engagements),
                 engagement_rate, engagement_rate,
                 datetime.now(timezone.utc).isoformat()),
            )

    def _mark_briefs_for_topic(
        self,
        conn: sqlite3.Connection,
        topic: str,
        calendar_id: str,
    ) -> None:
        """Link unpublished research briefs for this topic to the calendar_id."""
        briefs = conn.execute(
            """SELECT id FROM research_briefs
               WHERE topic=? AND was_published=0
               ORDER BY generated_at DESC LIMIT 3""",
            (topic,),
        ).fetchall()
        now = datetime.now(timezone.utc).isoformat()
        for b in briefs:
            conn.execute(
                "UPDATE research_briefs SET was_published=1, calendar_id=?, updated_at=? WHERE id=?",
                (calendar_id, now, b["id"]),
            )

    def _maybe_auto_learn(self, conn: sqlite3.Connection) -> None:
        """Lightweight auto-learning trigger.

        Runs at most once per hour. Checks if enough brief feedback
        data exists, then fires a learning cycle via the scheduler.
        """
        # Check if a learning run happened in the last hour
        last_run = conn.execute(
            "SELECT executed_at FROM learning_runs ORDER BY executed_at DESC LIMIT 1"
        ).fetchone()
        if last_run:
            try:
                from datetime import datetime
                last_dt = datetime.fromisoformat(last_run["executed_at"])
                if (datetime.now(timezone.utc) - last_dt).total_seconds() < 3600:
                    return  # within cooldown
            except (ValueError, TypeError):
                pass

        # Check minimum data threshold
        brief_count = conn.execute(
            "SELECT COUNT(*) as c FROM research_briefs WHERE was_published=1"
        ).fetchone()["c"]
        if brief_count < 5:
            return

        # Fire learning in background (non-blocking)
        try:
            from fanpage_agent.tools.research.learning_optimizer import (
                ConfidenceCalibrator,
                WeightOptimizer,
            )
            optimizer = WeightOptimizer(self)
            optimizer.run()
            calibrator = ConfidenceCalibrator(self)
            calibrator.run()
            logger.info("Auto-learning: weights + calibration updated (%d published briefs)", brief_count)
        except Exception as exc:
            logger.warning("Auto-learning trigger failed: %s", exc)

    # ── Metrics query helpers ────────────────────────────────────

    def metrics_backlog(self) -> list[dict[str, str]]:
        """Calendar items published but not yet having real metrics."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT calendar_id, published_at, topic, date
                   FROM calendar
                   WHERE status='published' AND reach = 0
                   ORDER BY published_at ASC LIMIT 50"""
            ).fetchall()
        return [dict(r) for r in rows]

    def metrics_count(self, since_days: int | None = None) -> int:
        with self._conn() as conn:
            if since_days:
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM post_metrics WHERE published_at >= datetime('now', ?)",
                    (f"-{since_days} days",),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM post_metrics"
                ).fetchone()
        return row["c"] if row else 0

    # ═══════════════════════════════════════════════════════════════
    # Triage
    # ═══════════════════════════════════════════════════════════════

    def list_triage_items(
        self,
        status: str | None = None,
        priority: str | None = None,
        assigned_to: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if priority:
            conditions.append("priority = ?")
            params.append(priority)
        if assigned_to:
            conditions.append("assigned_to = ?")
            params.append(assigned_to)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        limit_clause = f" LIMIT {limit}" if limit else ""
        sql = f"SELECT * FROM triage_items{where} ORDER BY created_at DESC{limit_clause}"

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def upsert_triage_items(
        self, brand_id: str, items: list[CommunityTriageItem],
    ) -> list[dict[str, str]]:
        now = datetime.now(timezone.utc).isoformat()
        persisted: list[dict[str, str]] = []
        with self._conn() as conn:
            for item in items:
                existing = conn.execute(
                    "SELECT * FROM triage_items WHERE triage_id=?",
                    (item.triage_id,),
                ).fetchone()
                status = existing["status"] if existing and existing["status"] not in ("", None) else "new"
                conn.execute(
                    """INSERT OR REPLACE INTO triage_items
                       (triage_id, brand_id, created_at, source, message, category,
                        priority, recommended_action, draft_reply,
                        escalation_required, requires_human_approval, matched_rules,
                        status, assigned_to, approved_by, rejected_reason,
                        reply_sent_at, reply_permalink, resolved_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item.triage_id, brand_id, item.created_at,
                        item.source, item.message, item.category,
                        item.priority, item.recommended_action, item.draft_reply,
                        1 if item.escalation_required else 0,
                        1 if item.requires_human_approval else 0,
                        "|".join(item.matched_rules),
                        status, "", "", "", "", "", "", now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM triage_items WHERE triage_id=?",
                    (item.triage_id,),
                ).fetchone()
                persisted.append(dict(row))
        return persisted

    def approve_triage_reply(
        self, triage_id: str, approved_by: str, approved_at: str,
        assigned_to: str = "",
    ) -> dict[str, str]:
        return self._update_triage_status(
            triage_id, approved_at, status="approved", approved_by=approved_by,
            assigned_to=assigned_to,
        )

    def reject_triage_reply(
        self, triage_id: str, reason: str, rejected_at: str,
        assigned_to: str = "",
    ) -> dict[str, str]:
        with self._conn() as conn:
            conn.execute(
                """UPDATE triage_items SET status='needs_revision',
                   rejected_reason=?, updated_at=?
                   WHERE triage_id=?""",
                (reason, rejected_at, triage_id),
            )
            if assigned_to:
                conn.execute(
                    "UPDATE triage_items SET assigned_to=? WHERE triage_id=?",
                    (assigned_to, triage_id),
                )
            row = conn.execute(
                "SELECT * FROM triage_items WHERE triage_id=?", (triage_id,)
            ).fetchone()
        return dict(row) if row else {}

    def resolve_triage_item(
        self, triage_id: str, resolved_at: str, assigned_to: str = "",
    ) -> dict[str, str]:
        return self._update_triage_status(
            triage_id, resolved_at, status="resolved",
            resolved_at=resolved_at, assigned_to=assigned_to,
        )

    def mark_triage_reply_sent(
        self, triage_id: str, sent_at: str, reply_permalink: str,
        assigned_to: str = "",
    ) -> dict[str, str]:
        return self._update_triage_status(
            triage_id, sent_at, status="replied",
            reply_sent_at=sent_at, reply_permalink=reply_permalink,
            assigned_to=assigned_to,
        )

    def reopen_triage_item(
        self, triage_id: str, reopened_at: str, assigned_to: str = "",
    ) -> dict[str, str]:
        return self._update_triage_status(
            triage_id, reopened_at, status="reopened",
            resolved_at="", assigned_to=assigned_to,
        )

    def _update_triage_status(
        self, triage_id, updated_at, status=None, **extra,
    ) -> dict[str, str]:
        sets = ["updated_at=?"]
        params: list[Any] = [updated_at]
        for key, val in extra.items():
            if val is not None:
                sets.append(f"{key}=?")
                params.append(val)
        if status:
            sets.insert(0, "status=?")
            params.insert(0, status)
        params.append(triage_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE triage_items SET {', '.join(sets)} WHERE triage_id=?",
                params,
            )
            row = conn.execute(
                "SELECT * FROM triage_items WHERE triage_id=?", (triage_id,)
            ).fetchone()
        return dict(row) if row else {}

    # ═══════════════════════════════════════════════════════════════
    # Hashtag usage
    # ═══════════════════════════════════════════════════════════════

    def record_hashtag_usage(
        self,
        calendar_id: str,
        brand_id: str,
        hashtags: list[str],
        topic: str = "",
        reach: int = 0,
        engagements: int = 0,
        recorded_at: str | None = None,
    ) -> dict[str, str]:
        now = recorded_at or datetime.now(timezone.utc).isoformat()
        row = {
            "calendar_id": calendar_id,
            "brand_id": brand_id,
            "topic": topic,
            "hashtags": " ".join(hashtags),
            "reach": reach,
            "engagements": engagements,
            "recorded_at": now,
        }
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO hashtag_usage
                   (calendar_id, brand_id, topic, hashtags, reach, engagements, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (calendar_id, brand_id, topic, row["hashtags"], reach, engagements, now),
            )
        return row

    # ═══════════════════════════════════════════════════════════════
    # Topic performance (replaces TopicPerformanceStore)
    # ═══════════════════════════════════════════════════════════════

    def get_topic_boost(self, topic: str, default: float = 0.0) -> float:
        """Boost factor (0-0.15) if topic has performed well before."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM topic_performance WHERE topic=?", (topic,)
            ).fetchone()
        if not row:
            return default
        # Same scoring as TopicPerformanceRecord.score
        avg_reach = row["total_reach"] / max(1, row["total_posts"])
        reach_score = min(1.0, avg_reach / 2000.0)
        engagement_score = min(1.0, row["avg_engagement_rate"] / 0.08)
        recency_bonus = min(0.1, row["recent_engagement"] * 0.02)
        score = max(0.0, min(1.0,
            reach_score * 0.45 + engagement_score * 0.35 + recency_bonus))
        return min(0.15, score * 0.15)

    def get_top_topics(self, limit: int = 5, min_score: float = 0.3) -> list[str]:
        """Topics with highest performance score."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM topic_performance ORDER BY total_reach DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r["topic"] for r in rows]

    def record_topic_published(
        self,
        topic: str,
        reach: int,
        engagements: int,
        engagement_rate: float,
    ) -> None:
        """Record/aggregate topic performance (called from Analyst)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM topic_performance WHERE topic=?", (topic,)
            ).fetchone()
            if existing:
                tp = existing["total_posts"]
                new_avg = (
                    (existing["avg_engagement_rate"] * tp + engagement_rate) / (tp + 1)
                )
                conn.execute(
                    """UPDATE topic_performance
                       SET total_reach=total_reach+?, total_engagements=total_engagements+?,
                           total_posts=total_posts+1, avg_engagement_rate=?,
                           recent_engagement=?, updated_at=?
                       WHERE topic=?""",
                    (max(0, reach), max(0, engagements), new_avg, engagement_rate, now, topic),
                )
            else:
                conn.execute(
                    """INSERT INTO topic_performance
                       (topic, total_reach, total_engagements, total_posts,
                        avg_engagement_rate, recent_engagement, updated_at)
                       VALUES (?, ?, ?, 1, ?, ?, ?)""",
                    (topic, max(0, reach), max(0, engagements), engagement_rate, engagement_rate, now),
                )

    # ═══════════════════════════════════════════════════════════════
    # Research briefs (feedback loop)
    # ═══════════════════════════════════════════════════════════════

    def save_research_brief(
        self,
        generated_at: str,
        brand_id: str,
        topic: str,
        total_score: float,
        brand_relevance: float = 0,
        novelty: float = 0,
        content_potential: float = 0,
        source_confidence: float = 0,
        fanpage_fit: float = 0,
        customer_value: float = 0,
        risk_penalty: float = 0,
        calendar_id: str = "",
    ) -> int:
        """Save a research brief topic score for later feedback analysis."""
        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO research_briefs
                   (generated_at, brand_id, calendar_id, topic,
                    total_score, brand_relevance, novelty,
                    content_potential, source_confidence, fanpage_fit,
                    customer_value, risk_penalty)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (generated_at, brand_id, calendar_id, topic,
                 total_score, brand_relevance, novelty,
                 content_potential, source_confidence, fanpage_fit,
                 customer_value, risk_penalty),
            )
            return cursor.lastrowid or 0

    def mark_brief_published(self, brief_id: int, calendar_id: str) -> None:
        """Link a research brief to a published post."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE research_briefs SET was_published=1, calendar_id=? WHERE id=?",
                (calendar_id, brief_id),
            )

    def get_brief_feedback(
        self, since_days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get brief scores + actual performance for variance analysis."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT rb.id, rb.topic, rb.total_score as brief_score,
                          rb.brand_relevance, rb.novelty, rb.content_potential,
                          rb.source_confidence, rb.fanpage_fit, rb.customer_value,
                          pm.reach, pm.engagements,
                          (CASE WHEN pm.reach > 0
                                THEN CAST(pm.engagements AS REAL) / pm.reach
                                ELSE 0 END) as actual_engagement_rate,
                          rb.generated_at
                   FROM research_briefs rb
                   LEFT JOIN calendar c ON c.calendar_id = rb.calendar_id
                   LEFT JOIN post_metrics pm ON pm.published_at = c.published_at
                   WHERE rb.was_published = 1
                     AND rb.generated_at >= datetime('now', ?)
                   ORDER BY rb.generated_at DESC""",
                (f"-{since_days} days",),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_variance_summary(self) -> dict[str, float]:
        """Summary: average variance (brief_score vs actual performance)."""
        briefs = self.get_brief_feedback(since_days=90)
        if not briefs:
            return {"avg_variance": 0, "sample_count": 0}
        variances = []
        for b in briefs:
            eng = b.get("engagements", 0)
            if eng is not None and eng > 0:
                actual = min(1.0, eng / 50.0)  # normalize
                variances.append(actual - b["brief_score"])
        if not variances:
            return {"avg_variance": 0, "sample_count": len(briefs)}
        return {
            "avg_variance": round(sum(variances) / len(variances), 4),
            "sample_count": len(variances),
        }

    # ═══════════════════════════════════════════════════════════════
    # Learned weights (dynamic tuning)
    # ═══════════════════════════════════════════════════════════════

    def get_weights(self) -> dict[str, float]:
        """Current scoring weights."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM learned_weights").fetchall()
        return {r["weight_name"]: r["current_weight"] for r in rows}

    def update_weight(
        self, weight_name: str, new_weight: float,
        correlation_7d: float | None = None,
        correlation_30d: float | None = None,
    ) -> None:
        """Update a single weight (optionally with correlation data)."""
        with self._conn() as conn:
            sets = ["current_weight=?", "updated_at=?"]
            params: list[Any] = [new_weight, datetime.now(timezone.utc).isoformat()]
            if correlation_7d is not None:
                sets.append("correlation_7d=?")
                params.append(correlation_7d)
            if correlation_30d is not None:
                sets.append("correlation_30d=?")
                params.append(correlation_30d)
            params.append(weight_name)
            conn.execute(
                f"UPDATE learned_weights SET {', '.join(sets)} WHERE weight_name=?",
                params,
            )

    def get_weight_variance_analysis(self) -> list[dict[str, Any]]:
        """Analyze which weights need tuning based on actual performance."""
        briefs = self.get_brief_feedback(since_days=30)
        if not briefs or len(briefs) < 3:
            return []

        weights = self.get_weights()
        result = []
        for weight_name in [
            "brand_relevance", "novelty", "content_potential",
            "source_confidence", "fanpage_fit", "customer_value",
        ]:
            # Simple correlation: does this sub-score predict performance?
            scores = []
            actuals = []
            for b in briefs:
                sub = b.get(weight_name, 0)
                act = b.get("engagements")
                if act is None or act <= 0:
                    continue
                if sub > 0 and act > 0:
                    scores.append(sub)
                    actuals.append(act)
            if len(scores) < 3:
                continue
            # Pearson-like correlation
            n = len(scores)
            mean_s = sum(scores) / n
            mean_a = sum(actuals) / n
            num = sum((s - mean_s) * (a - mean_a) for s, a in zip(scores, actuals))
            den = (
                sum((s - mean_s) ** 2 for s in scores) ** 0.5
                * sum((a - mean_a) ** 2 for a in actuals) ** 0.5
            )
            corr = round(num / den, 4) if den > 0 else 0
            current_w = weights.get(weight_name, 0.15)
            result.append({
                "weight_name": weight_name,
                "current_weight": current_w,
                "correlation": corr,
                "sample_size": n,
                "suggested_adjustment": (
                    "increase" if corr > 0.3 else
                    "decrease" if corr < -0.1 else
                    "stable"
                ),
            })
        return sorted(result, key=lambda x: abs(x["correlation"]), reverse=True)

    # ═══════════════════════════════════════════════════════════════
    # Learning runs (self-learning audit)
    # ═══════════════════════════════════════════════════════════════

    def log_learning_run(self, run_type: str, summary: dict[str, Any]) -> int:
        """Record a learning run for audit."""
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO learning_runs (run_type, summary) VALUES (?, ?)",
                (run_type, json.dumps(summary, ensure_ascii=False)),
            )
            return cursor.lastrowid or 0

    def get_learning_runs(
        self, run_type: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent learning run history."""
        with self._conn() as conn:
            if run_type:
                rows = conn.execute(
                    "SELECT * FROM learning_runs WHERE run_type=? ORDER BY executed_at DESC LIMIT ?",
                    (run_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM learning_runs ORDER BY executed_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        result = []
        for r in rows:
            entry = dict(r)
            try:
                entry["summary"] = json.loads(entry["summary"])
            except (json.JSONDecodeError, TypeError):
                pass
            result.append(entry)
        return result

    # ═══════════════════════════════════════════════════════════════
    # Topic performance (for DecayModel)
    # ═══════════════════════════════════════════════════════════════

    def get_topic_performance(self) -> list[dict[str, Any]]:
        """Return all topic_performance records."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM topic_performance").fetchall()
        return [dict(r) for r in rows]

    def update_topic_performance_decay(
        self, topic: str, new_avg_rate: float, decay_factor: float,
    ) -> None:
        """Apply time-decay to a topic's engagement rate."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE topic_performance SET avg_engagement_rate=? WHERE topic=?",
                (new_avg_rate, topic),
            )

    # ═══════════════════════════════════════════════════════════════
    # Export utilities
    # ═══════════════════════════════════════════════════════════════

    def export_csv(self, table: str) -> str:
        """Export a table to CSV string."""
        with self._conn() as conn:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                return ""
            headers = list(rows[0].keys())
            buf = StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            for r in rows:
                writer.writerow([r[h] for h in headers])
            return buf.getvalue()

    def close(self) -> None:
        """No-op for interface compatibility with backends that need cleanup."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
