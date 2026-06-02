from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from tests.test_env import isolated_subprocess_env


class CliSmokeTest(unittest.TestCase):
    def test_plan_week_command_outputs_valid_json(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "content_calendar.csv"
            history = tmpdir / "post_history.csv"

            # Create minimal empty CSV files with headers only
            calendar.write_text(
                "brand_id,calendar_id,date,pillar,objective,topic,angle,format,hook,cta,visual_brief,status,approval_status,approved_by,final_caption_ref,campaign_tag,notes,last_updated\n",
                encoding="utf-8",
            )
            history.write_text(
                "published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate\n",
                encoding="utf-8",
            )

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
                    "--history-file",
                    str(history),
                    "--calendar-file",
                    str(calendar),
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
