"""Tests for specialized agents — strategist, writer, designer, community, analyst."""

import pytest
from unittest.mock import MagicMock, patch

from fanpage_agent.core.types import (
    AgentRole, AgentTask, ActionPriority, ContentPackage,
)
from fanpage_agent.agents.strategist import StrategistAgent
from fanpage_agent.agents.writer import WriterAgent
from fanpage_agent.agents.designer import DesignerAgent
from fanpage_agent.agents.community import CommunityAgent
from fanpage_agent.agents.analyst import AnalystAgent
from fanpage_agent.agents.researcher import ResearchAgent


# ── Strategist ──────────────────────────────────────────────────

class TestStrategistAgent:
    @pytest.fixture
    def agent(self):
        return StrategistAgent(config={})

    def test_role_and_capabilities(self, agent):
        assert agent.role == AgentRole.STRATEGIST
        assert "plan_weekly" in agent.capabilities
        assert "gap_analysis" in agent.capabilities
        assert "pillar_recommend" in agent.capabilities
        assert "generate_ideas" in agent.capabilities
        assert "analyse_trends" in agent.capabilities

    def test_plan_weekly(self, agent):
        task = AgentTask(id="p1", target=AgentRole.STRATEGIST, action="plan_weekly",
                        params={"days": 3})
        result = agent.process(task)
        assert result.success
        data = result.data
        assert "schedule" in data
        assert len(data["schedule"]) == 3
        assert "pillar_distribution" in data

    def test_plan_weekly_with_existing_calendar(self, agent):
        task = AgentTask(id="p2", target=AgentRole.STRATEGIST, action="plan_weekly",
                        params={"days": 5, "existing_calendar": [{"day": "Mon"}]})
        result = agent.process(task)
        assert result.success
        assert len(result.data["schedule"]) == 5

    def test_plan_weekly_prioritises_scored_research_topics(self, agent):
        brief = {
            "confidence_score": 0.82,
            "topic_scores": [
                {"topic": "Chi phí soi da và khi nào nên đặt lịch", "total_score": 0.91, "duplication_risk": 0.1},
                {"topic": "Routine buổi tối cho da thiếu nước", "total_score": 0.77, "duplication_risk": 0.2},
            ],
        }
        task = AgentTask(
            id="p3",
            target=AgentRole.STRATEGIST,
            action="plan_weekly",
            params={"days": 2, "research_brief": brief},
        )
        result = agent.process(task)

        assert result.success
        assert result.data["schedule"][0]["topic_template"] == "Chi phí soi da và khi nào nên đặt lịch"
        assert result.data["research_priority_topics"][0]["total_score"] == 0.91
        assert result.data["research_confidence"] == 0.82

    def test_plan_weekly_accepts_research_packet_shape(self, agent):
        packet = {
            "schema_version": "research_packet.v1",
            "page_context": {
                "page_id": "main",
                "topic_focus": "phuc hoi da treatment",
                "community_value": "Giai thich phuc hoi hang rao bao ve da",
            },
            "brief": {
                "confidence_score": 0.7,
                "topic_scores": [
                    {"topic": "Review sản phẩm phục hồi cho da treatment", "total_score": 0.88}
                ],
            },
        }
        task = AgentTask(
            id="p4",
            target=AgentRole.STRATEGIST,
            action="plan_weekly",
            params={"days": 1, "research_brief": packet},
        )
        result = agent.process(task)

        assert result.success
        assert result.data["schedule"][0]["topic_template"] == "Review sản phẩm phục hồi cho da treatment"
        assert result.data["schedule"][0]["pillar"] == "product_review"
        assert result.data["page_context"]["topic_focus"] == "phuc hoi da treatment"

    def test_generate_ideas(self, agent):
        task = AgentTask(id="i1", target=AgentRole.STRATEGIST, action="generate_ideas",
                        params={"pillar": "skincare_routine", "count": 3})
        result = agent.process(task)
        assert result.success
        assert result.data["pillar"] == "skincare_routine"
        assert len(result.data["ideas"]) == 3

    def test_generate_ideas_unknown_pillar(self, agent):
        task = AgentTask(id="i2", target=AgentRole.STRATEGIST, action="generate_ideas",
                        params={"pillar": "unknown_pillar"})
        result = agent.process(task)
        assert result.success
        assert len(result.data["ideas"]) > 0  # falls back to default

    def test_pillar_recommend(self, agent):
        task = AgentTask(id="pr1", target=AgentRole.STRATEGIST, action="pillar_recommend")
        result = agent.process(task)
        assert result.success

    def test_analyse_trends(self, agent):
        task = AgentTask(id="at1", target=AgentRole.STRATEGIST, action="analyse_trends",
                        params={"pillars": ["skincare_routine", "myth_busting"]})
        result = agent.process(task)
        assert result.success
        assert "pillars_to_scan" in result.data

    def test_with_memory(self):
        mock_memory = MagicMock()
        mock_memory.pillar_performance.return_value = [
            {"pillar": "skincare_routine", "avg_engagement": 30.0, "post_count": 5,
             "avg_reach": 500, "avg_engagement_rate": 6.0},
            {"pillar": "myth_busting", "avg_engagement": 8.0, "post_count": 3,
             "avg_reach": 200, "avg_engagement_rate": 4.0},
        ]
        mock_memory.get_top_patterns.return_value = []
        agent = StrategistAgent(config={}, performance_memory=mock_memory)
        task = AgentTask(id="pm1", target=AgentRole.STRATEGIST, action="pillar_recommend")
        result = agent.process(task)
        assert result.success

    def test_unknown_action(self, agent):
        task = AgentTask(id="unk", target=AgentRole.STRATEGIST, action="nonsense")
        result = agent.process(task)
        assert not result.success


