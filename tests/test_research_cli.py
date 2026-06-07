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

            env = isolated_subprocess_env(
                PAGES=json.dumps([
                    {
                        "page_id": "main",
                        "page_token": "tok_main",
                        "topic_focus": "cong dong soi da",
                        "community_value": "Giai dap thac mac soi da bang ngon ngu de hieu",
                    }
                ], ensure_ascii=False)
            )
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
            self.assertEqual(payload["research_packet"]["research_packet_job_id"], "daily-2026-06-14")
            self.assertEqual(payload["research_packet"]["page_context"]["page_id"], "main")
            self.assertTrue(Path(payload["artifacts"]["research_packet"]).exists())
            self.assertTrue(any("soi da" in note.lower() for note in payload["plan"]["strategy_notes"]))

    def test_research_standalone_writes_research_packet(self) -> None:
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            output_dir = tmpdir / "research_packets"
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

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "research-standalone",
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
                    "--output-dir",
                    str(output_dir),
                    "--job-id",
                    "test-research",
                    "--page-id",
                    "main",
                    "--no-external-trends",
                ],
                cwd=root,
                env=isolated_subprocess_env(
                    PAGES=json.dumps([
                        {
                            "page_id": "main",
                            "page_token": "tok_main",
                            "topic_focus": "cong dong soi da",
                            "community_value": "Giai dap thac mac soi da bang ngon ngu de hieu",
                        }
                    ], ensure_ascii=False)
                ),
                capture_output=True,
                text=True,
                check=True,
            )

            payload = json.loads(completed.stdout)
            output_file = Path(payload["output_file"])
            saved_payload = json.loads(output_file.read_text(encoding="utf-8"))

            self.assertTrue(output_file.exists())
            self.assertEqual(payload["schema_version"], "research_packet.v1")
            self.assertEqual(payload["job_id"], "test-research")
            self.assertEqual(payload["page_id"], "main")
            self.assertEqual(payload["page_context"]["topic_focus"], "cong dong soi da")
            self.assertEqual(saved_payload["packet_id"], payload["packet_id"])
            self.assertIn(payload["status"], {"ready", "needs_review", "blocked"})
            self.assertEqual(saved_payload["handoff_policy"], payload["handoff_policy"])
            self.assertTrue(payload["handoff_policy"]["requires_human_review"])
            self.assertTrue(payload["gate_reasons"])
            self.assertTrue(payload["brief"]["topic_scores"])
            self.assertGreater(payload["brief"]["confidence_score"], 0)

    def test_page_status_lists_pages_and_recent_packets(self) -> None:
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "research_packets"
            output_dir.mkdir()
            (output_dir / "2026-06-05-test-rpkt-1.json").write_text(
                json.dumps({
                    "packet_id": "rpkt-1",
                    "job_id": "job-1",
                    "created_at": "2026-06-05T00:00:00+00:00",
                    "status": "needs_review",
                    "gate_reasons": ["demo warning"],
                    "page_id": "main",
                    "brief": {
                        "confidence_score": 0.8,
                        "topic_scores": [{"topic": "soi da", "total_score": 7}],
                        "evidence": [{"claim": "x"}],
                    },
                }, ensure_ascii=False),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "page-status",
                    "--output-dir",
                    str(output_dir),
                    "--page-id",
                    "main",
                ],
                cwd=root,
                env=isolated_subprocess_env(
                    PAGES=json.dumps([
                        {
                            "page_id": "main",
                            "page_token": "tok_main",
                            "topic_focus": "cong dong soi da",
                            "community_value": "Giai dap thac mac soi da bang ngon ngu de hieu",
                        }
                    ], ensure_ascii=False)
                ),
                capture_output=True,
                text=True,
                check=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["page_filter"], "main")
            self.assertEqual(payload["pages"][0]["page_id"], "main")
            self.assertEqual(payload["research_packets"][0]["packet_id"], "rpkt-1")
            self.assertEqual(payload["research_packets"][0]["status"], "needs_review")
            self.assertEqual(payload["research_packets"][0]["gate_reasons"], ["demo warning"])
            self.assertEqual(payload["research_packets"][0]["top_topic"], "soi da")
            self.assertEqual(payload["research_packets"][0]["evidence_count"], 1)


if __name__ == "__main__":
    unittest.main()
