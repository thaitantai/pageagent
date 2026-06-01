import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class CalendarOpsCliTest(unittest.TestCase):
    def test_run_daily_persists_draft_caption_ref_and_list_calendar_items_filters_pending(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifacts = tmpdir / "artifacts"
            calendar = tmpdir / "calendar.csv"
            history = tmpdir / "history.csv"
            metrics = tmpdir / "metrics.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"
            comments.write_text(
                "created_at,source,message\n2026-06-24,inbox,Khách hỏi routine cấp ẩm\n",
                encoding="utf-8",
            )
            campaign.write_text(
                json.dumps({"focus": "đẩy lead treatment cấp ẩm"}, ensure_ascii=False),
                encoding="utf-8",
            )
            env = isolated_subprocess_env()
            env["ARTIFACTS_DIR"] = str(artifacts)

            daily = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "run-daily",
                    "--brand-file",
                    str(sample),
                    "--run-date",
                    "2026-06-24",
                    "--days",
                    "1",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--metrics-file",
                    str(metrics),
                    "--comment-file",
                    str(comments),
                    "--campaign-file",
                    str(campaign),
                    "--write-calendar",
                    "--save",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "list-calendar-items",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--metrics-file",
                    str(metrics),
                    "--approval-status",
                    "pending",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )

        daily_payload = json.loads(daily.stdout)
        listed_payload = json.loads(listed.stdout)

        self.assertEqual(daily_payload["calendar_id"], "weekly-plan-brand_abc-2026-06-24-1")
        self.assertIn("artifacts", daily_payload)
        self.assertTrue(daily_payload["artifacts"]["packet"].endswith("daily-ops-2026-06-24.json"))
        self.assertTrue(daily_payload["artifacts"]["caption_package"].endswith("daily-caption-weekly-plan-brand_abc-2026-06-24-1.json"))
        self.assertEqual(listed_payload["summary"]["total_items"], 1)
        self.assertEqual(listed_payload["summary"]["by_approval_status"]["pending"], 1)
        self.assertEqual(listed_payload["items"][0]["calendar_id"], "weekly-plan-brand_abc-2026-06-24-1")
        self.assertTrue(listed_payload["items"][0]["draft_caption_ref"].endswith("daily-caption-weekly-plan-brand_abc-2026-06-24-1.json"))


if __name__ == "__main__":
    unittest.main()