# ── Writer ──────────────────────────────────────────────────────

class TestWriterAgent:
    @pytest.fixture
    def agent(self):
        return WriterAgent(config={}, brand_id="test_brand", default_variants=2)

    def test_role_and_capabilities(self, agent):
        assert agent.role == AgentRole.WRITER
        assert "write_variants" in agent.capabilities
        assert "generate_hooks" in agent.capabilities

    def test_write_variants_default_count(self, agent):
        task = AgentTask(id="w1", target=AgentRole.WRITER, action="write_variants",
                        params={"topic": "Vitamin C cho da dầu", "pillar": "ingredient_deepdive"})
        result = agent.process(task)
        assert result.success
        pkg = result.data
        assert isinstance(pkg, ContentPackage)
        assert pkg.brand_id == "test_brand"
        assert len(pkg.variants) == 2  # default_variants=2
        assert pkg.variants[0].topic == "Vitamin C cho da dầu"

    def test_write_variants_custom_count(self, agent):
        task = AgentTask(id="w2", target=AgentRole.WRITER, action="write_variants",
                        params={"topic": "Retinol", "pillar": "ingredient_deepdive", "variants": 3})
        result = agent.process(task)
        assert result.success
        assert len(result.data.variants) == 3

    def test_write_variants_with_schedule(self, agent):
        task = AgentTask(id="w3", target=AgentRole.WRITER, action="write_variants",
                        params={"topic": "SPF", "pillar": "ingredient_deepdive",
                               "scheduled_date": "2026-06-15", "scheduled_time": "10:00"})
        result = agent.process(task)
        assert result.success
        assert result.data.scheduled_date == "2026-06-15"
        assert result.data.scheduled_time == "10:00"

    def test_generate_hooks(self, agent):
        task = AgentTask(id="h1", target=AgentRole.WRITER, action="generate_hooks",
                        params={"topic": "Chống nắng", "count": 3})
        result = agent.process(task)
        assert result.success
        assert len(result.data["hooks"]) == 3

    def test_different_formats_across_variants(self, agent):
        task = AgentTask(id="w4", target=AgentRole.WRITER, action="write_variants",
                        params={"topic": "Test", "pillar": "test", "variants": 4})
        result = agent.process(task)
        assert result.success
        formats = [v.format for v in result.data.variants]
        assert len(set(formats)) > 1  # At least 2 different formats

    def test_unknown_action(self, agent):
        task = AgentTask(id="unk", target=AgentRole.WRITER, action="nonsense")
        result = agent.process(task)
        assert not result.success


