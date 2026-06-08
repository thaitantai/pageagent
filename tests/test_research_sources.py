import json
import tempfile
import unittest
from pathlib import Path

from fanpage_agent.models import ResearchSource
from fanpage_agent.scraping.source_collector import ScraplingSourceCollector
from fanpage_agent.tools.research.research_packet import build_research_packet
from fanpage_agent.tools.research.research_sources import SourceRegistry


class FakePage:
    status = 200

    def get_all_text(self):
        return "Clinical skin analysis guidance and treatment evidence. " * 3

    def css(self, selector):
        class Result:
            def get(self):
                return "Clinical Skin Analysis"

        return Result()


class FakeFetcher:
    calls = 0

    @staticmethod
    def get(url: str, timeout: int = 15):
        FakeFetcher.calls += 1
        return FakePage()


class ResearchSourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeFetcher.calls = 0

    def test_source_registry_filters_by_page_and_topic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_file = Path(tmp) / "sources.json"
            registry_file.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "source_id": "derm-01",
                                "name": "Derm Clinic Blog",
                                "source_type": "website",
                                "url": "https://example.com/derm",
                                "topics": ["soi da", "phuc hoi da"],
                                "allowed_pages": ["spa-main"],
                                "trust_score": 0.9,
                                "notes": "Clinical skincare education.",
                            },
                            {
                                "source_id": "ads-01",
                                "name": "Low Trust Ads Blog",
                                "topics": ["ads"],
                                "trust_score": 0.2,
                            },
                            {
                                "source_id": "disabled-01",
                                "name": "Disabled Source",
                                "topics": ["soi da"],
                                "enabled": False,
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            documents = SourceRegistry.from_file(registry_file).to_documents(
                page_id="spa-main",
                topics=["soi da"],
            )

        self.assertEqual([item.source_id for item in documents], ["derm-01"])
        self.assertEqual(documents[0].source_name, "Derm Clinic Blog")
        self.assertEqual(documents[0].trust_score, 0.9)

    def test_source_registry_matches_topic_phrases_from_live_page_config(self) -> None:
        registry = SourceRegistry([
            ResearchSource(source_id="derm-01", name="Derm Clinic Blog", topics=["soi da"], trust_score=0.9),
        ])

        selected = registry.select(topics=["soi da cham soc da"])

        self.assertEqual([item.source_id for item in selected], ["derm-01"])

    def test_research_packet_includes_registry_documents_as_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            history = tmpdir / "post_history.csv"
            metrics = tmpdir / "post_metrics.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"
            calendar = tmpdir / "calendar.csv"
            registry_file = tmpdir / "sources.json"

            history.write_text(
                "published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate\n"
                "2026-06-01,Khi nào cần soi da?,Hook,education,lead,https://example.com/1,1200,0.05\n",
                encoding="utf-8",
            )
            metrics.write_text(
                "published_at,topic,pillar,objective,reach,engagements,leads\n"
                "2026-06-01,Khi nào cần soi da?,education,lead,1200,80,7\n",
                encoding="utf-8",
            )
            comments.write_text("created_at,source,message\n", encoding="utf-8")
            campaign.write_text(json.dumps({"campaign_focus": ["soi da"]}), encoding="utf-8")
            calendar.write_text("date,topic,pillar,objective,status\n", encoding="utf-8")
            registry_file.write_text(
                json.dumps(
                    [
                        {
                            "source_id": "derm-01",
                            "name": "Derm Clinic Blog",
                            "source_type": "website",
                            "url": "https://example.com/derm",
                            "topics": ["soi da"],
                            "allowed_pages": ["spa-main"],
                            "trust_score": 0.95,
                            "notes": "Evidence about skin analysis.",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            packet = build_research_packet(
                history_file=history,
                metrics_file=metrics,
                comment_file=comments,
                campaign_file=campaign,
                calendar_file=calendar,
                job_id="test-research",
                page_id="spa-main",
                page_context={"page_id": "spa-main", "topic_focus": ["soi da"]},
                source_registry_file=registry_file,
                fetch_external_trends=False,
            )

        self.assertEqual(packet.brief.source_documents[0].source_id, "derm-01")
        self.assertTrue(any(item.source_id == "derm-01" for item in packet.brief.evidence))
        self.assertGreater(packet.brief.confidence_score, 0.6)

    def test_research_packet_accepts_string_topic_focus_for_live_page_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            history = tmpdir / "post_history.csv"
            metrics = tmpdir / "post_metrics.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"
            calendar = tmpdir / "calendar.csv"
            registry_file = tmpdir / "sources.json"

            history.write_text("published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate\n", encoding="utf-8")
            metrics.write_text("published_at,topic,pillar,objective,reach,engagements,leads\n", encoding="utf-8")
            comments.write_text("created_at,source,message\n", encoding="utf-8")
            campaign.write_text(json.dumps({"campaign_focus": ["soi da"]}), encoding="utf-8")
            calendar.write_text("date,topic,pillar,objective,status\n", encoding="utf-8")
            registry_file.write_text(
                json.dumps([
                    {
                        "source_id": "derm-01",
                        "name": "Derm Clinic Blog",
                        "url": "https://example.com/derm",
                        "topics": ["soi da"],
                        "allowed_pages": ["spa-main"],
                        "trust_score": 0.95,
                    }
                ]),
                encoding="utf-8",
            )

            packet = build_research_packet(
                history_file=history,
                metrics_file=metrics,
                comment_file=comments,
                campaign_file=campaign,
                calendar_file=calendar,
                page_id="spa-main",
                page_context={"page_id": "spa-main", "topic_focus": "soi da"},
                source_registry_file=registry_file,
                fetch_external_trends=False,
            )

        self.assertEqual(packet.brief.source_documents[0].source_id, "derm-01")

    def test_scrapling_source_collector_fetches_and_caches_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = ResearchSource(
                source_id="derm-01",
                name="Derm Clinic Blog",
                url="https://example.com/derm",
                topics=["soi da"],
                trust_score=0.95,
            )
            collector = ScraplingSourceCollector(cache_dir=tmp, fetcher=FakeFetcher)

            first = collector.collect([source])
            second = collector.collect([source])

        self.assertEqual(FakeFetcher.calls, 1)
        self.assertEqual(first[0].title, "Clinical Skin Analysis")
        self.assertIn("Clinical skin analysis", first[0].content)
        self.assertEqual(second[0].source_id, "derm-01")
        self.assertEqual(second[0].metadata["fetch_status"], "ok")

    def test_research_packet_can_fetch_registry_sources_with_scrapling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            history = tmpdir / "post_history.csv"
            metrics = tmpdir / "post_metrics.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"
            calendar = tmpdir / "calendar.csv"
            registry_file = tmpdir / "sources.json"

            history.write_text("published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate\n", encoding="utf-8")
            metrics.write_text("published_at,topic,pillar,objective,reach,engagements,leads\n", encoding="utf-8")
            comments.write_text("created_at,source,message\n", encoding="utf-8")
            campaign.write_text(json.dumps({"campaign_focus": ["soi da"]}), encoding="utf-8")
            calendar.write_text("date,topic,pillar,objective,status\n", encoding="utf-8")
            registry_file.write_text(
                json.dumps([
                    {
                        "source_id": "derm-01",
                        "name": "Derm Clinic Blog",
                        "url": "https://example.com/derm",
                        "topics": ["soi da"],
                        "trust_score": 0.95,
                    }
                ]),
                encoding="utf-8",
            )

            from unittest.mock import patch

            with patch("fanpage_agent.scraping.source_collector.Fetcher", FakeFetcher):
                packet = build_research_packet(
                    history_file=history,
                    metrics_file=metrics,
                    comment_file=comments,
                    campaign_file=campaign,
                    calendar_file=calendar,
                    page_context={"topic_focus": ["soi da"]},
                    source_registry_file=registry_file,
                    fetch_source_documents=True,
                    source_cache_dir=tmpdir / "cache",
                    fetch_external_trends=False,
                )

        self.assertEqual(packet.brief.source_documents[0].title, "Clinical Skin Analysis")
        self.assertEqual(packet.brief.source_documents[0].metadata["fetch_status"], "ok")


if __name__ == "__main__":
    unittest.main()
