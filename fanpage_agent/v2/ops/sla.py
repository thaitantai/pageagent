"""SLA dashboard — aggregates health metrics from audit log, backup, and ops.

Provides a compact snapshot suitable for Telegram delivery.
"""

from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fanpage_agent.v2.audit import AuditManager
from fanpage_agent.v2.memory.performance import PerformanceMemory

logger = logging.getLogger(__name__)


@dataclass
class SlaSnapshot:
    """Compact health snapshot."""

    # Audit
    audit_entries_24h: int = 0
    audit_errors_24h: int = 0
    audit_error_rate_pct: float = 0.0
    audit_entries_7d: int = 0

    # Backup
    last_backup_age_hours: float | None = None
    backup_retention: int = 7
    backup_dir_count: int = 0

    # DB
    db_path: str = ""
    db_size_mb: float = 0.0
    db_integrity_ok: bool = True
    db_integrity_errors: list[str] = field(default_factory=list)

    # Rate limit awareness
    fb_throttle_capacity: int = 180
    fb_throttle_available: float | None = None

    # Timeline
    sampled_at: str = ""
    uptime_hours: float = 0.0


class SlaDashboard:
    """Aggregates health data from audit log, backup system, and memory DB."""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        audit: AuditManager | None = None,
        memory: PerformanceMemory | None = None,
        fb_throttle_capacity: int = 180,
    ) -> None:
        self._data_dir = Path(data_dir) if data_dir else self._default_data_dir()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._audit = audit or AuditManager(db_dir=str(self._data_dir))
        self._memory = memory or PerformanceMemory(self._data_dir / "memory.db")
        self._fb_throttle_capacity = fb_throttle_capacity

    @staticmethod
    def _default_data_dir() -> Path:
        """Resolve default data dir from package location."""
        pkg = Path(__file__).resolve().parent.parent.parent  # fanpage_agent/v2/
        return pkg / "data" / "v2"

    # ── snapshot builder ──────────────────────────────────────────

    def snapshot(self, now: datetime.datetime | None = None) -> SlaSnapshot:
        """Build a compact health snapshot."""
        ref = now or datetime.datetime.now(datetime.timezone.utc)
        s = SlaSnapshot(sampled_at=ref.isoformat())

        # ── Audit log ────────────────────────────────────────────
        try:
            day_ago = ref - datetime.timedelta(hours=24)
            week_ago = ref - datetime.timedelta(days=7)

            all_24 = self._audit.list(since=day_ago.isoformat())
            all_7d = self._audit.list(since=week_ago.isoformat())

            s.audit_entries_24h = len(all_24)
            s.audit_entries_7d = len(all_7d)
            s.audit_errors_24h = sum(1 for e in all_24 if not e.success)
            if s.audit_entries_24h > 0:
                s.audit_error_rate_pct = round(
                    (s.audit_errors_24h / s.audit_entries_24h) * 100, 1
                )
        except Exception as exc:
            logger.warning("SLA: audit query failed: %s", exc)

        # ── Backup ───────────────────────────────────────────────
        try:
            bk_dir = self._data_dir / "backups"
            if bk_dir.exists():
                backups = sorted(bk_dir.iterdir(), key=os.path.getmtime, reverse=True)
                s.backup_dir_count = len(backups)
                if backups:
                    last_mtime = os.path.getmtime(backups[0])
                    age_sec = ref.timestamp() - last_mtime
                    s.last_backup_age_hours = round(max(age_sec, 0) / 3600, 1)
            # Retention info from memory
            s.backup_retention = 7
        except Exception as exc:
            logger.warning("SLA: backup query failed: %s", exc)

        # ── DB ───────────────────────────────────────────────────
        try:
            s.db_path = str(self._memory.db_path)
            if self._memory.db_path.exists():
                s.db_size_mb = round(self._memory.db_path.stat().st_size / (1024 * 1024), 2)
            try:
                errs = self._memory.integrity_check()
                s.db_integrity_ok = len(errs) == 0
                s.db_integrity_errors = errs
            except Exception:
                pass
        except Exception as exc:
            logger.warning("SLA: DB info failed: %s", exc)

        # ── Throttle state ───────────────────────────────────────
        try:
            from fanpage_agent.adapters.facebook_client import (
                FacebookClient,
            )

            # We can't easily introspect a running FB client's token bucket,
            # but we report the configured capacity
            s.fb_throttle_capacity = getattr(
                FacebookClient, "_DEFAULT_RATE_LIMIT", 180
            )
        except Exception:
            pass

        # Uptime — not tracked yet, skip
        pass

        return s

    # ── compact text (Telegram-friendly) ──────────────────────────

    def to_text(self, snap: SlaSnapshot | None = None) -> str:
        """Render SLA snapshot as compact Telegram text."""
        s = snap or self.snapshot()

        lines = ["📊 **SLA Dashboard**"]
        lines.append(f"🕐 {s.sampled_at[:19]}")

        # Health badge
        badges = []
        if s.audit_error_rate_pct <= 5:
            badges.append("✅ Audit OK")
        elif s.audit_error_rate_pct <= 15:
            badges.append("⚠️ Audit elevated errors")
        else:
            badges.append("🔴 Audit critical")
        if s.last_backup_age_hours is not None and s.last_backup_age_hours <= 8:
            badges.append("✅ Backup fresh")
        elif s.last_backup_age_hours is not None and s.last_backup_age_hours <= 24:
            badges.append("⚠️ Backup stale")
        elif s.last_backup_age_hours is not None:
            badges.append("🔴 Backup old")
        else:
            badges.append("⚠️ No backup data")
        badges.append("✅ DB OK" if s.db_integrity_ok else "🔴 DB issues")
        lines.append(" | ".join(badges))

        lines.append("")
        lines.append("📈 **Audit**")
        lines.append(f"• 24h: {s.audit_entries_24h} events ({s.audit_errors_24h} errors, {s.audit_error_rate_pct}%)")
        lines.append(f"• 7d:  {s.audit_entries_7d} events")

        lines.append("")
        lines.append("💾 **Backup & DB**")
        age_str = f"{s.last_backup_age_hours}h" if s.last_backup_age_hours is not None else "N/A"
        lines.append(f"• Backup: {s.backup_dir_count} files, last {age_str} (retention {s.backup_retention})")
        lines.append(f"• DB: {s.db_size_mb}MB — {'OK' if s.db_integrity_ok else '⚠️ issues'}")

        lines.append("")
        lines.append("⏱ **Uptime**")
        lines.append(f"• {s.uptime_hours}h since last reset")

        lines.append("")
        lines.append("🔒 **Facebook throttle**")
        lines.append(f"• Capacity: {s.fb_throttle_capacity} req/h")

        return "\n".join(lines)


# ── convenience ──────────────────────────────────────────────────


def build_sla_text(data_dir: str | None = None) -> str:
    """One-shot: build and render SLA dashboard."""
    return SlaDashboard(data_dir=data_dir).to_text()