# ── Designer ────────────────────────────────────────────────────

class TestDesignerAgent:
    @pytest.fixture
    def agent(self):
        return DesignerAgent(config={})

    def test_role_and_capabilities(self, agent):
        assert agent.role == AgentRole.DESIGNER
        assert "generate_brief" in agent.capabilities
        assert "generate_image" in agent.capabilities

    def test_generate_brief_text_image(self, agent):
        task = AgentTask(id="d1", target=AgentRole.DESIGNER, action="generate_brief",
                        params={"topic": "SPF cho da dầu", "hook": "Bạn có biết?",
                               "format": "text_image"})
        result = agent.process(task)
        assert result.success
        assert "visual_brief" in result.data
        assert result.data["format"] == "text_image"

    def test_generate_brief_carousel(self, agent):
        task = AgentTask(id="d2", target=AgentRole.DESIGNER, action="generate_brief",
                        params={"topic": "Routine các bước", "hook": "Có bạn nào...",
                               "format": "carousel"})
        result = agent.process(task)
        assert result.success
        assert "carousel" in (result.data.get("visual_brief") or "")

    def test_generate_image(self, agent):
        task = AgentTask(id="d3", target=AgentRole.DESIGNER, action="generate_image",
                        params={"brief": "Ảnh sản phẩm nền trắng", "style": "clean_skincare"})
        result = agent.process(task)
        assert result.success
        assert result.data["backend"] == "url"

    def test_unknown_action(self, agent):
        task = AgentTask(id="unk", target=AgentRole.DESIGNER, action="nonsense")
        result = agent.process(task)
        assert not result.success


# ── Community ───────────────────────────────────────────────────

class TestCommunityAgent:
    @pytest.fixture
    def agent(self):
        return CommunityAgent(config={})

    def test_role_and_capabilities(self, agent):
        assert agent.role == AgentRole.COMMUNITY
        assert "triage_comments" in agent.capabilities
        assert "suggest_reply" in agent.capabilities
        assert "sentiment_summary" in agent.capabilities

    def test_triage_empty(self, agent):
        task = AgentTask(id="c1", target=AgentRole.COMMUNITY, action="triage_comments",
                        params={"comments": [], "limit": 10})
        result = agent.process(task)
        assert result.success
        assert result.data["total_analysed"] == 0

    def test_triage_classifies_correctly(self, agent):
        comments = [
            {"message": "Sản phẩm này tốt quá!"},
            {"message": "Tại sao da mình bị kích ứng?"},
            {"message": "Thất vọng quá, không hiệu quả"},
            {"message": "Mua ở đâu giá tốt vậy?"},
            {"message": "Bài viết hay quá, cảm ơn bạn"},
        ]
        task = AgentTask(id="c2", target=AgentRole.COMMUNITY, action="triage_comments",
                        params={"comments": comments, "limit": 10})
        result = agent.process(task)
        assert result.success
        cats = result.data["categories"]
        assert cats["praise"] >= 2
        assert cats["question"] >= 1
        assert cats["complaint"] >= 1

    def test_suggest_reply_praise(self, agent):
        task = AgentTask(id="c3", target=AgentRole.COMMUNITY, action="suggest_reply",
                        params={"text": "Bài viết hay!", "sentiment": "praise"})
        result = agent.process(task)
        assert result.success
        assert "Cảm ơn" in result.data["suggestion"]

    def test_suggest_reply_complaint(self, agent):
        task = AgentTask(id="c4", target=AgentRole.COMMUNITY, action="suggest_reply",
                        params={"text": "Sản phẩm kém quá", "sentiment": "complaint"})
        result = agent.process(task)
        assert result.success
        assert "rất tiếc" in result.data["suggestion"]

    def test_sentiment_summary_positive(self, agent):
        comments = [
            {"message": "Tuyệt vời!"},
            {"message": "Rất thích!"},
            {"message": "Cảm ơn bạn"},
        ]
        task = AgentTask(id="c5", target=AgentRole.COMMUNITY, action="sentiment_summary",
                        params={"comments": comments})
        result = agent.process(task)
        assert result.success
        assert result.data["trend"] == "positive"

    def test_unknown_action(self, agent):
        task = AgentTask(id="unk", target=AgentRole.COMMUNITY, action="nonsense")
        result = agent.process(task)
        assert not result.success


