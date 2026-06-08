import csv
import json
import tempfile
import unittest
from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.content.auto_approval import (
    AutoApprovalConfig,
    AutoApprovalEngine,
    AutoApprovalResult,
)
from fanpage_agent.tools.publishing.planner import PlannerTool
from fanpage_agent.tools.content.verifier import VerifierTool


class AutoApprovalEngineTest(unittest.TestCase):
    """Test auto-approval of calendar items based on configurable rules."""

    def setUp(self):
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        self.profile = load_brand_profile(sample)
        self.plan = PlannerTool().plan_week(profile=self.profile, start_date="2026-06-01", days=2)
        self.calendar_id_1 = f"{self.plan.plan_title}-1"
        self.calendar_id_2 = f"{self.plan.plan_title}-2"

    def _make_store(self, tmpdir: Path) -> LocalSheetStore:
        calendar = tmpdir / "content_calendar.csv"
        history = tmpdir / "post_history.csv"
        store = LocalSheetStore(calendar_csv=calendar, history_csv=history)
        store.append_plan(self.profile.brand_id, self.plan)
        # Give item 1 a draft caption ref so it's eligible
        rows = store._read_calendar_rows()
        rows[0]["draft_caption_ref"] = str(tmpdir / "caption.json")
        rows[1]["draft_caption_ref"] = str(tmpdir / "caption2.json")
        store._write_calendar_rows(rows)
        return store

    # ── RED test 1: happy path ──────────────────────────────────

    def test_auto_approves_item_that_passes_all_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            engine = AutoApprovalEngine(
                brand_profile=self.profile,
                store=store,
                verifier=VerifierTool(),
                config=AutoApprovalConfig(require_verification_pass=False),
            )
            result = engine.process_pending()

        self.assertIsInstance(result, AutoApprovalResult)
        self.assertEqual(result.auto_approved_count, 2)
        self.assertEqual(result.skipped_count, 0)

    # ── RED test 2: banned phrases ──────────────────────────────

    def test_skips_item_with_banned_phrases(self):
        self.profile.banned_phrases = ["cấm"]
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            # Inject banned phrase into item 1's hook
            rows = store._read_calendar_rows()
            rows[0]["hook"] = "cấm không được làm điều này"
            store._write_calendar_rows(rows)

            engine = AutoApprovalEngine(
                brand_profile=self.profile,
                store=store,
                verifier=VerifierTool(),
                config=AutoApprovalConfig(
                    skip_banned_phrases=True,
                    require_verification_pass=False,
                ),
            )
            result = engine.process_pending()

        self.assertEqual(result.auto_approved_count, 1)  # item 2 passes
        self.assertEqual(result.skipped_count, 1)  # item 1 skipped
        self.assertIn("banned phrase", result.skipped[0]["reason"].lower())
        self.assertEqual(result.skipped[0]["reason_code"], "banned_phrase_detected")

    # ── RED test 3: already approved ────────────────────────────

    def test_skips_already_approved_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            store.approve_calendar_item(
                calendar_id=self.calendar_id_1,
                approved_by="Tai",
                final_caption_ref=str(Path(tmp) / "caption.json"),
                approved_at="2026-06-01",
            )
            engine = AutoApprovalEngine(
                brand_profile=self.profile,
                store=store,
                verifier=VerifierTool(),
                config=AutoApprovalConfig(require_verification_pass=False),
            )
            result = engine.process_pending()

        self.assertEqual(result.auto_approved_count, 1)  # item 2 auto-approved
        self.assertEqual(result.skipped_count, 1)  # item 1 skipped (already approved)
        self.assertEqual(result.skipped[0]["reason_code"], "already_finalized")

    # ── RED test 4: verification fail ───────────────────────────

    def test_skips_item_with_verification_issues(self):
        self.profile.banned_phrases = ["test_banned_phrase"]
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            rows = store._read_calendar_rows()
            rows[0]["hook"] = "this contains test_banned_phrase"
            store._write_calendar_rows(rows)

            engine = AutoApprovalEngine(
                brand_profile=self.profile,
                store=store,
                verifier=VerifierTool(),
                config=AutoApprovalConfig(require_verification_pass=True),
            )
            result = engine.process_pending()

        self.assertEqual(result.auto_approved_count, 1)  # item 2 passes
        self.assertGreaterEqual(len(result.skipped), 1)

    # ── RED test 5: duplicate topic with history ────────────────

    def test_detects_duplicate_with_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            topic = self.plan.days[0].topic
            with store.history_csv.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=store.HISTORY_HEADERS)
                writer.writeheader()
                writer.writerow({
                    "published_at": "2026-05-30",
                    "topic": topic,
                    "hook": "some hook",
                    "pillar": self.plan.days[0].pillar,
                    "objective": self.plan.days[0].objective,
                    "permalink": "https://example.com/prev",
                    "reach": "500",
                    "engagement_rate": "0.05",
                })

            engine = AutoApprovalEngine(
                brand_profile=self.profile,
                store=store,
                verifier=VerifierTool(),
                config=AutoApprovalConfig(
                    skip_duplicate_topics=True,
                    require_verification_pass=False,
                ),
            )
            result = engine.process_pending()

        self.assertEqual(result.auto_approved_count, 1)  # item 2 is different topic
        self.assertGreaterEqual(len(result.skipped), 1)
        self.assertIn("duplicate", result.skipped[0]["reason"].lower())


if __name__ == "__main__":
    unittest.main()
