import csv
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


class ApprovalLifecycleTest(unittest.TestCase):
    def test_approve_and_publish_update_calendar_and_history(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        plan = PlannerTool().plan_week(profile=profile, start_date="2026-06-01", days=1)

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "content_calendar.csv"
            history = tmpdir / "post_history.csv"
            caption = tmpdir / "caption.json"
            caption.write_text(
                json.dumps({"topic": plan.days[0].topic, "variants": [{"label": "A", "caption": "Caption A"}]}, ensure_ascii=False),
                encoding="utf-8",
            )

            store = LocalSheetStore(calendar_csv=calendar, history_csv=history)
            store.append_plan(profile.brand_id, plan)
            calendar_id = f"{plan.plan_title}-1"

            store.approve_calendar_item(
                calendar_id=calendar_id,
                approved_by="Tai",
                final_caption_ref=str(caption),
                approved_at="2026-06-01",
            )
            store.publish_calendar_item(
                calendar_id=calendar_id,
                published_at="2026-06-02",
                permalink="https://example.com/post-1",
                reach=1200,
                engagement_rate=0.08,
            )

            with calendar.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            with history.open("r", encoding="utf-8", newline="") as handle:
                history_rows = list(csv.DictReader(handle))

        self.assertEqual(rows[0]["approval_status"], "approved")
        self.assertEqual(rows[0]["status"], "published")
        self.assertEqual(rows[0]["approved_by"], "Tai")
        self.assertEqual(rows[0]["final_caption_ref"], str(caption))
        self.assertEqual(history_rows[0]["topic"], plan.days[0].topic)
        self.assertEqual(history_rows[0]["permalink"], "https://example.com/post-1")


class ApprovalLifecycleCliTest(unittest.TestCase):
    def test_cli_approve_and_publish_commands_work(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "content_calendar.csv"
            history = tmpdir / "post_history.csv"
            plan_json = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "plan-week",
                    "--brand-file",
                    str(sample),
                    "--start-date",
                    "2026-06-01",
                    "--days",
                    "1",
                    "--write-calendar",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(plan_json.stdout)
            calendar_id = f"{payload['plan_title']}-1"

            caption = tmpdir / "caption.json"
            caption.write_text(json.dumps({"topic": payload['days'][0]['topic']}, ensure_ascii=False), encoding="utf-8")

            approve = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "approve-caption",
                    "--calendar-file",
                    str(calendar),
                    "--calendar-id",
                    calendar_id,
                    "--approved-by",
                    "Tai",
                    "--caption-file",
                    str(caption),
                    "--approved-at",
                    "2026-06-01",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            publish = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "publish-post",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--calendar-id",
                    calendar_id,
                    "--published-at",
                    "2026-06-02",
                    "--permalink",
                    "https://example.com/post-1",
                    "--reach",
                    "1200",
                    "--engagement-rate",
                    "0.08",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )

        approve_data = json.loads(approve.stdout)
        publish_data = json.loads(publish.stdout)
        self.assertEqual(approve_data["approval_status"], "approved")
        self.assertEqual(publish_data["status"], "published")
        self.assertEqual(publish_data["permalink"], "https://example.com/post-1")

    def test_cli_publish_blocks_unapproved_caption(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "content_calendar.csv"
            history = tmpdir / "post_history.csv"
            plan_json = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "plan-week",
                    "--brand-file",
                    str(sample),
                    "--start-date",
                    "2026-06-01",
                    "--days",
                    "1",
                    "--write-calendar",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(plan_json.stdout)
            calendar_id = f"{payload['plan_title']}-1"

            publish = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "publish-post",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--calendar-id",
                    calendar_id,
                    "--published-at",
                    "2026-06-02",
                    "--permalink",
                    "https://example.com/post-1",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
            )

        self.assertEqual(publish.returncode, 2)
        publish_data = json.loads(publish.stdout)
        self.assertTrue(publish_data["blocked"])
        self.assertEqual(publish_data["action"], "publish-post")
        self.assertIn("approval_status_not_approved", publish_data["reason_codes"])
        self.assertIn("missing_final_caption_ref", publish_data["reason_codes"])


if __name__ == "__main__":
    unittest.main()
