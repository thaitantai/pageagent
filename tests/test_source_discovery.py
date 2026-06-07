import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fanpage_agent.scraping.web_search import SearchResult
from fanpage_agent.services.research_packet import build_research_packet
from fanpage_agent.services.source_discovery import WebSourceDiscovery


class FakeSearchClient:
    def search(self, query: str, max_results: int = 5):
        return [
            SearchResult(
                title="Skin analysis guide for clinic customers",
                url="https://example.com/skin-analysis",
                snippet=f"Evidence and customer education about {query}",
            ),
            SearchResult(
                title="Unrelated travel deals",
                url="https://example.com/travel",
                snippet="Cheap flights and hotels",
            ),
        ][:max_results]


class SourceDiscoveryTest(unittest.TestCase):
    def test_web_source_discovery_returns_scored_candidates(self) -> None:
        discovery = WebSourceDiscovery(search_client=FakeSearchClient())

        candidates = discovery.discover(["skin analysis clinic"], max_candidates=2)

        self.assertEqual(candidates[0].status, "candidate")
        self.assertEqual(candidates[0].discovery_query, "skin analysis clinic")
        self.assertIn("web_search_candidate", candidates[0].reason_codes)
        self.assertGreater(candidates[0].relevance_score, candidates[1].relevance_score)

    def test_research_packet_can_discover_dynamic_source_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            history = tmpdir / "post_history.csv"
            metrics = tmpdir / "post_metrics.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"
            calendar = tmpdir / "calendar.csv"

            history.write_text("published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate\n", encoding="utf-8")
            metrics.write_text("published_at,topic,pillar,objective,reach,engagements,leads\n", encoding="utf-8")
            comments.write_text("created_at,source,message\n", encoding="utf-8")
            campaign.write_text(json.dumps({"campaign_focus": ["skin analysis"]}), encoding="utf-8")
            calendar.write_text("date,topic,pillar,objective,status\n", encoding="utf-8")

            with patch("fanpage_agent.services.source_discovery.WebSearchClient", return_value=FakeSearchClient()):
                packet = build_research_packet(
                    history_file=history,
                    metrics_file=metrics,
                    comment_file=comments,
                    campaign_file=campaign,
                    calendar_file=calendar,
                    page_context={"topic_focus": ["skin analysis clinic"]},
                    discover_sources=True,
                    max_discovered_sources=1,
                    fetch_external_trends=False,
                )

        self.assertEqual(len(packet.brief.source_candidates), 1)
        self.assertEqual(packet.brief.source_candidates[0].status, "candidate")
        self.assertIn("nguồn ứng viên mới", " ".join(packet.brief.recommendations))


if __name__ == "__main__":
    unittest.main()
