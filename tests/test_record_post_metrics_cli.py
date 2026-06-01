import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class RecordPostMetricsCliTest(unittest.TestCase):
    def test_publish_then_record_post_metrics_updates_calendar_and_metrics_store(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "calendar.csv"
            history = tmpdir / "history.csv"
            metrics = tmpdir / "metrics.csv"

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "plan-week",
                    "--brand-file",
                    str(sample),
                    "--start-date",
                    "2026-06-25",
                    "--days",
                    "1",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--write-calendar",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "approve-caption",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--metrics-file",
                    str(metrics),
                    "--calendar-id",
                    "weekly-plan-brand_abc-2026-06-25-1",
                    "--approved-by",
                    "Tai",
                    "--caption-file",
                    "artifacts/captions/final.json",
                    "--approved-at",
                    "2026-06-25T09:00:00",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "publish-post",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--metrics-file",
                    str(metrics),
                    "--calendar-id",
                    "weekly-plan-brand_abc-2026-06-25-1",
                    "--published-at",
                    "2026-06-25T10:00:00",
                    "--permalink",
                    "https://example.com/post-1",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "record-post-metrics",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--metrics-file",
                    str(metrics),
                    "--calendar-id",
                    "weekly-plan-brand_abc-2026-06-25-1",
                    "--reach",
                    "1800",
                    "--engagements",
                    "126",
                    "--leads",
                    "11",
                    "--recorded-at",
                    "2026-06-26T08:00:00",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )

            payload = json.loads(completed.stdout)
            with calendar.open("r", encoding="utf-8", newline="") as handle:
                calendar_rows = list(csv.DictReader(handle))
            with metrics.open("r", encoding="utf-8", newline="") as handle:
                metric_rows = list(csv.DictReader(handle))

        self.assertEqual(payload["calendar"]["reach"], "1800")
        self.assertEqual(payload["calendar"]["engagement_rate"], "0.07")
        self.assertEqual(payload["metric"]["engagements"], "126")
        self.assertEqual(payload["metric"]["leads"], "11")
        self.assertEqual(calendar_rows[0]["reach"], "1800")
        self.assertEqual(calendar_rows[0]["engagement_rate"], "0.07")
        self.assertEqual(metric_rows[0]["published_at"], "2026-06-25T10:00:00")
        self.assertEqual(metric_rows[0]["reach"], "1800")
        self.assertEqual(metric_rows[0]["engagements"], "126")
        self.assertEqual(metric_rows[0]["leads"], "11")


if __name__ == "__main__":
    unittest.main()
