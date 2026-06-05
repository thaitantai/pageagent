"""Tests for V2 backup, restore, and integrity check (Stage 5)."""

import shutil
import sqlite3
from pathlib import Path

import pytest

from fanpage_agent.v2.memory.performance import (
    BackupError,
    IntegrityError,
    PerformanceMemory,
)
from fanpage_agent.v2.core.types import ContentPackage, ContentVariant


# ── fixtures ────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "memory.db"


@pytest.fixture
def memory(tmp_db: Path) -> PerformanceMemory:
    return PerformanceMemory(tmp_db)


@pytest.fixture
def sample_package() -> ContentPackage:
    return ContentPackage(
        package_id="test-pkg-1",
        brand_id="test_brand",
        scheduled_date="2026-06-05",
        scheduled_time="10:00",
        variants=[
            ContentVariant(
                variant_id="v1",
                topic="Test topic",
                caption="Test caption for the post",
                pillar="education",
                format="carousel",
                hook="Did you know this?",
                cta="Share your thoughts",
                tone_tags=["informative"],
                hashtags=["#skincare", "#tips"],
            )
        ],
    )


# ── backup tests ────────────────────────────────────────────────


class TestBackup:
    def test_backup_creates_file(self, memory: PerformanceMemory, sample_package: ContentPackage):
        """Backup creates a .bak.1 file in the backups dir."""
        memory.record_publish(sample_package, "v1", reach=1000, engagements=50, permalink="https://fb.com/1")
        path = memory.backup(keep=5)
        assert path.exists()
        assert path.name.endswith(".bak.1")

    def test_backup_dir_created(self, tmp_db: Path, memory: PerformanceMemory):
        """Backup dir is auto-created on first backup."""
        raw_backup_dir = tmp_db.parent / "backups"
        assert not raw_backup_dir.exists()
        memory.backup()
        assert raw_backup_dir.exists()

    def test_backup_rotation(self, memory: PerformanceMemory, sample_package: ContentPackage):
        """Rotating should keep at most `keep` backups, removing oldest."""
        memory.record_publish(sample_package, "v1", reach=1000, engagements=50, permalink="https://fb.com/1")
        for _ in range(5):
            memory.backup(keep=3, force=True)
        backups = memory.list_backups()
        assert len(backups) <= 3

    def test_backup_flushes_wal(self, memory: PerformanceMemory):
        """Backup should flush WAL before copying (WAL checkpoint)."""
        # Write some data
        with memory._conn() as conn:
            conn.execute(
                "INSERT INTO published_posts (package_id, variant_id, brand_id, scheduled_date, topic, published_at) "
                "VALUES (?,?,?,?,?,?)",
                ("pkg-wal", "v1", "brand", "2026-06-05", "topic", "2026-06-05T10:00:00"),
            )
        # Check WAL exists
        wal_path = memory.db_path.with_suffix(".db-wal")
        if wal_path.exists():
            wal_before = wal_path.stat().st_size
        else:
            wal_before = 0

        path = memory.backup(force=True)

        # Backup should exist and be readable
        conn = sqlite3.connect(str(path))
        count = conn.execute("SELECT COUNT(*) FROM published_posts").fetchone()[0]
        conn.close()
        assert count > 0

    def test_list_backups_empty(self, memory: PerformanceMemory):
        """list_backups returns empty list when no backups exist."""
        assert memory.list_backups() == []

    def test_list_backups_after_backup(self, memory: PerformanceMemory):
        """list_backups returns metadata after a backup."""
        memory.backup(force=True)
        backups = memory.list_backups()
        assert len(backups) == 1
        b = backups[0]
        assert "index" in b
        assert "path" in b
        assert "size_bytes" in b
        assert "modified" in b


# ── restore tests ────────────────────────────────────────────────


