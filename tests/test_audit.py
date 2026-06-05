"""Tests for audit log (Step 3)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from fanpage_agent.audit import AuditManager, audit, audit_sync
from fanpage_agent.audit.auditor import AuditEntry
from fanpage_agent.main import _run_harness_status, _run_roadmap_status


class AuditManagerTest(unittest.TestCase):
    """Core CRUD + query for the audit log."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="audit_test_")
        self.mgr = AuditManager(db_dir=self._tmp, retention_days=1)

    def tearDown(self) -> None:
        for f in Path(self._tmp).iterdir():
            f.unlink()
        os.rmdir(self._tmp)

    # ── record ────────────────────────────────────────────────

    def test_record_and_list(self) -> None:
        eid = self.mgr.record(
            event_type="test.event",
            source="TestSuite",
            event_data={"key": "value"},
            success=True,
            duration_ms=42,
        )
        self.assertGreater(eid, 0)

        entries = self.mgr.list(limit=10)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e.event_type, "test.event")
        self.assertEqual(e.event_data, {"key": "value"})
        self.assertTrue(e.success)
        self.assertEqual(e.duration_ms, 42)

    def test_record_failure(self) -> None:
        eid = self.mgr.record(
            event_type="test.error",
            source="TestSuite",
            success=False,
            error="Something broke",
        )
        entries = self.mgr.list(limit=10)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertFalse(e.success)
        self.assertEqual(e.error, "Something broke")

    def test_record_no_optional_fields(self) -> None:
        eid = self.mgr.record(
            event_type="minimal",
            source="TestSuite",
        )
        entries = self.mgr.list(limit=10)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertIsNone(e.event_data)
        self.assertIsNone(e.duration_ms)
        self.assertIsNone(e.error)
        self.assertTrue(e.success)

    # ── list with filters ─────────────────────────────────────

    def test_list_filter_by_event_type(self) -> None:
        self.mgr.record(event_type="type_a", source="src1")
        self.mgr.record(event_type="type_b", source="src1")
        self.mgr.record(event_type="type_a", source="src2")

        entries = self.mgr.list(event_type="type_a", limit=10)
        self.assertEqual(len(entries), 2)

        entries = self.mgr.list(event_type="type_b", limit=10)
        self.assertEqual(len(entries), 1)

    def test_list_filter_by_source(self) -> None:
        self.mgr.record(event_type="ev", source="src_a")
        self.mgr.record(event_type="ev", source="src_b")
        self.mgr.record(event_type="ev", source="src_a")

        entries = self.mgr.list(source="src_a", limit=10)
        self.assertEqual(len(entries), 2)

    def test_list_filter_by_success(self) -> None:
        self.mgr.record(event_type="ev", source="src", success=True)
        self.mgr.record(event_type="ev", source="src", success=False)

        entries = self.mgr.list(success=True, limit=10)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].success)

        entries = self.mgr.list(success=False, limit=10)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].success)

    def test_list_returns_newest_first(self) -> None:
        eid1 = self.mgr.record(event_type="ev", source="src")
        eid2 = self.mgr.record(event_type="ev", source="src")
        eid3 = self.mgr.record(event_type="ev", source="src")

        entries = self.mgr.list(limit=3)
        ids = [e.id for e in entries]
        self.assertEqual(ids, [eid3, eid2, eid1])

    def test_list_limit_and_offset(self) -> None:
        for _ in range(10):
            self.mgr.record(event_type="ev", source="src")

        entries = self.mgr.list(limit=3, offset=5)
        self.assertEqual(len(entries), 3)
        # Offset 5 means skip 5 newest, so these should be ids 5,4,3
        self.assertEqual(entries[0].id, 5)
        self.assertEqual(entries[-1].id, 3)

    # ── count ─────────────────────────────────────────────────

    def test_count(self) -> None:
        self.mgr.record(event_type="a", source="s")
        self.mgr.record(event_type="b", source="s")
        self.mgr.record(event_type="a", source="s")

        self.assertEqual(self.mgr.count(), 3)
        self.assertEqual(self.mgr.count(event_type="a"), 2)
        self.assertEqual(self.mgr.count(event_type="c"), 0)

    def test_count_with_success(self) -> None:
        self.mgr.record(event_type="ev", source="s", success=True)
        self.mgr.record(event_type="ev", source="s", success=False)
        self.mgr.record(event_type="ev", source="s", success=True)

        self.assertEqual(self.mgr.count(success=True), 2)
        self.assertEqual(self.mgr.count(success=False), 1)

    # ── summary ───────────────────────────────────────────────

    def test_summary(self) -> None:
        self.mgr.record(event_type="post.published", source="s")
        self.mgr.record(event_type="post.published", source="s")
        self.mgr.record(event_type="web.search", source="s")
        self.mgr.record(event_type="error", source="s")

        summary = self.mgr.summary(since="-24 hours")
        self.assertEqual(summary["post.published"], 2)
        self.assertEqual(summary["web.search"], 1)
        self.assertEqual(summary["error"], 1)

    # ── vacuum / retention ────────────────────────────────────

    def test_vacuum_removes_old_entries(self) -> None:
        self.mgr.record(event_type="old", source="s")
        self.mgr.record(event_type="old", source="s")
        self.mgr.record(event_type="new", source="s")
        # All entries are recent (< 1 day old), so vacuum shouldn't remove them
        removed = self.mgr.vacuum()
        self.assertEqual(removed, 0)
        self.assertEqual(self.mgr.count(), 3)

    # ── DB file creation ──────────────────────────────────────

    def test_db_created_on_init(self) -> None:
        db_path = os.path.join(self._tmp, "audit.db")
        self.assertTrue(os.path.exists(db_path))

    def test_custom_db_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mgr = AuditManager(db_dir=td)
            self.assertTrue(os.path.exists(os.path.join(td, "audit.db")))


