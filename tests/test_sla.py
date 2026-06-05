"""Tests for SLA dashboard (Step 5)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from fanpage_agent.ops.sla import SlaDashboard, SlaSnapshot, build_sla_text


class SlaDashboardTest(unittest.TestCase):
    """SlaDashboard unit tests."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="sla_test_")
        self._data_dir = Path(self._tmp)

    def _dashboard(self) -> SlaDashboard:
        return SlaDashboard(data_dir=str(self._data_dir))

    # ── snapshot construction ────────────────────────────────────

    def test_snapshot_returns_all_fields(self) -> None:
        """Snapshot contains all expected fields."""
        dash = self._dashboard()
        snap = dash.snapshot()
        self.assertIsInstance(snap, SlaSnapshot)
        self.assertIsNotNone(snap.sampled_at)
        self.assertGreaterEqual(snap.audit_entries_24h, 0)
        self.assertGreaterEqual(snap.audit_entries_7d, 0)

    def test_empty_audit_produces_zeroes(self) -> None:
        """No audit entries → zero counts, 0% error rate."""
        snap = self._dashboard().snapshot(
            now=datetime(2026, 6, 5, tzinfo=timezone.utc)
        )
        self.assertEqual(snap.audit_entries_24h, 0)
        self.assertEqual(snap.audit_errors_24h, 0)
        self.assertEqual(snap.audit_error_rate_pct, 0.0)

    def test_db_no_backup_dir_no_crash(self) -> None:
        """No backups directory shouldn't crash."""
        snap = self._dashboard().snapshot()
        self.assertEqual(snap.backup_dir_count, 0)
        self.assertIsNone(snap.last_backup_age_hours)

    def test_db_no_file_shows_zero_mb(self) -> None:
        """Dashboard creates a small DB on init — filesize reflects that but is small."""
        fresh_tmp = Path(tempfile.mkdtemp(prefix="sla_no_db_"))
        dash = SlaDashboard(data_dir=str(fresh_tmp))
        snap = dash.snapshot()
        # PerformanceMemory creates memory.db on init, so size is non-zero
        self.assertGreater(snap.db_size_mb, 0.0)
        self.assertTrue(snap.db_integrity_ok)

    # ── to_text rendering ─────────────────────────────────────────

    def test_to_text_includes_health_badges(self) -> None:
        """Text output contains health indicators."""
        text = self._dashboard().to_text()
        self.assertIn("SLA Dashboard", text)
        self.assertIn("Audit", text)
        self.assertIn("Backup", text)
        self.assertIn("DB", text)

    def test_to_text_with_mocked_audit_errors(self) -> None:
        """High error rate shows critical badge."""
        snap = SlaSnapshot(
            audit_entries_24h=100,
            audit_errors_24h=60,
            audit_error_rate_pct=60.0,
        )
        text = SlaDashboard(data_dir=self._tmp).to_text(snap)
        self.assertIn("🔴 Audit critical", text)

    def test_to_text_with_good_health(self) -> None:
        """Low error + fresh backup shows green badges."""
        snap = SlaSnapshot(
            audit_entries_24h=50,
            audit_errors_24h=1,
            audit_error_rate_pct=2.0,
            last_backup_age_hours=2.5,
            backup_dir_count=3,
            db_integrity_ok=True,
            db_size_mb=1.2,
            fb_throttle_capacity=180,
        )
        text = SlaDashboard(data_dir=self._tmp).to_text(snap)
        self.assertIn("✅ Audit OK", text)
        self.assertIn("✅ Backup fresh", text)
        self.assertIn("✅ DB OK", text)

    def test_to_text_with_stale_backup(self) -> None:
        """Old backup shows warning badge."""
        snap = SlaSnapshot(
            audit_entries_24h=10,
            last_backup_age_hours=15.0,
            backup_dir_count=1,
            db_integrity_ok=True,
        )
        text = SlaDashboard(data_dir=self._tmp).to_text(snap)
        self.assertIn("⚠️ Backup stale", text)

    def test_to_text_very_old_backup(self) -> None:
        """Very old backup shows critical badge."""
        snap = SlaSnapshot(
            audit_entries_24h=5,
            last_backup_age_hours=48.0,
            backup_dir_count=1,
            db_integrity_ok=True,
        )
        text = SlaDashboard(data_dir=self._tmp).to_text(snap)
        self.assertIn("🔴 Backup old", text)

    def test_to_text_db_integrity_failure(self) -> None:
        """DB integrity failure shows red badge."""
        snap = SlaSnapshot(
            audit_entries_24h=10,
            db_integrity_ok=False,
            db_integrity_errors=["table missing"],
        )
        text = SlaDashboard(data_dir=self._tmp).to_text(snap)
        self.assertIn("🔴 DB issues", text)

    # ── build_sla_text convenience ────────────────────────────────

    def test_build_sla_text_returns_string(self) -> None:
        """Convenience function returns non-empty string."""
        text = build_sla_text(data_dir=str(self._data_dir))
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 50)

    # ── edge cases ────────────────────────────────────────────────

    def test_audit_list_with_many_entries(self) -> None:
        """SLA can handle dash query with realistic entry count."""
        # Write some audit entries to the real audit DB
        from fanpage_agent.audit import AuditManager

        am = AuditManager(db_dir=str(self._data_dir))
        for i in range(20):
            am.record("test.event", source="sla_test", success=(i % 5 != 0))
        snap = self._dashboard().snapshot()
        # At least some entries should be within 24h
        self.assertGreaterEqual(snap.audit_entries_24h, 20)

    def test_dashboard_created_without_data_dir(self) -> None:
        """SlaDashboard with default data dir doesn't crash."""
        # Just verify instantiation works
        dash = SlaDashboard()
        self.assertIsNotNone(dash)
        snap = dash.snapshot()
        self.assertIsInstance(snap, SlaSnapshot)
        self.assertGreaterEqual(snap.audit_entries_24h, 0)


if __name__ == "__main__":
    unittest.main()
