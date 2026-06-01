import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class RunDailyCliTest(unittest.TestCase):
    def test_run_daily_command_outputs_packet_and_saves_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifacts_dir = tmpdir / "artifacts"
            calendar = tmpdir / "calendar.csv"
            history = tmpdir / "history.csv"
            env = isolated_subprocess_env()
            env["ARTIFACTS_DIR"] = str(artifacts_dir)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "run-daily",
                    "--brand-file",
                    str(sample),
                    "--run-date",
                    "2026-06-12",
                    "--days",
                    "1",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--write-calendar",
                    "--save",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )

            payload = json.loads(completed.stdout)
            artifact = artifacts_dir / "ops" / "daily-ops-2026-06-12.json"
            with calendar.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            artifact_exists = artifact.exists()

            self.assertEqual(payload["run_date"], "2026-06-12")
            self.assertEqual(payload["calendar_id"], "weekly-plan-brand_abc-2026-06-12-1")
            self.assertTrue(artifact_exists)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "planned")


if __name__ == "__main__":
    unittest.main()
