import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class ResearchCliTest(unittest.TestCase):
    def test_run_daily_includes_research_brief_and_saves_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifacts_dir = tmpdir / "artifacts"
            calendar = tmpdir / "calendar.csv"
            history = tmpdir / "history.csv"
            metrics = tmpdir / "metrics.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"

            history.write_text(
                "published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate\n"
                "2026-06-01,Da thiếu nước nên làm gì?,Hook A,education,reach,https://example.com/1,1200,0.05\n",
                encoding="utf-8",
            )
            metrics.write_text(
                "published_at,topic,pillar,objective,reach,engagements,leads\n"
                "2026-06-03,Khi nào cần soi da?,trust,lead,1500,90,8\n",
                encoding="utf-8",
            )
            comments.write_text(
                "created_at,source,message\n"
                "2026-06-05,inbox,Chi phí soi da là bao nhiêu?\n",
                encoding="utf-8",
            )
            campaign.write_text(
                json.dumps({"campaign_focus": ["soi da"], "priority_objective": "lead"}, ensure_ascii=False),
                encoding="utf-8",
            )

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
                    "2026-06-14",
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

            payload = json.loads(completed.stdout)
            artifact = artifacts_dir / "ops" / "daily-ops-2026-06-14.json"
            self.assertTrue(artifact.exists())
            self.assertIn("research_brief", payload)
            self.assertEqual(payload["research_brief"]["recommended_objectives"][0], "lead")
            self.assertIn("soi da", payload["research_brief"]["campaign_focus"])
            self.assertIn("Chi phí soi da là bao nhiêu?", payload["research_brief"]["frequent_questions"])
            self.assertGreater(payload["research_brief"]["confidence_score"], 0)
            self.assertTrue(payload["research_brief"]["evidence"])
            self.assertIn("quality_warnings", payload["research_brief"])
            self.assertTrue(payload["research_brief"]["topic_scores"])
            self.assertIn("total_score", payload["research_brief"]["topic_scores"][0])
            self.assertTrue(any("soi da" in note.lower() for note in payload["plan"]["strategy_notes"]))


if __name__ == "__main__":
    unittest.main()
