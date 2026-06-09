#!/usr/bin/env python3
"""Tests for the Content Queue (Phase 4).

Covers:
- UnifiedStore queue methods: enqueue, list, approve, reject, publish, stats
- ContentQueueTool: enqueue_from_calendar, show_queue, approve_item, reject_item
- ContentQueueTool: batch_approve, batch_reject
- ContentQueueTool: publish_to_facebook (dry_run mode)
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fanpage_agent.adapters.sqlite_store import UnifiedStore
from fanpage_agent.tools.publishing.content_queue import (
    ContentQueueResult,
    ContentQueueTool,
)


class ContentQueueStoreTest(unittest.TestCase):
    """UnifiedStore queue methods."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_queue.db"
        self.store = UnifiedStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.store.close()

    def seed_calendar(self) -> str:
        """Insert a calendar item and return its calendar_id."""
        cal_id = "cal_test_01"
        with self.store._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO calendar
                   (calendar_id, brand_id, date, pillar, objective, topic, angle, status)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (cal_id, "test_brand", "2026-06-10", "education", "reach",
                 "skincare routine", "test_angle", "planned"),
            )
        return cal_id

    def test_enqueue_new_item(self) -> None:
        """Enqueue a new calendar item."""
        cal_id = self.seed_calendar()
        result = self.store.enqueue_calendar_item(
            calendar_id=cal_id,
            brand_id="test_brand",
            topic="skincare routine",
            pillar="education",
        )
        self.assertIn("id", result)
        self.assertEqual(result["queue_status"], "queued")
        self.assertEqual(result["calendar_id"], cal_id)

    def test_enqueue_updates_existing(self) -> None:
        """Enqueuing the same calendar_id updates in place."""
        cal_id = self.seed_calendar()
        self.store.enqueue_calendar_item(
            calendar_id=cal_id, topic="original",
        )
        result = self.store.enqueue_calendar_item(
            calendar_id=cal_id, topic="updated",
        )
        self.assertEqual(result["topic"], "updated")

    def test_list_queue_no_filters(self) -> None:
        """list_content_queue returns all items."""
        cal_id = self.seed_calendar()
        self.store.enqueue_calendar_item(calendar_id=cal_id)
        items = self.store.list_content_queue()
        self.assertGreaterEqual(len(items), 1)

    def test_list_queue_filter_status(self) -> None:
        """list_content_queue filters by status."""
        cal_id = self.seed_calendar()
        self.store.enqueue_calendar_item(calendar_id=cal_id)
        items_queued = self.store.list_content_queue(status="queued")
        items_approved = self.store.list_content_queue(status="approved")
        self.assertGreaterEqual(len(items_queued), 1)
        self.assertEqual(len(items_approved), 0)

    def test_approve_queue_item(self) -> None:
        """approve_queue_item sets status to approved."""
        cal_id = self.seed_calendar()
        self.store.enqueue_calendar_item(calendar_id=cal_id)
        result = self.store.approve_queue_item(calendar_id=cal_id, approved_by="test")
        self.assertEqual(result["queue_status"], "approved")
        self.assertEqual(result["approved_by"], "test")
        self.assertNotEqual(result["approved_at"], "")

    def test_reject_queue_item(self) -> None:
        """reject_queue_item sets status to rejected."""
        cal_id = self.seed_calendar()
        self.store.enqueue_calendar_item(calendar_id=cal_id)
        result = self.store.reject_queue_item(calendar_id=cal_id, reason="wrong tone")
        self.assertEqual(result["queue_status"], "rejected")
        self.assertEqual(result["rejected_reason"], "wrong tone")

    def test_mark_queue_item_published(self) -> None:
        """mark_queue_item_published sets status to published."""
        cal_id = self.seed_calendar()
        self.store.enqueue_calendar_item(calendar_id=cal_id)
        self.store.approve_queue_item(calendar_id=cal_id)
        result = self.store.mark_queue_item_published(
            calendar_id=cal_id, fb_post_id="123_456",
        )
        self.assertEqual(result["queue_status"], "published")
        self.assertEqual(result["fb_post_id"], "123_456")

    def test_mark_queue_item_failed(self) -> None:
        """mark_queue_item_published with error sets status to failed."""
        cal_id = self.seed_calendar()
        self.store.enqueue_calendar_item(calendar_id=cal_id)
        result = self.store.mark_queue_item_published(
            calendar_id=cal_id, fb_error="rate_limit_exceeded",
        )
        self.assertEqual(result["queue_status"], "failed")
        self.assertEqual(result["fb_error"], "rate_limit_exceeded")

    def test_get_queue_stats(self) -> None:
        """get_queue_stats returns correct counts."""
        cal_id_1 = self.seed_calendar()
        self.store.enqueue_calendar_item(calendar_id=cal_id_1)
        stats = self.store.get_queue_stats()
        self.assertGreaterEqual(stats["queued"], 1)
        self.assertIn("total", stats)
        self.assertEqual(stats["total"], stats["queued"] + stats["approved"]
                         + stats["rejected"] + stats["published"] + stats["failed"])

    def test_batch_approve_all(self) -> None:
        """batch_approve_queue approves all queued items."""
        for i in range(3):
            cal_id = f"cal_batch_{i}"
            with self.store._conn() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO calendar
                       (calendar_id, brand_id, date, pillar, topic, angle, status)
                       VALUES (?,?,?,?,?,?,?)""",
                    (cal_id, "test", "2026-06-10", "education", f"topic_{i}",
                     "angle", "planned"),
                )
            self.store.enqueue_calendar_item(calendar_id=cal_id)
        result = self.store.batch_approve_queue()
        self.assertEqual(result["approved_count"], 3)
        # Verify calendar also updated
        items = self.store.list_content_queue(status="approved")
        self.assertGreaterEqual(len(items), 3)

    def test_batch_publish_queue(self) -> None:
        """batch_publish_queue returns approved items ready for publish."""
        cal_id = self.seed_calendar()
        self.store.enqueue_calendar_item(calendar_id=cal_id)
        self.store.approve_queue_item(calendar_id=cal_id)
        items = self.store.batch_publish_queue()
        self.assertGreaterEqual(len(items), 1)
        for item in items:
            self.assertEqual(item["queue_status"], "approved")

    def test_reject_only_queued(self) -> None:
        """Reject only works on 'queued' items, not already approved."""
        cal_id = self.seed_calendar()
        self.store.enqueue_calendar_item(calendar_id=cal_id)
        self.store.approve_queue_item(calendar_id=cal_id)
        result = self.store.reject_queue_item(calendar_id=cal_id)
        # Should NOT change since it's already approved
        self.assertEqual(result["queue_status"], "approved")


class ContentQueueToolTest(unittest.TestCase):
    """ContentQueueTool — orchestrates queue lifecycle."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_queue_tool.db"
        self.store = UnifiedStore(db_path=self.db_path)
        self.tool = ContentQueueTool(store=self.store, dry_run=True)

    def tearDown(self) -> None:
        self.store.close()

    def _seed_calendar(self, cal_id: str = "cal_tool_01",
                       topic: str = "vitamin c") -> str:
        with self.store._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO calendar
                   (calendar_id, brand_id, date, pillar, objective, topic, angle, status)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (cal_id, "test", "2026-06-10", "education", "reach",
                 topic, "test", "planned"),
            )
        return cal_id

    def test_enqueue_from_calendar(self) -> None:
        """enqueue_from_calendar reads calendar and creates queue entry."""
        cal_id = self._seed_calendar()
        result = self.tool.enqueue_from_calendar(calendar_id=cal_id)
        self.assertTrue(result.get("enqueued"))
        self.assertEqual(result["queue_status"], "queued")

    def test_enqueue_missing_calendar(self) -> None:
        """enqueue_from_calendar returns error for missing calendar item."""
        result = self.tool.enqueue_from_calendar(calendar_id="nonexistent")
        self.assertFalse(result.get("enqueued"))
        self.assertIn("error", result)

    def test_show_queue_empty(self) -> None:
        """show_queue returns empty when no items."""
        result = self.tool.show_queue()
        self.assertEqual(result["count"], 0)

    def test_show_queue_with_items(self) -> None:
        """show_queue returns items after enqueue."""
        cal_id = self._seed_calendar()
        self.tool.enqueue_from_calendar(calendar_id=cal_id)
        result = self.tool.show_queue()
        self.assertGreaterEqual(result["count"], 1)
        self.assertIn("stats", result)

    def test_approve_item(self) -> None:
        """approve_item approves a single item."""
        cal_id = self._seed_calendar()
        self.tool.enqueue_from_calendar(calendar_id=cal_id)
        result = self.tool.approve_item(calendar_id=cal_id)
        self.assertTrue(result.get("approved"))
        # Verify in store
        items = self.store.list_content_queue(status="approved")
        self.assertTrue(any(i["calendar_id"] == cal_id for i in items))

    def test_reject_item(self) -> None:
        """reject_item rejects a single item."""
        cal_id = self._seed_calendar()
        self.tool.enqueue_from_calendar(calendar_id=cal_id)
        result = self.tool.reject_item(calendar_id=cal_id, reason="test")
        self.assertTrue(result.get("rejected"))

    def test_batch_approve_by_pillar(self) -> None:
        """batch_approve approves items matching pillar."""
        for i in range(2):
            cal_id = f"cal_pillar_{i}"
            self._seed_calendar(cal_id=cal_id)
            self.tool.enqueue_from_calendar(calendar_id=cal_id)
        result = self.tool.batch_approve(pillar="education")
        self.assertGreaterEqual(result["approved_count"], 1)

    def test_publish_dry_run(self) -> None:
        """publish_to_facebook with dry_run sets published status."""
        cal_id = self._seed_calendar()
        self.tool.enqueue_from_calendar(calendar_id=cal_id)
        self.tool.approve_item(calendar_id=cal_id)
        result = self.tool.publish_to_facebook(calendar_id=cal_id, dry_run=True)
        self.assertTrue(result.get("published"))
        self.assertTrue(result.get("dry_run"))

    def test_batch_publish_dry_run(self) -> None:
        """batch_publish_to_facebook publishes multiple approved items."""
        for i in range(3):
            cal_id = f"cal_batchpub_{i}"
            self._seed_calendar(cal_id=cal_id, topic=f"topic_{i}")
            self.tool.enqueue_from_calendar(calendar_id=cal_id)
            self.tool.approve_item(calendar_id=cal_id)
        result = self.tool.batch_publish_to_facebook(dry_run=True)
        self.assertGreaterEqual(result.published_count, 1)
        self.assertEqual(result.failed_count, 0)

    def test_publish_only_approved(self) -> None:
        """publish_to_facebook only works on approved items."""
        cal_id = self._seed_calendar()
        self.tool.enqueue_from_calendar(calendar_id=cal_id)
        # NOT approved
        result = self.tool.publish_to_facebook(calendar_id=cal_id, dry_run=True)
        self.assertFalse(result.get("published"))
        self.assertIn("error", result)

    def test_content_queue_result_dataclass(self) -> None:
        """ContentQueueResult dataclass works correctly."""
        r = ContentQueueResult()
        self.assertEqual(r.published_count, 0)
        self.assertEqual(r.failed_count, 0)
        self.assertEqual(r.total, 0)

        r.published.append({"calendar_id": "a"})
        r.failed.append({"calendar_id": "b"})
        self.assertEqual(r.published_count, 1)
        self.assertEqual(r.failed_count, 1)
        self.assertEqual(r.total, 2)
        payload = r.to_dict()
        self.assertEqual(payload["published_count"], 1)
        self.assertEqual(payload["failed_count"], 1)


