import json
import tempfile
import unittest
from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.analytics.evals import EvalTool


class EvalToolTest(unittest.TestCase):
    def test_mentions_campaign_focus_accepts_vietnamese_focus_terms(self) -> None:
        result = EvalTool._mentions_campaign_focus(
            ["Tuần này tập trung vào soi da và phục hồi da treatment."],
            type("Brief", (), {"campaign_focus": ["soi da"]})(),
        )

        self.assertTrue(result)

    def test_run_all_returns_passed_checks_and_summary(self) -> None:
        root = Path(__file__).resolve().parents[1]
        profile = load_brand_profile(root / "data" / "sample" / "brand_profile.json")

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            history = tmpdir / "post_history.csv"
            metrics = tmpdir / "post_metrics.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"

            history.write_text(
                "published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate\n"
                "2026-06-01,Da thiếu nước nên làm gì?,Hook A,education,reach,https://example.com/1,1200,0.05\n"
                "2026-06-02,Da thiếu nước nên làm gì?,Hook B,education,reach,https://example.com/2,900,0.04\n"
                "2026-06-03,Khi nào cần soi da?,Hook C,trust,lead,https://example.com/3,1500,0.07\n",
                encoding="utf-8",
            )
            metrics.write_text(
                "published_at,topic,pillar,objective,reach,engagements,leads\n"
                "2026-06-01,Da thiếu nước nên làm gì?,education,reach,1200,60,2\n"
                "2026-06-03,Khi nào cần soi da?,trust,lead,1500,90,8\n"
                "2026-06-04,Routine phục hồi da,education,lead,1700,130,11\n",
                encoding="utf-8",
            )
            comments.write_text(
                "created_at,source,message\n"
                "2026-06-05,comment,Da thiếu nước thì nên bắt đầu từ đâu?\n"
                "2026-06-05,inbox,Chi phí soi da là bao nhiêu?\n",
                encoding="utf-8",
            )
            campaign.write_text(
                json.dumps(
                    {
                        "campaign_focus": ["soi da", "phục hồi da treatment"],
                        "priority_objective": "lead",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            store = LocalSheetStore(calendar_csv=tmpdir / "calendar.csv", history_csv=history, metrics_csv=metrics)
            result = EvalTool().run_all(
                profile=profile,
                store=store,
                comment_csv=comments,
                campaign_notes_file=campaign,
                start_date="2026-06-20",
            )

            self.assertEqual(result["summary"]["total"], 4)
            self.assertEqual(result["summary"]["failed"], 0)
            self.assertEqual(result["summary"]["passed"], 4)
            self.assertGreaterEqual(result["summary"]["score"], 1.0)
            checks = {item["name"]: item for item in result["checks"]}
            self.assertTrue(checks["research"]["passed"])
            self.assertTrue(checks["planner"]["passed"])
            self.assertTrue(checks["writer"]["passed"])
            self.assertTrue(checks["verifier"]["passed"])
            self.assertIn("lead", " ".join(checks["research"]["details"]).lower())
            self.assertIn("campaign focus", " ".join(checks["planner"]["details"]).lower())
            self.assertIn("cta", " ".join(checks["writer"]["details"]).lower())
            self.assertIn("missing cta", " ".join(checks["verifier"]["details"]).lower())


if __name__ == "__main__":
    unittest.main()
