"""Performance Memory — learns from content performance and suggests improvements.

SQLite-backed store that tracks:
1. Content performance by pillar, format, hook_style, posting time
2. Patterns that correlate with high engagement
3. Recommendations for future content
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fanpage_agent.core.types import ContentPackage, PerformancePattern
from fanpage_agent.memory.backup import BackupMixin

logger = logging.getLogger(__name__)


class PerformanceMemory(BackupMixin):
    """Stores and analyses content performance over time.

    The memory learns what works (high reach/engagement) and surfaces
    actionable patterns for the strategist and writer agents.

    Usage::
        memory = PerformanceMemory(Path("data/agent/memory.db"))
        memory.record_publish(package, reach=1500, engagements=45)
        patterns = memory.get_top_patterns(limit=5)
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_backup_time: float | None = None
        try:
            self._init_db()
        except sqlite3.DatabaseError as e:
            logger.warning("DB corrupt at init: %s — will attempt recovery", e)
        self._check_integrity()

    # ── public API ──────────────────────────────────────────────

    def record_publish(
        self,
        package: ContentPackage,
        variant_id: str,
        reach: int,
        engagements: int,
        permalink: str,
        page_id: str | None = None,
    ) -> None:
        """Record a published post's performance."""
        variant = next((v for v in package.variants if v.variant_id == variant_id), None)
        if not variant:
            return

        now = datetime.now(timezone.utc).isoformat()
        engagement_rate = (engagements / max(reach, 1)) * 100
        effective_page_id = page_id or "main"

        with self._conn() as conn:
            conn.execute(
                """INSERT INTO published_posts
                (package_id, variant_id, brand_id, scheduled_date, topic, pillar,
                 format, hook, cta, tone_tags, hashtags, reach, engagements, engagement_rate,
                 permalink, published_at, page_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    package.package_id, variant_id, package.brand_id,
                    package.scheduled_date, variant.topic, variant.pillar,
                    variant.format, variant.hook, variant.cta,
                    json.dumps(variant.tone_tags, ensure_ascii=False),
                    json.dumps(variant.hashtags, ensure_ascii=False),
                    reach, engagements, round(engagement_rate, 2),
                    permalink, now, effective_page_id,
                ),
            )

            # Update pattern stats (use same connection to avoid lock)
            self._update_pattern("pillar", variant.pillar, reach, engagements, conn=conn)
            self._update_pattern("format", variant.format, reach, engagements, conn=conn)

            # Extract hook style (first 8 words)
            hook_style = " ".join(variant.hook.split()[:8])
            self._update_pattern("hook_style", hook_style, reach, engagements, conn=conn)

            # Time-based pattern
            if package.scheduled_time:
                hour = package.scheduled_time.split(":")[0]
                self._update_pattern("posting_hour", f"{hour}:00", reach, engagements, conn=conn)

            # Tone pattern
            if variant.tone_tags:
                primary_tone = variant.tone_tags[0]
                self._update_pattern("tone", primary_tone, reach, engagements, conn=conn)

    def record_metrics_update(
        self,
        package_id: str,
        variant_id: str,
        reach: int,
        engagements: int,
    ) -> None:
        """Update metrics for an already-published post (e.g., after 24h)."""
        engagement_rate = (engagements / max(reach, 1)) * 100
        with self._conn() as conn:
            conn.execute(
                """UPDATE published_posts
                SET reach=?, engagements=?, engagement_rate=?
                WHERE package_id=? AND variant_id=?""",
                (reach, engagements, round(engagement_rate, 2), package_id, variant_id),
            )

    def get_top_patterns(self, pattern_type: str | None = None, limit: int = 5) -> list[PerformancePattern]:
        """Get best-performing patterns, optionally filtered by type."""
        rows = self._query_patterns(pattern_type, order_by="avg_engagement DESC", limit=limit)
        return [self._row_to_pattern(r) for r in rows]

    def get_underperforming_patterns(self, limit: int = 3) -> list[PerformancePattern]:
        """Get patterns that need improvement."""
        rows = self._query_patterns(order_by="avg_engagement ASC", limit=limit)
        return [self._row_to_pattern(r) for r in rows]

    def get_patterns(
        self,
        pattern_type: str | None = None,
        limit: int = 50,
    ) -> list[PerformancePattern]:
        """Return learned patterns for scoring and analysis."""
        rows = self._query_patterns(pattern_type=pattern_type, limit=limit)
        return [self._row_to_pattern(r) for r in rows]

    def get_recommendations(self, limit: int = 3) -> list[str]:
        """Get actionable content recommendations based on learned patterns."""
        top = self.get_top_patterns(limit=3)
        under = self.get_underperforming_patterns(limit=2)

        recs: list[str] = []
        for p in top:
            if p.confidence > 0.3 and p.recommendation:
                recs.append(p.recommendation)
        for p in under:
            if p.confidence > 0.3:
                recs.append(
                    f"⚠️ '{p.value}' ({p.pattern_type}) underperforms "
                    f"(avg engagement: {p.avg_engagement:.1f}) — consider reducing or retesting"
                )
        return recs[:limit]

    def get_recent_posts(self, limit: int = 10, page_id: str | None = None) -> list[dict]:
        """Return recent published posts for analysis.

        Args:
            limit: Max number of posts to return.
            page_id: Optional filter — only return posts for this page.
        """
        with self._conn() as conn:
            if page_id:
                rows = conn.execute(
                    """SELECT package_id, variant_id, brand_id, scheduled_date, topic,
                              pillar, format, hook, reach, engagements, engagement_rate,
                              permalink, published_at, page_id
                       FROM published_posts
                       WHERE page_id=?
                       ORDER BY published_at DESC LIMIT ?""",
                    (page_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT package_id, variant_id, brand_id, scheduled_date, topic,
                              pillar, format, hook, reach, engagements, engagement_rate,
                              permalink, published_at, page_id
                       FROM published_posts
                       ORDER BY published_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def pillar_performance(self, page_id: str | None = None) -> list[dict]:
        """Aggregate performance by content pillar.

        Args:
            page_id: Optional filter — only aggregate posts for this page.
        """
        with self._conn() as conn:
            if page_id:
                rows = conn.execute(
                    """SELECT pillar,
                              COUNT(*) as post_count,
                              ROUND(AVG(reach), 0) as avg_reach,
                              ROUND(AVG(engagements), 1) as avg_engagement,
                              ROUND(AVG(engagement_rate), 2) as avg_engagement_rate
                       FROM published_posts
                       WHERE page_id=?
                       GROUP BY pillar
                       ORDER BY avg_engagement DESC""",
                    (page_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT pillar,
                              COUNT(*) as post_count,
                              ROUND(AVG(reach), 0) as avg_reach,
                              ROUND(AVG(engagements), 1) as avg_engagement,
                              ROUND(AVG(engagement_rate), 2) as avg_engagement_rate
                       FROM published_posts
                       GROUP BY pillar
                       ORDER BY avg_engagement DESC"""
                ).fetchall()
            return [dict(r) for r in rows]

    def format_summary(self) -> str:
        """Compact summary for Telegram reports."""
        pillars = self.pillar_performance()
        recs = self.get_recommendations(limit=3)

        lines = ["📊 *Performance Memory*"]
        lines.append(f"• Total posts tracked: {self._total_posts()}")
        lines.append("")

        if pillars:
            lines.append("*Pillar Performance:*")
            for p in pillars:
                pr = p.get("pillar", "?")
                ct = p.get("post_count", 0)
                ar = int(p.get("avg_reach", 0))
                ae = p.get("avg_engagement", 0)
                er = p.get("avg_engagement_rate", 0)
                lines.append(f"  • {pr}: {ct} posts | Ø{ar} reach | Ø{ae} eng ({er}%)")

        if recs:
            lines.append("")
            lines.append("*Recommendations:*")
            for r in recs:
                lines.append(f"  → {r}")

        return "\n".join(lines)

    # ── internals ───────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=DELETE")
        return conn

    def _init_db(self) -> None:
        try:
            with self._conn() as conn:
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS published_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id TEXT NOT NULL,
                    variant_id TEXT NOT NULL,
                    brand_id TEXT NOT NULL DEFAULT '',
                    scheduled_date TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    pillar TEXT NOT NULL DEFAULT '',
                    format TEXT NOT NULL DEFAULT '',
                    hook TEXT NOT NULL DEFAULT '',
                    cta TEXT NOT NULL DEFAULT '',
                    tone_tags TEXT NOT NULL DEFAULT '[]',
                    hashtags TEXT DEFAULT '[]',
                    reach INTEGER NOT NULL DEFAULT 0,
                    engagements INTEGER NOT NULL DEFAULT 0,
                    engagement_rate REAL NOT NULL DEFAULT 0.0,
                    permalink TEXT,
                    published_at TEXT NOT NULL,
                    page_id TEXT NOT NULL DEFAULT 'main',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS performance_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_type TEXT NOT NULL,
                    value TEXT NOT NULL,
                    total_reach INTEGER NOT NULL DEFAULT 0,
                    total_engagement INTEGER NOT NULL DEFAULT 0,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    avg_reach REAL NOT NULL DEFAULT 0.0,
                    avg_engagement REAL NOT NULL DEFAULT 0.0,
                    last_seen TEXT,
                    UNIQUE(pattern_type, value)
                );

                CREATE INDEX IF NOT EXISTS idx_posts_published_at ON published_posts(published_at DESC);
                CREATE INDEX IF NOT EXISTS idx_patterns_type ON performance_patterns(pattern_type);
                CREATE INDEX IF NOT EXISTS idx_posts_pillar ON published_posts(pillar);
                CREATE INDEX IF NOT EXISTS idx_posts_page ON published_posts(page_id);

                -- Migration: add page_id column to existing tables (if missing)
                ALTER TABLE published_posts ADD COLUMN page_id TEXT NOT NULL DEFAULT 'main';
            """)
        except sqlite3.DatabaseError as e:
            logger.warning("DB corrupt at init: %s — will attempt recovery", e)

    def _update_pattern(
        self, pattern_type: str, value: str, reach: int, engagements: int,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        executor = conn if conn else self._conn()
        context = contextlib.nullcontext(executor) if conn else executor
        with context as c:
            c.execute(
                """INSERT INTO performance_patterns
                   (pattern_type, value, total_reach, total_engagement, sample_count,
                    avg_reach, avg_engagement, last_seen)
                   VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                   ON CONFLICT(pattern_type, value) DO UPDATE SET
                      total_reach = total_reach + ?,
                      total_engagement = total_engagement + ?,
                      sample_count = sample_count + 1,
                      avg_reach = (total_reach + ?) / (sample_count + 1.0),
                      avg_engagement = (total_engagement + ?) / (sample_count + 1.0),
                      last_seen = ?
                """,
                (pattern_type, value, reach, engagements,
                 float(reach), float(engagements), now,
                 reach, engagements, reach, engagements, now),
            )

    def _query_patterns(
        self,
        pattern_type: str | None = None,
        order_by: str = "avg_engagement DESC",
        limit: int = 5,
    ) -> list[sqlite3.Row]:
        with self._conn() as conn:
            if pattern_type:
                return conn.execute(
                    f"SELECT * FROM performance_patterns WHERE pattern_type=? ORDER BY {order_by} LIMIT ?",
                    (pattern_type, limit),
                ).fetchall()
            return conn.execute(
                f"SELECT * FROM performance_patterns ORDER BY {order_by} LIMIT ?",
                (limit,),
            ).fetchall()

    def _row_to_pattern(self, row: sqlite3.Row) -> PerformancePattern:
        confidence = min(1.0, row["sample_count"] / 10.0)
        rec = self._generate_recommendation(row["pattern_type"], row["value"], row["avg_engagement"])
        return PerformancePattern(
            pattern_id=f"pat-{row['pattern_type']}-{row['id']}",
            pattern_type=row["pattern_type"],
            value=row["value"],
            avg_reach=row["avg_reach"],
            avg_engagement=row["avg_engagement"],
            sample_size=row["sample_count"],
            confidence=round(confidence, 2),
            last_seen=row["last_seen"] or "",
            recommendation=rec,
        )

    def _generate_recommendation(self, pattern_type: str, value: str, avg_engagement: float) -> str:
        if pattern_type == "pillar":
            return f"Pillar '{value}' avg {avg_engagement:.0f} eng — prioritize if high, review mix if low"
        elif pattern_type == "format":
            return f"Format '{value}' avg {avg_engagement:.0f} eng — {'ưu tiên dùng' if avg_engagement > 10 else 'cân nhắc thay đổi'} format này"
        elif pattern_type == "hook_style":
            return f"Hook style này avg {avg_engagement:.0f} eng — {'giữ pattern' if avg_engagement > 10 else 'thử hook style mới'}"
        elif pattern_type == "posting_hour":
            return f"Khung giờ {value} avg {avg_engagement:.0f} eng — {'ưu tiên đăng giờ này' if avg_engagement > 10 else 'thử khung giờ khác'}"
        elif pattern_type == "tone":
            return f"Tone '{value}' avg {avg_engagement:.0f} eng — {'giữ giọng văn' if avg_engagement > 10 else 'điều chỉnh tone'}"
        return f"Pattern '{value}' avg {avg_engagement:.0f} eng"

    def _total_posts(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) as c FROM published_posts").fetchone()["c"]