class ContentQueueIntegrationTest(unittest.TestCase):
    """Full queue lifecycle integration test."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_queue_int.db"
        self.store = UnifiedStore(db_path=self.db_path)
        self.tool = ContentQueueTool(store=self.store, dry_run=True)

    def tearDown(self) -> None:
        self.store.close()

    def test_full_lifecycle(self) -> None:
        """Enqueue → Approve → Publish full lifecycle."""
        # Seed calendar items
        for i in range(2):
            cal_id = f"cal_lifecycle_{i}"
            with self.store._conn() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO calendar
                       (calendar_id, brand_id, date, pillar, objective, topic, angle, status)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (cal_id, "test", "2026-06-10", "education", "reach",
                     f"topic_{i}", "test", "planned"),
                )
            # Enqueue
            self.tool.enqueue_from_calendar(calendar_id=cal_id)

        # Verify queued
        stats = self.store.get_queue_stats()
        self.assertGreaterEqual(stats["queued"], 2)

        # Batch approve
        batch_result = self.tool.batch_approve()
        self.assertGreaterEqual(batch_result["approved_count"], 2)

        stats = self.store.get_queue_stats()
        self.assertGreaterEqual(stats["approved"], 2)
        self.assertEqual(stats["queued"], stats["total"] - stats["approved"])

        # Batch publish (dry run)
        publish_result = self.tool.batch_publish_to_facebook(dry_run=True)
        self.assertGreaterEqual(publish_result.published_count, 1)

        # Final stats
        stats = self.store.get_queue_stats()
        # Some may still be approved (if limit hit) or published
        self.assertGreaterEqual(
            stats["published"] + stats["approved"],
            publish_result.published_count,
        )

    def test_batch_reject_rejected_items(self) -> None:
        """Batch reject with topic filter."""
        cal_id = f"cal_reject_test"
        with self.store._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO calendar
                   (calendar_id, brand_id, date, pillar, topic, angle, status)
                   VALUES (?,?,?,?,?,?,?)""",
                (cal_id, "test", "2026-06-10", "education", "bad_topic",
                 "test", "planned"),
            )
        self.tool.enqueue_from_calendar(calendar_id=cal_id)
        result = self.tool.batch_reject(topic="bad_topic", reason="wrong topic")
        self.assertEqual(result["rejected_count"], 1)
        # Verify status
        item = self.store.list_content_queue(status="rejected")
        self.assertGreaterEqual(len(item), 1)