class TestRestore:
    def test_restore_restores_data(self, memory: PerformanceMemory, sample_package: ContentPackage):
        """Data restored from backup should match original."""
        # Insert data
        memory.record_publish(sample_package, "v1", reach=1000, engagements=50, permalink="https://fb.com/1")
        memory.backup(keep=3, force=True)

        # Corrupt current DB by deleting data
        with memory._conn() as conn:
            conn.execute("DELETE FROM published_posts")
        assert memory._total_posts() == 0

        # Restore
        memory.restore(backup_idx=1)
        assert memory._total_posts() == 1

    def test_restore_invalid_index(self, memory: PerformanceMemory):
        """Restoring a non-existent backup index raises BackupError."""
        with pytest.raises(BackupError):
            memory.restore(backup_idx=99)

    def test_restore_multiple_backups(self, memory: PerformanceMemory, sample_package: ContentPackage):
        """Restore from .bak.2 should work after rotating."""
        # Backup 1
        sample_package.package_id = "pkg-a"
        memory.record_publish(sample_package, "v1", reach=100, engagements=5, permalink="https://fb.com/a")
        memory.backup(keep=3, force=True)

        # Backup 2
        sample_package.package_id = "pkg-b"
        memory.record_publish(sample_package, "v1", reach=200, engagements=10, permalink="https://fb.com/b")
        memory.backup(keep=3, force=True)

        # Restore .bak.2 → should have only pkg-a
        memory.restore(backup_idx=2)
        posts = memory.get_recent_posts(limit=10)
        pkg_ids = {p["package_id"] for p in posts}
        assert "pkg-a" in pkg_ids
        assert "pkg-b" not in pkg_ids

    def test_restore_integrity_check(self, memory: PerformanceMemory):
        """After restore, integrity should pass."""
        memory.backup(force=True)
        memory.restore(backup_idx=1)
        errors = memory.integrity_check()
        assert errors == []


# ── integrity tests ──────────────────────────────────────────────


class TestIntegrityCheck:
    def test_integrity_clean(self, memory: PerformanceMemory):
        """Fresh DB should pass integrity check."""
        errors = memory.integrity_check()
        assert errors == []

    def test_integrity_after_write(self, memory: PerformanceMemory, sample_package: ContentPackage):
        """DB after writes should pass integrity check."""
        memory.record_publish(sample_package, "v1", reach=1000, engagements=50, permalink="https://fb.com/1")
        errors = memory.integrity_check()
        assert errors == []

    def test_integrity_on_init(self, memory: PerformanceMemory):
        """_check_integrity runs on init without crashing (just logs)."""
        # Should not raise
        memory2 = PerformanceMemory(memory.db_path)
        assert memory2 is not None

    def test_integrity_corrupt_db(self, tmp_db: Path):
        """Corrupt DB should report errors (but not crash on init)."""
        tmp_db.parent.mkdir(parents=True, exist_ok=True)
        # Write garbage
        tmp_db.write_text("NOT A SQLITE DATABASE")
        mem = PerformanceMemory(tmp_db)
        errors = mem.integrity_check()
        assert len(errors) > 0


# ── CLI helper integration (smoke) ───────────────────────────────


class TestCLIIntegration:
    def test_cli_backup_all_actions(self, tmp_db: Path, sample_package: ContentPackage):
        """Simulate CLI workflow: backup → check-db → restore → check-db."""
        mem = PerformanceMemory(tmp_db)
        mem.record_publish(sample_package, "v1", reach=1000, engagements=50, permalink="https://fb.com/cli")

        # Backup
        path = mem.backup(keep=5, force=True)
        assert path.exists()

        # Integrity check
        assert mem.integrity_check() == []

        # Different DB path to verify restore
        assert mem._total_posts() == 1
        with mem._conn() as conn:
            conn.execute("DELETE FROM published_posts")
        assert mem._total_posts() == 0

        # Restore
        mem.restore(backup_idx=1)
        assert mem._total_posts() == 1
        assert mem.integrity_check() == []
