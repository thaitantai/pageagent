import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class EvalCliTest(unittest.TestCase):
    def test_eval_all_outputs_summary_and_saves_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifacts_dir = tmpdir / "artifacts"
            history = tmpdir / "post_history.csv"
            metrics = tmpdir / "post_metrics.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"
            calendar = tmpdir / "calendar.csv"

            history.write_text(
                "published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate\n"
                "2026-06-01,Da thiếu nước nên làm gì?,Hook A,education,reach,https://example.com/1,1200,0.05\n"
                "2026-06-02,Da thiếu nước nên làm gì?,Hook B,education,reach,https://example.com/2,900,0.04\n",
                encoding="utf-8",
            )
            metrics.write_text(
                "published_at,topic,pillar,objective,reach,engagements,leads\n"
                "2026-06-03,Khi nào cần soi da?,trust,lead,1500,90,8\n"
                "2026-06-04,Routine phục hồi da,education,lead,1700,130,11\n",
                encoding="utf-8",
            )
            comments.write_text(
                "created_at,source,message\n"
                "2026-06-05,comment,Da thiếu nước thì nên bắt đầu từ đâu?\n",
                encoding="utf-8",
            )
            campaign.write_text(
                json.dumps(
                    {
                        "campaign_focus": ["soi da"],
                        "priority_objective": "lead",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            env = isolated_subprocess_env()
            env["ARTIFACTS_DIR"] = str(artifacts_dir)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "eval-all",
                    "--brand-file",
                    str(sample),
                    "--start-date",
                    "2026-06-20",
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
                    "--save",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )

            payload = json.loads(completed.stdout)
            artifact = artifacts_dir / "evals" / "eval-summary-2026-06-20.json"

            self.assertEqual(payload["summary"]["total"], 4)
            self.assertEqual(payload["summary"]["failed"], 0)
            self.assertTrue(artifact.exists())
            self.assertEqual(len(payload["checks"]), 4)


if __name__ == "__main__":
    unittest.main()