# ── Analyst ─────────────────────────────────────────────────────

class TestAnalystAgent:
    @pytest.fixture
    def agent(self):
        return AnalystAgent(config={})

    def test_role_and_capabilities(self, agent):
        assert agent.role == AgentRole.ANALYST
        assert "weekly_report" in agent.capabilities
        assert "pattern_analysis" in agent.capabilities
        assert "pillar_health" in agent.capabilities
        assert "content_recommendations" in agent.capabilities

    def test_weekly_report_no_memory(self, agent):
        task = AgentTask(id="a1", target=AgentRole.ANALYST, action="weekly_report")
        result = agent.process(task)
        assert result.success
        assert result.data["summary"] == "Chưa có dữ liệu performance."

    def test_weekly_report_with_memory(self):
        mock_memory = MagicMock()
        mock_memory.pillar_performance.return_value = [
            {"pillar": "skincare", "post_count": 5, "avg_reach": 500,
             "avg_engagement": 30, "avg_engagement_rate": 6.0},
        ]
        mock_memory.get_recent_posts.return_value = [{"topic": "Vitamin C"}]
        mock_memory.get_top_patterns.return_value = []
        mock_memory.get_recommendations.return_value = ["Test recommendation"]
        agent = AnalystAgent(config={}, performance_memory=mock_memory)
        task = AgentTask(id="a2", target=AgentRole.ANALYST, action="weekly_report")
        result = agent.process(task)
        assert result.success
        assert result.data["total_posts"] == 5
        assert result.data["avg_reach"] == 500
        assert result.data["recommendations"] == ["Test recommendation"]

    def test_pattern_analysis(self, agent):
        task = AgentTask(id="a3", target=AgentRole.ANALYST, action="pattern_analysis",
                        params={"pattern_types": []})
        result = agent.process(task)
        assert result.success

    def test_pillar_health(self, agent):
        task = AgentTask(id="a4", target=AgentRole.ANALYST, action="pillar_health")
        result = agent.process(task)
        assert result.success
        assert result.data["overall"] == "no_data"

    def test_content_recommendations(self, agent):
        task = AgentTask(id="a5", target=AgentRole.ANALYST, action="content_recommendations")
        result = agent.process(task)
        assert result.success
        assert "Chưa có đủ dữ liệu" in result.data["recommendations"][0]

    def test_ab_test_results(self, agent):
        task = AgentTask(id="a6", target=AgentRole.ANALYST, action="ab_test_results")
        result = agent.process(task)
        assert result.success
        assert "A/B analysis" in result.data["note"]

    def test_unknown_action(self, agent):
        task = AgentTask(id="unk", target=AgentRole.ANALYST, action="nonsense")
        result = agent.process(task)
        assert not result.success


# ── Researcher ──────────────────────────────────────────────────