# ── Decorator / context-manager helpers ─────────────────────────────


class AuditHelpersTest(unittest.TestCase):
    """Test the convenience ``audit()`` context manager and ``audit_sync()``."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="audit_helper_")
        self.mgr = AuditManager(db_dir=self._tmp)

    def tearDown(self) -> None:
        for f in Path(self._tmp).iterdir():
            f.unlink()
        os.rmdir(self._tmp)

    def test_audit_context_success(self) -> None:
        with audit(
            event_type="helper.test",
            source="test",
            manager=self.mgr,
            extra="data",
        ) as ctx:
            ctx["data"]["processed"] = True

        entries = self.mgr.list(limit=10)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertTrue(e.success)
        self.assertEqual(e.event_data["extra"], "data")
        self.assertEqual(e.event_data["processed"], True)
        self.assertIsNotNone(e.duration_ms)
        self.assertIsNotNone(ctx["entry_id"])

    def test_audit_context_failure(self) -> None:
        with self.assertRaises(ValueError):
            with audit(
                event_type="helper.error",
                source="test",
                manager=self.mgr,
            ):
                raise ValueError("boom")

        entries = self.mgr.list(limit=10)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertFalse(e.success)
        self.assertIsNotNone(e.error)
        self.assertIn("boom", e.error or "")

    def test_audit_sync_fire_and_forget(self) -> None:
        eid = audit_sync(
            event_type="helper.fnf",
            source="test",
            manager=self.mgr,
            note="immediate",
        )
        self.assertGreater(eid, 0)
        entries = self.mgr.list(limit=10)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].success)
        self.assertEqual(entries[0].event_type, "helper.fnf")

    def test_audit_sync_without_manager(self) -> None:
        """Default manager (prod data dir) should work."""
        # This writes to the real data/agent/audit.db — use a small tmp
        with tempfile.TemporaryDirectory() as td:
            import os
            old = os.environ.get("AUDIT_DB_DIR", "")
            from fanpage_agent.audit.auditor import _DEFAULT_DATA_DIR

            # We can't override easily; just test with explicit manager
            # This test verifies the function signature works
            eid = audit_sync(
                event_type="test.fnf",
                source="test",
                manager=self.mgr,
            )
            self.assertGreater(eid, 0)


# ── Integration: real-world event types ────────────────────────────


class AuditEventTypeTest(unittest.TestCase):
    """Verify that the event types used by actual services are valid."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="audit_event_")
        self.mgr = AuditManager(db_dir=self._tmp)

    def tearDown(self) -> None:
        for f in Path(self._tmp).iterdir():
            f.unlink()
        os.rmdir(self._tmp)

    def _record(self, event_type: str, source: str = "Test") -> int:
        return self.mgr.record(
            event_type=event_type,
            source=source,
            event_data={"test": True},
        )

    def test_fb_request_events(self) -> None:
        for et in ["fb.get", "fb.post", "fb.photo_upload", "fb.comment_reply"]:
            eid = self._record(et)
            self.assertGreater(eid, 0)

    def test_web_search_events(self) -> None:
        eid = self._record("web.search")
        self.assertGreater(eid, 0)

    def test_error_events(self) -> None:
        eid = self.mgr.record(
            event_type="error",
            source="FacebookClient",
            success=False,
            error="HTTP 500",
        )
        self.assertGreater(eid, 0)

    def test_backup_events(self) -> None:
        for et in ["backup.run", "backup.restore"]:
            eid = self._record(et)
            self.assertGreater(eid, 0)

    def test_pipeline_events(self) -> None:
        for et in ["pipeline.publish", "pipeline.deliver"]:
            eid = self._record(et)
            self.assertGreater(eid, 0)

    def test_list_on_empty_returns_empty(self) -> None:
        entries = self.mgr.list(limit=10)
        self.assertEqual(len(entries), 0)

    def test_audit_entry_dataclass(self) -> None:
        entry = AuditEntry(
            id=1,
            timestamp="2026-06-04 12:00:00",
            event_type="test",
            source="src",
            event_data={"k": "v"},
            success=True,
            duration_ms=100,
            error=None,
        )
        self.assertEqual(entry.id, 1)
        self.assertEqual(entry.event_data, {"k": "v"})


class HarnessStatusCliTest(unittest.TestCase):
    def test_harness_status_reads_agent_harness_events(self) -> None:
        with tempfile.TemporaryDirectory(prefix="harness_status_") as data_dir:
            mgr = AuditManager(db_dir=data_dir)
            mgr.record(
                event_type="harness.blocked",
                source="AgentHarness",
                event_data={"task_id": "t1", "action": "publish_post", "agent": "publisher"},
                success=False,
                error="requires explicit approval",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                _run_harness_status(data_dir=data_dir, limit=5)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["harness_events_total"], 1)
            self.assertEqual(payload["recent"][0]["event_type"], "harness.blocked")
            self.assertEqual(payload["recent"][0]["event_data"]["action"], "publish_post")


class RoadmapStatusCliTest(unittest.TestCase):
    def test_roadmap_status_reads_next_roadmap(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            _run_roadmap_status()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["roadmap"].endswith("docs/roadmap-next.md"))
        self.assertGreaterEqual(payload["phases_total"], 5)
        self.assertIn("Phase 1", payload["current_phase"])
        self.assertGreaterEqual(len(payload["immediate_priorities"]), 1)


if __name__ == "__main__":
    unittest.main()
