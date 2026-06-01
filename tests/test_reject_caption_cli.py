import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class RejectCaptionCliTest(unittest.TestCase):
    def test_reject_caption_updates_calendar_row(self) -> None:
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

            rejected = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "reject-caption",
                    "--calendar-file",
                    str(calendar),
                    "--calendar-id",
                    calendar_id,
                    "--reason",
                    "CTA chưa ổn",
                    "--rejected-at",
                    "2026-06-01",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )

            with calendar.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        rejected_data = json.loads(rejected.stdout)
        self.assertEqual(rejected_data["approval_status"], "rejected")
        self.assertIn("CTA chưa ổn", rejected_data["notes"])
        self.assertEqual(rows[0]["approval_status"], "rejected")


if __name__ == "__main__":
    unittest.main()
