import tempfile
import unittest
from datetime import date
from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.services.auto_approval import (
    AutoApprovalConfig,
    AutoApprovalEngine,
)
from fanpage_agent.services.planner import PlannerService
from fanpage_agent.services.scheduled_publish import ScheduledPublishResult, ScheduledPublishService
from fanpage_agent.services.verifier import VerifierService


class ScheduledPublishServiceTest(unittest.TestCase):
    """Test publishing approved items that are due."""

    def setUp(self):
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        self.profile = load_brand_profile(sample)
        self.plan = PlannerService().plan_week(profile=self.profile, start_date="2026-06-01", days=2)

    def _make_store_with_approved_items(self, tmpdir: Path) -> LocalSheetStore:
        calendar = tmpdir / "content_calendar.csv"
        history = tmpdir / "post_history.csv"
        store = LocalSheetStore(calendar_csv=calendar, history_csv=history)
        store.append_plan(self.profile.brand_id, self.plan)
        rows = store._read_calendar_rows()

        # Give both items captions and auto-approve them
        rows[0]["draft_caption_ref"] = str(tmpdir / "caption1.json")
        rows[1]["draft_caption_ref"] = str(tmpdir / "caption2.json")
        store._write_calendar_rows(rows)

        engine = AutoApprovalEngine(
            brand_profile=self.profile,
            store=store,
            verifier=VerifierService(),
            config=AutoApprovalConfig(require_verification_pass=False),
        )
        engine.process_pending()
        return store

    def test_publishes_due_approved_items(self):
        """Items approved and due on/before today should be published."""
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store_with_approved_items(Path(tmp))

            service = ScheduledPublishService(
                store=store,
                brand_id=self.profile.brand_id,
            )
            result = service.publish_due(reference_date="2026-06-02")

        self.assertIsInstance(result, ScheduledPublishResult)
        self.assertEqual(result.published_count, 2)  # both items are due
        self.assertEqual(len(result.published), 2)

    def test_skips_future_items(self):
        """Items with future dates should not be published yet."""
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store_with_approved_items(Path(tmp))

            # Change dates to future
            rows = store._read_calendar_rows()
            rows[0]["date"] = "2099-01-01"
            rows[1]["date"] = "2099-01-02"
            store._write_calendar_rows(rows)

            service = ScheduledPublishService(
                store=store,
                brand_id=self.profile.brand_id,
            )
            result = service.publish_due(reference_date="2026-06-02")

        self.assertEqual(result.published_count, 0)

    def test_publishes_partially_due(self):
        """Only items whose date is <= reference_date should be published."""
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store_with_approved_items(Path(tmp))

            rows = store._read_calendar_rows()
            rows[1]["date"] = "2099-01-02"  # day 2 is future
            store._write_calendar_rows(rows)

            service = ScheduledPublishService(
                store=store,
                brand_id=self.profile.brand_id,
            )
            result = service.publish_due(reference_date="2026-06-02")

        self.assertEqual(result.published_count, 1)
        self.assertEqual(result.published[0]["calendar_id"], f"{self.plan.plan_title}-1")

    def test_skips_already_published_items(self):
        """Already published items should be skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store_with_approved_items(Path(tmp))
            store.publish_calendar_item(
                calendar_id=f"{self.plan.plan_title}-1",
                published_at="2026-06-01",
                permalink="https://example.com/post-1",
            )

            service = ScheduledPublishService(
                store=store,
                brand_id=self.profile.brand_id,
            )
            result = service.publish_due(reference_date="2026-06-02")

        self.assertEqual(result.published_count, 1)  # only item 2 published
        self.assertEqual(result.skipped_count, 1)

    def test_publishes_item_updates_calendar_and_history(self):
        """Verifying that published items actually have status=published in CSV."""
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store_with_approved_items(Path(tmp))

            service = ScheduledPublishService(
                store=store,
                brand_id=self.profile.brand_id,
            )
            result = service.publish_due(reference_date="2026-06-02")

            rows = store._read_calendar_rows()

        self.assertEqual(rows[0]["status"], "published")
        self.assertEqual(rows[1]["status"], "published")
        self.assertIn("published_at", rows[0])
        self.assertTrue(rows[0]["published_at"])  # not empty


if __name__ == "__main__":
    unittest.main()