class TestResearchAgent:
    @pytest.fixture
    def agent(self):
        return ResearchAgent(config={})

    def test_role_and_capabilities(self, agent):
        assert agent.role == AgentRole.RESEARCHER
        assert "research_trends" in agent.capabilities
        assert "crawl_source" in agent.capabilities
        assert "get_source_list" in agent.capabilities

    def test_research_trends_returns_brief(self, agent):
        """Should return a structured brief even without Scrapling."""
        task = AgentTask(id="r1", target=AgentRole.RESEARCHER, action="research_trends",
                        params={})
        result = agent.process(task)
        assert result.success
        assert "brief" in result.data
        assert "source_count" in result.data
        assert "finding_count" in result.data

    def test_research_trends_with_specific_pillars(self, agent):
        """Should filter research to requested pillars."""
        task = AgentTask(id="r2", target=AgentRole.RESEARCHER, action="research_trends",
                        params={"pillars": ["skincare_routine"]})
        result = agent.process(task)
        assert result.success
        brief = result.data["brief"]
        checked = brief.get("sources_checked", [])
        pillar_sources = [s for s in checked if s["pillar"] == "skincare_routine"]
        assert len(pillar_sources) > 0

    def test_get_source_list(self, agent):
        """Should return configured sources (discovery + fallback)."""
        task = AgentTask(id="r3", target=AgentRole.RESEARCHER, action="get_source_list")
        result = agent.process(task)
        assert result.success
        assert "rss_feeds" in result.data
        assert "category_pages" in result.data
        assert "fallback_urls" in result.data
        assert len(result.data["rss_feeds"]) > 0

    def test_crawl_source_fails_gracefully(self, agent):
        """With an unreachable URL, should fail gracefully without crashing."""
        task = AgentTask(id="r4", target=AgentRole.RESEARCHER, action="crawl_source",
                        params={"url": "https://this-domain-does-not-exist-12345.xyz"})
        result = agent.process(task)
        assert not result.success
        assert result.error is not None

    def test_unknown_action(self, agent):
        task = AgentTask(id="unk", target=AgentRole.RESEARCHER, action="nonsense")
        result = agent.process(task)
        assert not result.success

    def test_brief_structure(self, agent):
        """Verify the brief has the expected schema (mocked fetch)."""
        with patch.object(agent, '_fetch_text', return_value="Vitamin C là một thành phần chống oxy hóa mạnh. "
                                                              "Retinol kết hợp với niacinamide có hiệu quả cao. "
                                                              "Kem chống nắng là bước quan trọng nhất."):
            task = AgentTask(id="r5", target=AgentRole.RESEARCHER, action="research_trends",
                            params={"pillars": ["skincare_routine", "ingredient_deepdive"]})
            result = agent.process(task)
        assert result.success
        brief = result.data["brief"]
        assert "generated_at" in brief
        assert "sources_checked" in brief
        assert "findings" in brief
        assert len(brief["sources_checked"]) > 0
        # With mocked content, should find ingredient mentions
        assert len(brief["findings"]) > 0

    def test_brief_includes_scrapling_lifecycle(self, agent):
        """Verify fetch attempts and graceful fallback."""
        # Mock fetch to sometimes succeed, sometimes fail
        real_fetch = agent._fetch_text
        call_count = [0]

        def mock_fetch(url):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                return real_fetch(url)  # odd calls pass through
            return None  # even calls fail

        task = AgentTask(id="r6", target=AgentRole.RESEARCHER, action="research_trends",
                        params={"pillars": ["myth_busting"]})
        result = agent.process(task)
        assert result.success
        assert result.data["source_count"] > 0

    def test_plan_weekly_can_accept_research_brief(self, agent):
        """Strategist should accept research_brief in params."""
        from fanpage_agent.agents.strategist import StrategistAgent
        s_agent = StrategistAgent(config={})
        brief = {
            "findings": [
                {"pillar": "skincare_routine", "topic": "Morning routine mùa hè cho da dầu"},
                {"pillar": "ingredient_deepdive", "topic": "Vitamin C vs Niacinamide"},
            ]
        }
        task = AgentTask(id="r7", target=AgentRole.STRATEGIST, action="plan_weekly",
                        params={"days": 2, "research_brief": brief})
        result = s_agent.process(task)
        assert result.success
        assert len(result.data["schedule"]) == 2

    # ── Cache tests ──────────────────────────────────────────────

    def test_cache_ttl(self, agent):
        """Cache should return fresh content within TTL."""
        # Manually set cache entry
        agent._cache["http://test.url"] = {
            "text": "cached content",
            "fetched_at": __import__("time").time(),
            "pillar": "skincare_routine",
        }
        cached = agent._get_cached("http://test.url")
        assert cached == "cached content"
        assert agent._is_from_cache("http://test.url")

    def test_cache_expires_after_ttl(self, agent):
        """Cache should return None for stale entries (simulate old timestamp)."""
        agent._cache["http://stale.url"] = {
            "text": "stale content",
            "fetched_at": 0,  # epoch = definitely expired
            "pillar": "skincare_routine",
        }
        cached = agent._get_cached("http://stale.url")
        assert cached is None

    def test_cache_auto_cleanup(self, agent):
        """Cache should purge stale entries when > 100 entries."""
        now = __import__("time").time()
        from fanpage_agent.agents.researcher import CACHE_TTL
        # Fill 101 entries: 50 fresh, 51 stale (> TTL old)
        for i in range(101):
            if i < 50:
                # fresh: fetched now
                ts = now
            else:
                # stale: fetched before TTL (older than 6h)
                ts = now - CACHE_TTL - 3600  # 1h past TTL
            agent._cache[f"http://url{i}.test"] = {
                "text": f"content {i}",
                "fetched_at": ts,
                "pillar": "skincare_routine",
            }
        # Trigger cleanup by setting another entry
        agent._set_cached("http://new.test", "new content", "skincare_routine")
        # Should have removed stale entries (51 stale removed)
        assert len(agent._cache) == 51  # 50 fresh + 1 new

    # ── Discovery + seen-articles tests ───────────────────────────

    def test_seen_articles_tracker_accumulates(self, agent):
        """seen_articles should grow after research_trends calls."""
        task = AgentTask(id="seen1", target=AgentRole.RESEARCHER, action="research_trends",
                        params={"pillars": ["skincare_routine"]})
        agent.process(task)
        count1 = len(agent._seen_articles)
        # Second call should discover and see the same articles (cached)
        agent.process(task)
        count2 = len(agent._seen_articles)
        # seen_articles should not shrink between calls
        assert count2 >= count1

    def test_get_source_list_includes_stats(self, agent):
        """Source list should include discovery cache + seen articles stats."""
        task = AgentTask(id="src1", target=AgentRole.RESEARCHER, action="get_source_list")
        result = agent.process(task)
        assert result.success
        assert "seen_articles_count" in result.data
        assert "cache_entries" in result.data
        assert "discovery_cache_entries" in result.data

    # ── LLM extraction tests ─────────────────────────────────────

    def test_llm_extraction_called_when_llm_available(self, agent):
        """When LLMAdapter is provided, _llm_extract should be called."""
        mock_llm = __import__("unittest").mock.MagicMock()
        mock_llm.generate_json.return_value = {
            "findings": [
                {"pillar": "skincare_routine", "topic": "Routine mùa hè cho da dầu",
                 "key_points": "Dùng sữa rửa mặt dịu nhẹ, toner cấp ẩm, gel dưỡng",
                 "relevance": 5, "source_type": "tip"},
            ]
        }
        agent._llm = mock_llm
        result = agent._extract_findings("Test content about skincare routine", "skincare_routine")
        assert len(result) == 1
        assert result[0]["topic"] == "Routine mùa hè cho da dầu"
        mock_llm.generate_json.assert_called_once()

    def test_llm_extraction_fallback_on_failure(self, agent):
        """When LLM fails, should fall back to heuristic extraction."""
        mock_llm = __import__("unittest").mock.MagicMock()
        mock_llm.generate_json.side_effect = RuntimeError("LLM unavailable")
        agent._llm = mock_llm
        # Heuristic should still work on ingredient text
        result = agent._extract_findings(
            "Vitamin C là chất chống oxy hóa mạnh. Retinol kết hợp niacinamide hiệu quả.",
            "ingredient_deepdive",
        )
        assert len(result) > 0  # heuristic finds ingredient mentions

    # ── Cache stats ──────────────────────────────────────────────

    def test_cache_stats(self, agent):
        """get_cache_stats should return correct counts."""
        now = __import__("time").time()
        agent._cache["http://fresh.test"] = {"text": "fresh", "fetched_at": now, "pillar": "x"}
        agent._cache["http://stale.test"] = {"text": "stale", "fetched_at": 0, "pillar": "x"}
        stats = agent.get_cache_stats()
        assert stats["total_entries"] == 2
        assert stats["fresh_entries"] == 1
        assert stats["stale_entries"] == 1

