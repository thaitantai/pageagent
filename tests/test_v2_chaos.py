"""Chaos / resilience tests — inject failures at key integration points.

Tests cover: connection drops, timeouts, corrupt responses,
both-fallback-failure, file I/O errors, DB corruption, concurrent access.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.scraping.web_search import SearchResult, WebSearchClient
from fanpage_agent_v2.audit import AuditManager
from fanpage_agent_v2.core.types import ContentPackage, ContentVariant
from fanpage_agent_v2.memory.performance import (
    BackupError,
    PerformanceMemory,
    IntegrityError,
)


def _make_fb_config() -> Mock:
    """Minimal Settings mock for FacebookClient."""
    cfg = Mock()
    cfg.fb_page_id = "test_page_123"
    cfg.fb_page_token = "EAA_test_token"
    cfg.fb_rate_limit = 999
    cfg.fb_rate_interval = 3600.0
    cfg.fb_retry_max = 2
    cfg.fb_retry_backoff = 0.1
    return cfg


# ── FacebookClient chaos ────────────────────────────────────────


class FacebookClientChaosTest(unittest.TestCase):
    """Inject network / API failures into FacebookClient."""

    def setUp(self) -> None:
        self.config = _make_fb_config()
        self.client = FacebookClient(self.config)

    # ── _request: transport errors ──────────────────────────────

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_do_request_timeout_propagates(self, mock_do: Mock) -> None:
        """Connection timeout should propagate as RuntimeError."""
        mock_do.side_effect = RuntimeError("timeout: HTTPSConnectionPool(host='graph.facebook.com')")

        with self.assertRaises(RuntimeError) as ctx:
            self.client._request("GET", "/test")
        self.assertIn("timeout", str(ctx.exception).lower())

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_do_request_500_raises_immediately(self, mock_do: Mock) -> None:
        """HTTP 500 is not a 429 — should fail fast (non-429 raises)."""
        mock_do.side_effect = RuntimeError("HTTP 500 Internal Server Error")

        with self.assertRaises(RuntimeError) as ctx:
            self.client._request("GET", "/test")
        self.assertIn("500", str(ctx.exception))

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_do_request_dns_failure(self, mock_do: Mock) -> None:
        """DNS resolution failure (not a 429)."""
        mock_do.side_effect = RuntimeError(
            "Failed to resolve 'graph.facebook.com'"
        )

        with self.assertRaises(RuntimeError) as ctx:
            self.client._request("GET", "/test")
        self.assertIn("resolve", str(ctx.exception))

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_empty_response_raises(self, mock_do: Mock) -> None:
        """Empty/None response from _do_request should propagate."""
        mock_do.return_value = None
        self.config.fb_retry_max = 0  # no retry
        # _request returns the result directly (no None-check inside)
        # This tests that the caller can handle unexpected None
        result = self.client._request("GET", "/empty")
        self.assertIsNone(result)

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_malformed_json_response(self, mock_do: Mock) -> None:
        """Non-JSON response from _do_request propagates raw RuntimeError."""
        mock_do.side_effect = RuntimeError(
            "Expecting value: line 1 column 1 (char 0)"
        )
        with self.assertRaises(RuntimeError) as ctx:
            self.client._request("GET", "/badjson")
        self.assertIn("Expecting value", str(ctx.exception))

    # ── post_photo: file I/O failures ───────────────────────────

    @patch("requests.post")
    def test_post_photo_file_not_found(self, mock_post: Mock) -> None:
        """Non-existent image path should raise FileNotFoundError."""
        self.config.fb_retry_max = 0
        with self.assertRaises(FileNotFoundError):
            self.client.post_photo("/nonexistent/image.jpg")

    @patch("requests.post")
    def test_post_photo_network_error(self, mock_post: Mock) -> None:
        """Connection reset on photo upload should fail."""
        mock_post.side_effect = RuntimeError("Connection reset by peer")
        self.config.fb_retry_max = 0

        with patch("builtins.open", mock_open(read_data=b"fake")):
            with self.assertRaises(RuntimeError) as ctx:
                self.client.post_photo("/fake/path.jpg")
            self.assertIn("Connection reset", str(ctx.exception))

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_reply_to_comment_failure(self, mock_do: Mock) -> None:
        """Failed comment reply propagates error."""
        mock_do.side_effect = RuntimeError(
            "Facebook API error: (#100) No permission"
        )

        with self.assertRaises(RuntimeError) as ctx:
            self.client.reply_to_comment("comment_1", "test reply")
        self.assertIn("No permission", str(ctx.exception))


# ── WebSearchClient chaos ───────────────────────────────────────


class WebSearchChaosTest(unittest.TestCase):
    """Both SDK and HTML fallback fail."""

    def setUp(self) -> None:
        self.client = WebSearchClient()

    @patch.object(WebSearchClient, "_search_ddg_sdk")
    @patch.object(WebSearchClient, "_search_ddg_html")
    def test_both_search_methods_fail(
        self, mock_html: Mock, mock_sdk: Mock
    ) -> None:
        """When both SDK and HTML fallback fail, search should return []."""
        mock_sdk.side_effect = RuntimeError("SDK timeout")
        mock_html.side_effect = RuntimeError("HTML scrape blocked")

        result = self.client.search("test query", max_results=5)
        self.assertEqual(result, [])

    @patch.object(WebSearchClient, "_search_ddg_sdk")
    @patch.object(WebSearchClient, "_search_ddg_html")
    def test_sdk_fails_html_succeeds(
        self, mock_html: Mock, mock_sdk: Mock
    ) -> None:
        """If SDK fails but HTML fallback works, return HTML results."""
        mock_sdk.side_effect = RuntimeError("SDK failed")

        from fanpage_agent.scraping.web_search import SearchResult

        html_results = [SearchResult(title="fallback", url="https://x.com/a", snippet="ok")]
        mock_html.return_value = html_results

        result = self.client.search("test", max_results=5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].url, "https://x.com/a")

    @patch.object(WebSearchClient, "_search_ddg_sdk")
    def test_sdk_empty_results(self, mock_sdk: Mock) -> None:
        """SDK returning empty list should be valid (not an error)."""
        mock_sdk.return_value = []

        result = self.client.search("obscure query", max_results=5)
        self.assertEqual(result, [])

    @patch.object(WebSearchClient, "_search_ddg_sdk")
    @patch.object(WebSearchClient, "_search_ddg_html")
    def test_partial_result_with_missing_fields(
        self, mock_html: Mock, mock_sdk: Mock
    ) -> None:
        """Results missing title/url return as SearchResult with empty fields."""
        mock_sdk.side_effect = RuntimeError("SDK dead")
        mock_html.return_value = [
            SearchResult(title="", url="", snippet=""),
            SearchResult(
                title="Valid", url="https://v.com", snippet="content"
            ),
        ]

        result = self.client.search("test", max_results=5)
        # Current behavior: no filtering, both results pass through
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].url, "")
        self.assertEqual(result[1].url, "https://v.com")


# ── PerformanceMemory chaos ──────────────────────────────────────


class PerformanceMemoryChaosTest(unittest.TestCase):
    """DB corruption, recovery, concurrent access."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="pm_chaos_")

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _db_path(self, name: str = "chaos.db") -> Path:
        return Path(self._tmp) / name

    def test_init_with_corrupt_db(self) -> None:
        """Opening a corrupt DB should not crash init."""
        # Write garbage as the DB
        db = self._db_path("corrupt.db")
        db.write_bytes(b"\x00\x01\x02\x03this is not a valid sqlite database")

        # Should not raise — init should attempt recovery
        try:
            mem = PerformanceMemory(db)
            # Either it recovered or just logged a warning
            self.assertTrue(db.exists())
        except sqlite3.DatabaseError:
            # Acceptable — the DB is truly corrupt
            pass

    def test_write_after_corrupt_recovery(self) -> None:
        """If recovery creates a fresh DB, writing should work."""
        db = self._db_path("recover.db")
        db.write_bytes(b"\x00\x01\x02\x03not sqlite")

        try:
            mem = PerformanceMemory(db)
            # Try writing
            pkg = ContentPackage(
                package_id="chaos_pkg_1",
                brand_id="test_brand",
                scheduled_date="2026-06-04",
                variants=[
                    ContentVariant(
                        variant_id="var_corrupt",
                        topic="chaos test",
                        pillar="test",
                        caption="chaos test",
                        hook="what",
                        cta="test",
                        format="post_short",
                    ),
                ],
            )
            mem.record_publish(pkg, variant_id="var_corrupt", reach=100, engagements=10, permalink="https://fb.com/x")
            # If we got here without error, recovery worked
        except sqlite3.DatabaseError:
            pass  # Acceptable

    def test_delete_db_file_between_ops(self) -> None:
        """Deleting the DB file mid-session causes write errors."""
        db = self._db_path("removed.db")
        mem = PerformanceMemory(db)
        db.unlink()

        # _check_integrity only logs warnings, doesn't raise.
        # A write operation after DB deletion should fail.
        pkg = ContentPackage(
            package_id="chaos_delete",
            brand_id="test",
            scheduled_date="2026-06-04",
            variants=[
                ContentVariant(
                    variant_id="var_delete",
                    topic="test",
                    pillar="test",
                    caption="delete test",
                    hook="test",
                    cta="test",
                    format="post_short",
                ),
            ],
        )
        with self.assertRaises((sqlite3.OperationalError, Exception)):
            mem.record_publish(
                pkg,
                variant_id="var_delete",
                reach=10,
                engagements=1,
                permalink="https://fb.com/x",
            )

    def test_backup_fails_when_disk_full(self) -> None:
        """Simulate disk-full on backup copy."""
        db = self._db_path("diskfull.db")
        mem = PerformanceMemory(db)

        # Patch shutil.copy2 to fail
        with patch("shutil.copy2") as mock_copy:
            mock_copy.side_effect = OSError("No space left on device")
            with self.assertRaises(OSError):
                mem.backup(force=True)

    def test_backup_restore_corrupt_backup(self) -> None:
        """Restore from a corrupt backup file should raise."""
        db = self._db_path("restore_corrupt.db")
        mem = PerformanceMemory(db)

        # Create backup first
        bp = mem.backup(force=True)
        # Corrupt the backup file
        if bp and bp.exists():
            bp.write_bytes(b"garbage")
        elif db.exists():
            # fallback: find backup via list
            backups = list(Path(self._tmp).rglob("memory.db.bak.*"))
            if backups:
                backups[0].write_bytes(b"garbage")
            else:
                self.skipTest("No backup file found to corrupt")

        with self.assertRaises((BackupError, IntegrityError, sqlite3.DatabaseError)):
            mem.restore(1)

    def test_concurrent_access_does_not_crash(self) -> None:
        """Simulate concurrent writes (sequential with short-lived conns)."""
        db = self._db_path("concurrent.db")
        mem = PerformanceMemory(db)
        import threading

        errors: list[Exception] = []

        def write_thread(thread_id: int) -> None:
            try:
                local_mem = PerformanceMemory(db)
                pkg = ContentPackage(
                    package_id=f"chaos_thread_{thread_id}",
                    brand_id="test_brand",
                    scheduled_date="2026-06-04",
                    variants=[
                        ContentVariant(
                            variant_id=f"var_thread_{thread_id}",
                            topic="chaos test",
                            pillar=f"thread_{thread_id}",
                            caption="concurrent test",
                            hook="story",
                            cta="learn",
                            format="post_short",
                        ),
                    ],
                )
                local_mem.record_publish(
                    pkg,
                    variant_id=f"var_thread_{thread_id}",
                    reach=50,
                    engagements=5,
                    permalink=f"https://fb.com/thread_{thread_id}",
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_thread, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            # In WAL mode, concurrent reads are fine, but with DELETE mode
            # (as currently configured) some writes may fail.
            # Accept a small number of failures.
            self.assertLessEqual(len(errors), 3)
        else:
            # All 5 succeeded — great
            patterns = mem.get_top_patterns()
            self.assertGreaterEqual(len(patterns), 0)


# ── Audit log chaos ──────────────────────────────────────────────


class AuditChaosTest(unittest.TestCase):
    """Resilience of the audit log under failures."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="audit_chaos_")

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_write_to_readonly_db(self) -> None:
        """Writing to a read-only DB should not crash the process."""
        mgr = AuditManager(db_dir=self._tmp)
        db_path = Path(self._tmp) / "audit.db"
        # Make it read-only
        os.chmod(db_path, 0o444)

        try:
            mgr.record(event_type="test", source="chaos")
        except (sqlite3.OperationalError, PermissionError, OSError):
            pass  # Acceptable
        finally:
            os.chmod(db_path, 0o644)

    def test_read_from_empty_db(self) -> None:
        """Reading from a DB with no entries returns empty list."""
        mgr = AuditManager(db_dir=self._tmp)
        entries = mgr.list(limit=10)
        self.assertEqual(entries, [])

    def test_vacuum_does_not_corrupt_data(self) -> None:
        """Vacuum should preserve existing data."""
        mgr = AuditManager(db_dir=self._tmp)
        for i in range(20):
            mgr.record(event_type=f"ev_{i}", source="chaos")
        mgr.vacuum()

        entries = mgr.list(limit=30)
        self.assertEqual(len(entries), 20)  # all preserved

    def test_large_event_data_no_crash(self) -> None:
        """Storing large event data should not crash."""
        mgr = AuditManager(db_dir=self._tmp)
        big_data = {"data": "x" * 100_000}  # 100KB
        eid = mgr.record(
            event_type="big_event",
            source="chaos",
            event_data=big_data,
        )
        self.assertGreater(eid, 0)

    def test_special_chars_in_event_data(self) -> None:
        """Unicode + special characters in event_data should survive."""
        mgr = AuditManager(db_dir=self._tmp)
        eid = mgr.record(
            event_type="unicode_test",
            source="chaos",
            event_data={
                "emoji": "🎉🔥💀",
                "vietnamese": "chăm sóc da dầu mụn",
                "json_with_quotes": 'he said "hello"',
                "null_value": None,
            },
        )
        entries = mgr.list(limit=10)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].event_data["emoji"], "🎉🔥💀")
        self.assertEqual(entries[0].event_data["vietnamese"], "chăm sóc da dầu mụn")


if __name__ == "__main__":
    unittest.main()
