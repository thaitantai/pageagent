import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.models import TrendItem
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
            self.assertGreater(brief.confidence_score, 0)
            self.assertTrue(any(item.source == "post_metrics" for item in brief.evidence))
            self.assertTrue(any(item.source == "comment_inbox" for item in brief.evidence))
            self.assertTrue(brief.quality_warnings)
            self.assertTrue(brief.topic_scores)
            self.assertGreaterEqual(brief.topic_scores[0].total_score, brief.topic_scores[-1].total_score)
            self.assertTrue(any(item.topic == "soi da" for item in brief.topic_scores))
            self.assertTrue(any(item.duplication_risk > 0.8 for item in brief.topic_scores))

    def test_build_brief_enriches_with_trend_analyzer(self) -> None:
        """ResearchBrief chứa trend_keywords và trend_clusters khi có TrendAnalyzer."""
        mock_scraper = MagicMock()
        mock_scraper.fetch_all.return_value = [
            TrendItem(title="Cách chọn kem dưỡng ẩm cho da dầu", source="VnExpress"),
            TrendItem(title="Chống nắng mùa hè đúng cách", source="24h"),
            TrendItem(title="Retinol có nên dùng hàng ngày không", source="Afamily"),
            TrendItem(title="Trị mụn hiệu quả với BHA", source="VnExpress"),
            TrendItem(title="Dưỡng ẩm sâu cho da khô", source="24h"),
        ]

        from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer

        service = ResearchService(trend_scraper=mock_scraper, trend_analyzer=TrendAnalyzer([]))
        store = MagicMock()
        store.read_post_history.return_value = []
        store.read_post_metrics.return_value = []

        brief = service.build_brief(store=store)

        self.assertGreater(len(brief.trend_keywords), 0)
        self.assertGreater(len(brief.trend_clusters), 0)
        # trend_keywords should contain some of the words from trend titles
        trend_words_flat = set(brief.trend_keywords)
        common = trend_words_flat & {"dưỡng", "ẩm", "kem", "chống", "nắng", "mụn", "da"}
        self.assertGreater(len(common), 0)
        # recommendations should mention trend data
        trend_recs = [r for r in brief.recommendations if "trend" in r.lower() or "keyword" in r.lower() or "cluster" in r.lower()]
        self.assertGreater(len(trend_recs), 0)

    def test_build_brief_skips_trend_analyzer_when_not_configured(self) -> None:
        """Không crash khi không có TrendAnalyzer."""
        mock_scraper = MagicMock()
        mock_scraper.fetch_all.return_value = [
            TrendItem(title="Test title", source="Test"),
        ]

        service = ResearchService(trend_scraper=mock_scraper)
        store = MagicMock()
        store.read_post_history.return_value = []
        store.read_post_metrics.return_value = []

        brief = service.build_brief(store=store)
        self.assertEqual(brief.trend_keywords, [])
        self.assertEqual(brief.trend_clusters, {})


if __name__ == "__main__":
    unittest.main()
