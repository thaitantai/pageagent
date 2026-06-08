"""Backup, restore, and integrity-check logic for the memory database."""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BACKUP_PATTERN = "memory.db.bak.{idx}"
MEMORY_SNAPSHOT_DIR = "memory_snapshots"
DEFAULT_MAX_BACKUPS = 7
AUTO_BACKUP_INTERVAL = 6 * 3600  # 6 hours in seconds


class BackupError(Exception):
    """Raised when backup/restore operations fail."""


class IntegrityError(Exception):
    """Raised when DB integrity check fails."""


class BackupMixin:
    """Mixin providing backup, restore, and integrity methods for a SQLite-backed store.

    Expects the host class to expose:
        - self.db_path : Path
        - self._conn() -> sqlite3.Connection
        - self._init_db() -> None
    """

    db_path: Path
    _last_backup_time: float | None = None

    # Abstract interface that the host must provide
    def _conn(self) -> sqlite3.Connection:  # pragma: no cover
        raise NotImplementedError

    def _init_db(self) -> None:  # pragma: no cover
        raise NotImplementedError

    # ── backup directory ────────────────────────────────────────

    @property
    def backup_dir(self) -> Path:
        """Directory where memory database snapshots are stored."""
        bdir = self.db_path.parent / MEMORY_SNAPSHOT_DIR
        bdir.mkdir(parents=True, exist_ok=True)
        return bdir

    def _extract_backup_path(self, idx: int | str) -> Path:
        return self.backup_dir / BACKUP_PATTERN.format(idx=idx)

    # ── backup ──────────────────────────────────────────────────

    def backup(
        self,
        keep: int | None = None,
        force: bool = False,
    ) -> Path:
        """Create a snapshot of the current memory database.

        Args:
            keep: Number of memory snapshots to retain (default: max_backups).
            force: Skip interval check even if it's too soon.

        Returns:
            Path to the created backup file.
        """
        if keep is None:
            keep = DEFAULT_MAX_BACKUPS
        now = datetime.now(timezone.utc).timestamp()

        # Auto-backup throttle: skip if < 6h since last backup (unless forced)
        if not force and self._last_backup_time is not None:
            elapsed = now - self._last_backup_time
            if elapsed < AUTO_BACKUP_INTERVAL:
                logger.debug("Skipping auto-backup — only %.0fs since last one", elapsed)
                return self._extract_backup_path(1)

        # Flush WAL so backup is consistent
        try:
            with self._conn() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError:
            pass  # Live with whatever we have

        # Ensure backup dir exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Rotate: shift existing backups up by one index
        existing = sorted(
            self.backup_dir.glob("memory.db.bak.*"),
            key=lambda p: int(p.suffixes[-1].lstrip(".")),
        )
        for p in reversed(existing):
            current_idx = int(p.suffixes[-1].lstrip("."))
            new_idx = current_idx + 1
            # Drop if beyond keep limit
            if new_idx <= keep:
                p.rename(self._extract_backup_path(new_idx))

        # Create new .bak.1 as copy of current DB
        backup_path = self._extract_backup_path(1)
        shutil.copy2(str(self.db_path), str(backup_path))
        self._last_backup_time = now

        # Prune anything > keep
        for p in sorted(
            self.backup_dir.glob("memory.db.bak.*"),
            key=lambda fp: int(fp.suffixes[-1].lstrip(".")),
        ):
            idx = int(p.suffixes[-1].lstrip("."))
            if idx > keep:
                p.unlink()

        logger.info("Backup created: %s (retention=%d)", backup_path, keep)
        return backup_path

    # ── verify / restore ────────────────────────────────────────

    def _verify_backup(self, backup_path: Path) -> None:
        """Verify a backup file is a valid SQLite database."""
        try:
            conn = sqlite3.connect(str(backup_path))
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("SELECT COUNT(*) FROM published_posts")
            conn.close()
        except sqlite3.DatabaseError as e:
            raise BackupError(f"Backup verification failed for {backup_path}: {e}") from e

    def restore(self, backup_idx: int = 1) -> None:
        """Restore DB from a numbered backup (1 = most recent)."""
        backup_path = self._extract_backup_path(backup_idx)
        if not backup_path.exists():
            raise BackupError(
                f"Backup #{backup_idx} not found at {backup_path}. "
                f"Available: {self._list_backups()}"
            )
        # Verify backup before restoring
        self._verify_backup(backup_path)
        shutil.copy2(str(backup_path), str(self.db_path))
        # Remove stale WAL/SHM so new connection doesn't replay old WAL
        for suffix in (".db-wal", ".db-shm"):
            stale = self.db_path.with_suffix(suffix)
            if stale.exists():
                stale.unlink()
        self._init_db()
        self._check_integrity()

    # ── list backups ────────────────────────────────────────────

    def list_backups(self) -> list[dict[str, Any]]:
        """List available backups with metadata.

        Returns sorted list (newest first).
        """
        backups = self._list_backups()
        result: list[dict[str, Any]] = []
        for idx, path in backups:
            stat = path.stat()
            result.append({
                "index": idx,
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "created": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
            })
        return result

    def _list_backups(self) -> list[tuple[int, Path]]:
        """List available backups as (index, path), sorted newest first."""
        pattern = re.compile(r"memory\.db\.bak\.(\d+)$")
        backups: list[tuple[int, Path]] = []
        for p in self.backup_dir.glob("memory.db.bak.*"):
            m = pattern.match(p.name)
            if m:
                backups.append((int(m.group(1)), p))
        backups.sort(key=lambda x: x[0])  # Smallest index = newest (most recent)
        return backups

    # ── integrity ───────────────────────────────────────────────

    def integrity_check(self) -> list[str]:
        """Run PRAGMA integrity_check on the DB.

        Returns list of error messages. Empty list = healthy.
        """
        try:
            with self._conn() as conn:
                rows = conn.execute("PRAGMA integrity_check").fetchall()
                errors = [r[0] for r in rows if r[0] != "ok"]
                if errors:
                    logger.warning("Integrity check found %d issue(s): %s", len(errors), errors[:3])
                    return errors
                return []
        except sqlite3.DatabaseError as e:
            logger.error("Cannot run integrity check: %s", e)
            return [str(e)]

    def _check_integrity(self) -> None:
        """Run integrity check on init and log warnings (don't crash)."""
        errors = self.integrity_check()
        if errors:
            logger.warning("DB integrity check found %d issue(s): %s", len(errors), errors[:3])
