import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class AnalyticsReportTest(unittest.TestCase):
    def test_weekly_report_command_outputs_recommendations(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            metrics_csv = Path(tmp) / "post_metrics.csv"
            with metrics_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["published_at", "topic", "pillar", "objective", "reach", "engagements", "leads"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "published_at": "2026-05-29",
                        "topic": "Routine 3 bước cho da thiếu nước",
                        "pillar": "education",
                        "objective": "engagement",
                        "reach": "1500",
                        "engagements": "180",
                        "leads": "8",
                    }
                )
                writer.writerow(
                    {
                        "published_at": "2026-05-30",
                        "topic": "Checklist chăm da sau treatment",
                        "pillar": "trust",
                        "objective": "lead",
                        "reach": "900",
                        "engagements": "45",
                        "leads": "12",
                    }
                )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "weekly-report",
                    "--brand-file",
                    str(sample),
                    "--metrics-file",
                    str(metrics_csv),
                    "--store-backend",
                    "local",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )

        data = json.loads(completed.stdout)
        self.assertEqual(data["summary"]["total_posts"], 2)
        self.assertEqual(data["top_post"]["topic"], "Routine 3 bước cho da thiếu nước")
        # New recommendations: data-driven, mentions best pillar or engagement rate insight
        recs_text = " ".join(data.get("recommendations", []))
        self.assertTrue(
            any(kw in recs_text.lower() for kw in ["education", "engagement", "nội dung"]),
            f"Recommendations missing expected content: {data['recommendations']}",
        )


if __name__ == "__main__":
    unittest.main()