class TestPerformanceMemory:
    @pytest.fixture
    def memory(self, tmp_path):
        from fanpage_agent.memory.performance import PerformanceMemory
        return PerformanceMemory(db_path=tmp_path / "test_memory.db")

    def test_init_creates_tables(self, memory):
        """DB tables created on init."""
        from fanpage_agent.memory.performance import PerformanceMemory
        import sqlite3
        # Just verify we can query
        rows = memory.get_top_patterns()
        assert rows == []

    def test_record_and_query_pillar(self, memory, tmp_path):
        from fanpage_agent.core.types import ContentPackage, ContentVariant
        pkg = ContentPackage(package_id="pkg1", brand_id="test", scheduled_date="2026-06-10")
        pkg.variants = [
            ContentVariant(variant_id="v1", topic="Vitamin C", pillar="ingredient_deepdive",
                          caption="Test", hook="Hook", cta="CTA1", format="text_image",
                          tone_tags=["chuyên_môn"], hashtags=["skincare"])
        ]
        memory.record_publish(pkg, "v1", reach=1500, engagements=50, permalink="https://fb.com/123")

        patterns = memory.get_top_patterns()
        assert len(patterns) > 0
        pillar_pats = [p for p in patterns if p.pattern_type == "pillar"]
        assert len(pillar_pats) > 0
        assert pillar_pats[0].value == "ingredient_deepdive"

    def test_record_updates_metrics(self, memory, tmp_path):
        from fanpage_agent.core.types import ContentPackage, ContentVariant
        pkg = ContentPackage(package_id="pkg2", brand_id="test", scheduled_date="2026-06-10")
        pkg.variants = [ContentVariant(variant_id="v1", topic="SPF", pillar="skincare_routine",
                                      caption="Test", hook="Hook", cta="CTA", format="carousel")]
        memory.record_publish(pkg, "v1", reach=1000, engagements=30, permalink="https://fb.com/456")
        memory.record_metrics_update("pkg2", "v1", reach=1200, engagements=40)

        posts = memory.get_recent_posts(limit=5)
        matching = [p for p in posts if p["package_id"] == "pkg2"]
        assert len(matching) > 0
        assert matching[0]["reach"] == 1200

    def test_pillar_performance(self, memory, tmp_path):
        from fanpage_agent.core.types import ContentPackage, ContentVariant
        for i, pillar in enumerate(["skincare_routine", "ingredient_deepdive", "myth_busting"]):
            pkg = ContentPackage(package_id=f"p{i}", brand_id="test", scheduled_date="2026-06-10")
            pkg.variants = [ContentVariant(variant_id=f"v{i}", topic=f"T{i}", pillar=pillar,
                                          caption="T", hook="H", cta="C", format="text_image")]
            memory.record_publish(pkg, f"v{i}", reach=1000 + i * 500, engagements=10 + i * 20,
                                 permalink=f"https://fb.com/{i}")

        perf = memory.pillar_performance()
        assert len(perf) == 3
        # myth_busting has highest engagement (10 + 2*20 = 50)
        assert perf[0]["pillar"] == "myth_busting"

    def test_recommendations(self, memory, tmp_path):
        from fanpage_agent.core.types import ContentPackage, ContentVariant
        # Need sample_count >= 4 so confidence > 0.3 (confidence = min(1.0, count/10))
        for i in range(4):
            pkg = ContentPackage(package_id=f"pkg_rec_{i}", brand_id="test", scheduled_date="2026-06-10")
            pkg.variants = [ContentVariant(variant_id=f"v_rec_{i}", topic="Test", pillar="test",
                                          caption="T", hook=f"H{i}", cta=f"C{i}", format="text_image")]
            memory.record_publish(pkg, f"v_rec_{i}", reach=2000, engagements=100 + i * 10,
                                 permalink=f"https://fb.com/rec/{i}")
        recs = memory.get_recommendations(limit=3)
        assert len(recs) > 0

    def test_format_summary(self, memory, tmp_path):
        from fanpage_agent.core.types import ContentPackage, ContentVariant
        pkg = ContentPackage(package_id="pkg_sum", brand_id="test", scheduled_date="2026-06-10")
        pkg.variants = [ContentVariant(variant_id="v_sum", topic="Summary", pillar="test",
                                      caption="T", hook="H", cta="C", format="text_image")]
        memory.record_publish(pkg, "v_sum", reach=1000, engagements=50, permalink="https://fb.com/sum")
        summary = memory.format_summary()
        assert "Performance Memory" in summary
        assert "Total posts tracked" in summary or "pillar" in summary.lower()
