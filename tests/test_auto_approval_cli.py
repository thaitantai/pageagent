import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.publishing.planner import PlannerTool
from tests.test_env import isolated_subprocess_env


class ProcessPendingCliTest(unittest.TestCase):
    """Test 'process-pending' CLI command."""

    _root = Path(__file__).resolve().parents[1]
    _sample = _root / "data" / "sample" / "brand_profile.json"

    def test_process_pending_auto_approves_eligible_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "content_calendar.csv"
            history = tmpdir / "post_history.csv"
            brand_file = tmpdir / "brand_profile.json"

            # Create a minimal brand profile
            profile = load_brand_profile(self._sample)
            profile.banned_phrases = []
            brand_file.write_text(profile.model_dump_json(), encoding="utf-8")

            # Plan and save to calendar
            plan = PlannerTool().plan_week(profile=profile, start_date="2026-06-01", days=2)
            store = LocalSheetStore(calendar_csv=calendar, history_csv=history)
            store.append_plan(profile.brand_id, plan)

            # Give items captions
            rows = store._read_calendar_rows()
            rows[0]["draft_caption_ref"] = str(tmpdir / "caption1.json")
            rows[1]["draft_caption_ref"] = str(tmpdir / "caption2.json")
            store._write_calendar_rows(rows)

            result = subprocess.run(
                [
                    sys.executable, "-m", "fanpage_agent.main",
                    "process-pending",
                    "--brand-file", str(brand_file),
                    "--calendar-file", str(calendar),
                    "--history-file", str(history),
                    "--no-verify",
                ],
                cwd=self._root,
                env=isolated_subprocess_env(),
                capture_output=True, text=True, check=True,
            )

        data = json.loads(result.stdout)
        self.assertEqual(data["auto_approved_count"], 2)
        self.assertEqual(data["skipped_count"], 0)

    def test_process_pending_with_banned_phrases_skips_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "content_calendar.csv"
            history = tmpdir / "post_history.csv"
            brand_file = tmpdir / "brand_profile.json"

            profile = load_brand_profile(self._sample)
            profile.banned_phrases = ["cấm"]
            brand_file.write_text(profile.model_dump_json(), encoding="utf-8")

            plan = PlannerTool().plan_week(profile=profile, start_date="2026-06-01", days=2)
            store = LocalSheetStore(calendar_csv=calendar, history_csv=history)
            store.append_plan(profile.brand_id, plan)
            rows = store._read_calendar_rows()
            rows[0]["draft_caption_ref"] = str(tmpdir / "caption1.json")
            rows[0]["hook"] = "cấm không được làm vậy"
            rows[1]["draft_caption_ref"] = str(tmpdir / "caption2.json")
            store._write_calendar_rows(rows)

            result = subprocess.run(
                [
                    sys.executable, "-m", "fanpage_agent.main",
                    "process-pending",
                    "--brand-file", str(brand_file),
                    "--calendar-file", str(calendar),
                    "--history-file", str(history),
                    "--no-verify",
                ],
                cwd=self._root,
                env=isolated_subprocess_env(),
                capture_output=True, text=True, check=True,
            )

        data = json.loads(result.stdout)
        self.assertEqual(data["auto_approved_count"], 1)
        self.assertEqual(data["skipped_count"], 1)


class ScheduledPublishCliTest(unittest.TestCase):
    """Test 'scheduled-publish' CLI command."""

    _root = Path(__file__).resolve().parents[1]
    _sample = _root / "data" / "sample" / "brand_profile.json"

    def _prepare_auto_approved_store(self, tmpdir: Path) -> tuple[Path, Path, str]:
        calendar = tmpdir / "content_calendar.csv"
        history = tmpdir / "post_history.csv"
        brand_file = tmpdir / "brand_profile.json"

        profile = load_brand_profile(self._sample)
        profile.banned_phrases = []
        brand_file.write_text(profile.model_dump_json(), encoding="utf-8")

        plan = PlannerTool().plan_week(profile=profile, start_date="2026-06-01", days=2)
        store = LocalSheetStore(calendar_csv=calendar, history_csv=history)
        store.append_plan(profile.brand_id, plan)
        rows = store._read_calendar_rows()
        rows[0]["draft_caption_ref"] = str(tmpdir / "caption1.json")
        rows[1]["draft_caption_ref"] = str(tmpdir / "caption2.json")
        store._write_calendar_rows(rows)

        # Auto-approve via process-pending CLI
        subprocess.run(
            [
                sys.executable, "-m", "fanpage_agent.main",
                "process-pending",
                "--brand-file", str(brand_file),
                "--calendar-file", str(calendar),
                "--history-file", str(history),
                "--no-verify",
            ],
            cwd=self._root,
            env=isolated_subprocess_env(),
            capture_output=True, text=True, check=True,
        )
        return calendar, history, profile.brand_id

    def test_scheduled_publish_publishes_due_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            calendar, history, brand_id = self._prepare_auto_approved_store(Path(tmp))

            result = subprocess.run(
                [
                    sys.executable, "-m", "fanpage_agent.main",
                    "scheduled-publish",
                    "--calendar-file", str(calendar),
                    "--reference-date", "2026-06-02",
                ],
                cwd=self._root,
                env=isolated_subprocess_env(),
                capture_output=True, text=True, check=True,
            )

        data = json.loads(result.stdout)
        self.assertEqual(data["published_count"], 2)

    def test_scheduled_publish_skips_future_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            calendar, history, brand_id = self._prepare_auto_approved_store(Path(tmp))

            result = subprocess.run(
                [
                    sys.executable, "-m", "fanpage_agent.main",
                    "scheduled-publish",
                    "--calendar-file", str(calendar),
                    "--reference-date", "2026-05-30",  # before both items
                ],
                cwd=self._root,
                env=isolated_subprocess_env(),
                capture_output=True, text=True, check=True,
            )

        data = json.loads(result.stdout)
        self.assertEqual(data["published_count"], 0)
        self.assertEqual(data["skipped_count"], 2)


if __name__ == "__main__":
    unittest.main()
