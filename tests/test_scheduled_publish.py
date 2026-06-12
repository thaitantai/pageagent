import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.content.auto_approval import (
    AutoApprovalConfig,
    AutoApprovalEngine,
)
from fanpage_agent.tools.publishing.planner import PlannerTool
from fanpage_agent.tools.publishing.scheduled_publish import ScheduledPublishResult, ScheduledPublishTool
from fanpage_agent.tools.content.verifier import VerifierTool


class ScheduledPublishToolTest(unittest.TestCase):
    """Test publishing approved items that are due."""

    def setUp(self):
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        self.profile = load_brand_profile(sample)
        self.plan = PlannerTool().plan_week(profile=self.profile, start_date="2026-06-01", days=2)

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
            verifier=VerifierTool(),
            config=AutoApprovalConfig(require_verification_pass=False),
        )
        engine.process_pending()
        return store

    def test_publishes_due_approved_items(self):
        """Items approved and due on/before today should be published."""
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store_with_approved_items(Path(tmp))

            service = ScheduledPublishTool(
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

            service = ScheduledPublishTool(
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

            service = ScheduledPublishTool(
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

            service = ScheduledPublishTool(
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

            service = ScheduledPublishTool(
                store=store,
                brand_id=self.profile.brand_id,
            )
            result = service.publish_due(reference_date="2026-06-02")

            rows = store._read_calendar_rows()

        self.assertEqual(rows[0]["status"], "published")
        self.assertEqual(rows[1]["status"], "published")
        self.assertIn("published_at", rows[0])
        self.assertTrue(rows[0]["published_at"])  # not empty

    def test_skipped_items_include_operator_reason_codes(self):
        """Skipped scheduled items should explain what an operator must fix."""
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store_with_approved_items(Path(tmp))
            rows = store._read_calendar_rows()
            rows[0]["approval_status"] = "pending"
            rows[0]["status"] = "planned"
            rows[1]["final_caption_ref"] = ""
            store._write_calendar_rows(rows)

            service = ScheduledPublishTool(
                store=store,
                brand_id=self.profile.brand_id,
            )
            result = service.publish_due(reference_date="2026-06-02")

        reason_codes = {item["reason_code"] for item in result.skipped}
        self.assertEqual(result.published_count, 0)
        self.assertIn("approval_status_not_approved", reason_codes)
        self.assertIn("missing_final_caption_ref", reason_codes)
        self.assertTrue(all("approval_status" in item for item in result.skipped))


class ScheduledPublishWithFacebookTest(unittest.TestCase):
    """Test publishing with FacebookClient integration."""

    def setUp(self):
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        self.profile = load_brand_profile(sample)

    def test_publishes_to_facebook_when_client_provided(self):
        """When fb_client is provided, post_to_page should be called."""
        # Build a minimal mock FacebookClient
        class MockFacebookClient:
            page_id = "123456789"

            def post_to_page(self, message: str, link: str = "") -> dict:
                self.last_message = message
                return {"id": "123456789_987654321"}

        mock_fb = MockFacebookClient()

        # Create store with approved items
        planner = PlannerTool()
        plan = planner.plan_week(profile=self.profile, start_date="2026-06-01", days=1)

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "content_calendar.csv"
            history = tmpdir / "post_history.csv"
            store = LocalSheetStore(calendar_csv=calendar, history_csv=history)
            store.append_plan(self.profile.brand_id, plan)

            rows = store._read_calendar_rows()
            rows[0]["approval_status"] = "approved"
            rows[0]["status"] = "approved"

            # Create a caption file
            caption = tmpdir / "caption.json"
            caption.write_text(json.dumps({
                "topic": "Test topic",
                "variants": [
                    {
                        "label": "A",
                        "hook": "Bạn có biết điều này?",
                        "caption": "Đây là nội dung bài viết.",
                        "cta": "Nhắn tin để biết thêm",
                        "tone_tags": ["ấm", "rõ"],
                        "visual_brief": "",
                    }
                ],
                "dos": [],
                "donts": [],
            }), encoding="utf-8")
            rows[0]["final_caption_ref"] = str(caption)
            store._write_calendar_rows(rows)

            service = ScheduledPublishTool(
                store=store,
                brand_id=self.profile.brand_id,
                fb_client=mock_fb,  # type: ignore[arg-type]
            )
            result = service.publish_due(reference_date="2026-06-02")

        self.assertEqual(result.published_count, 1)
        self.assertIn("post_id", result.published[0])
        self.assertEqual(result.published[0]["post_id"], "123456789_987654321")
        self.assertIn("permalink", result.published[0])
        self.assertIn("facebook.com", result.published[0]["permalink"])
        self.assertIn("Bạn có biết điều này?", mock_fb.last_message)
        self.assertIn("Đây là nội dung bài viết.", mock_fb.last_message)

    def test_publishes_without_facebook_when_no_client(self):
        """Without fb_client, it falls back to old behaviour (no API call)."""
        planner = PlannerTool()
        plan = planner.plan_week(profile=self.profile, start_date="2026-06-01", days=1)

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "content_calendar.csv"
            history = tmpdir / "post_history.csv"
            store = LocalSheetStore(calendar_csv=calendar, history_csv=history)
            store.append_plan(self.profile.brand_id, plan)

            rows = store._read_calendar_rows()
            rows[0]["approval_status"] = "approved"
            rows[0]["status"] = "approved"
            rows[0]["final_caption_ref"] = str(tmpdir / "caption.json")
            store._write_calendar_rows(rows)

            service = ScheduledPublishTool(
                store=store,
                brand_id=self.profile.brand_id,
                # no fb_client — should fall back silently
            )
            result = service.publish_due(reference_date="2026-06-02")

        self.assertEqual(result.published_count, 1)
        self.assertEqual(result.published[0]["post_id"], "")
        base_id = f"{plan.plan_title}-1"
        self.assertEqual(
            result.published[0]["permalink"],
            f"https://fanpage.auto/{base_id}",
        )

    def test_fail_open_when_facebook_errors(self):
        """If Facebook API raises, we still mark as published locally (fail open)."""

        class FailingFacebookClient:
            page_id = "123456789"

            def post_to_page(self, message: str, link: str = "") -> dict:
                msg = "Facebook API error 400: (#200) Permission error"
                raise RuntimeError(msg)

        planner = PlannerTool()
        plan = planner.plan_week(profile=self.profile, start_date="2026-06-01", days=1)

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "content_calendar.csv"
            history = tmpdir / "post_history.csv"
            store = LocalSheetStore(calendar_csv=calendar, history_csv=history)
            store.append_plan(self.profile.brand_id, plan)

            rows = store._read_calendar_rows()
            rows[0]["approval_status"] = "approved"
            rows[0]["status"] = "approved"
            rows[0]["final_caption_ref"] = str(tmpdir / "caption.json")
            store._write_calendar_rows(rows)

            service = ScheduledPublishTool(
                store=store,
                brand_id=self.profile.brand_id,
                fb_client=FailingFacebookClient(),  # type: ignore[arg-type]
            )
            result = service.publish_due(reference_date="2026-06-02")

        # Published count should still be 1 (fail open) with error field
        self.assertEqual(result.published_count, 1)
        self.assertIn("error", result.published[0])
        self.assertIn("Facebook API error", result.published[0]["error"])

    def test_publishes_with_sqlite_backend(self):
        """Regression: publish_due crashed on UnifiedStore because it called
        the LocalSheetStore-private _read_calendar_rows()."""
        from fanpage_agent.adapters.sqlite_store import UnifiedStore

        plan = PlannerTool().plan_week(
            profile=self.profile, start_date="2026-06-01", days=2
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            store = UnifiedStore(db_path=tmpdir / "store.db")
            store.append_plan(self.profile.brand_id, plan)

            items = store.list_calendar_items()
            self.assertEqual(len(items), 2)
            for item in items:
                store.approve_calendar_item(
                    calendar_id=item["calendar_id"],
                    approved_by="test",
                    final_caption_ref=str(tmpdir / "caption.json"),
                    approved_at="2026-06-01T00:00:00+00:00",
                )

            service = ScheduledPublishTool(
                store=store,
                brand_id=self.profile.brand_id,
            )
            result = service.publish_due(reference_date="2026-06-02")

        self.assertEqual(result.published_count, 2)
        self.assertEqual(result.skipped_count, 0)


if __name__ == "__main__":
    unittest.main()
