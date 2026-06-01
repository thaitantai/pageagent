import json
import tempfile
import unittest
from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.services.research import ResearchService


class ResearchServiceTest(unittest.TestCase):
    def test_build_brief_combines_history_metrics_comments_and_campaign(self) -> None:
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
                "2026-06-05,inbox,Chi phí soi da là bao nhiêu?\n"
                "2026-06-06,comment,Da treatment bị khô thì xử lý sao?\n",
                encoding="utf-8",
            )
            campaign.write_text(
                json.dumps(
                    {
                        "campaign_focus": ["soi da", "phục hồi da treatment"],
                        "priority_objective": "lead",
                        "notes": ["Đẩy dịch vụ soi da trong 7 ngày tới"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            store = LocalSheetStore(calendar_csv=tmpdir / "calendar.csv", history_csv=history, metrics_csv=metrics)
            brief = ResearchService().build_brief(
                store=store,
                comment_csv=comments,
                campaign_notes_file=campaign,
            )

            self.assertIn("Da thiếu nước nên làm gì?", brief.overused_topics)
            self.assertEqual(brief.recommended_objectives[0], "lead")
            self.assertIn("Chi phí soi da là bao nhiêu?", brief.frequent_questions)
            self.assertIn("soi da", brief.campaign_focus)
            self.assertIn("Routine phục hồi da", brief.top_performing_topics)
            self.assertTrue(any("lead" in item.lower() for item in brief.recommendations))


if __name__ == "__main__":
    unittest.main()
