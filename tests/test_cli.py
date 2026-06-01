from pathlib import Path
import json
import subprocess
import sys
import unittest

from tests.test_env import isolated_subprocess_env


class CliSmokeTest(unittest.TestCase):
    def test_plan_week_command_outputs_valid_json(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"
        env = isolated_subprocess_env()
        completed = subprocess.run(
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
                "2",
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        data = json.loads(completed.stdout)
        self.assertEqual(data["plan_title"], "weekly-plan-brand_abc-2026-06-01")
        self.assertEqual(len(data["days"]), 2)


if __name__ == "__main__":
    unittest.main()
