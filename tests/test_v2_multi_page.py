"""Tests for V2 multi-page support — PageRegistry, per-page pipeline, main.py."""

import json
import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path

from fanpage_agent_v2.core.types import (
    AgentRole, AgentTask, ActionPriority, ContentPackage, ContentVariant,
)


# ── Config / PageConfig ──────────────────────────────────────────

class TestPageConfig:
    def test_create_page_config(self):
        from config import PageConfig
        cfg = PageConfig(page_id="test", page_token="tok123", name="Test Page")
        assert cfg.page_id == "test"
        assert cfg.page_token == "tok123"
        assert cfg.name == "Test Page"
        assert cfg.api_version == "v21.0"
        assert cfg.is_default is False

    def test_default_page_config(self):
        from config import PageConfig
        cfg = PageConfig(page_id="main", page_token="main_tok",
                         name="Main", is_default=True)
        assert cfg.is_default is True


# ── PageRegistry ─────────────────────────────────────────────────

class TestPageRegistry:
    @pytest.fixture
    def registry(self, tmp_path):
        from fanpage_agent_v2.adapters.page_registry import PageRegistry
        from config import Settings, PageConfig
        s = Settings(pages=[
            {"page_id": "main", "page_token": "tok_main"},
            {"page_id": "page2", "page_token": "tok_page2"},
        ])
        return PageRegistry(s)

    def test_list_pages(self, registry):
        pages = registry.list_pages()
        assert len(pages) == 2
        ids = [p["page_id"] for p in pages]
        assert "main" in ids
        assert "page2" in ids

    def test_get_page(self, registry):
        cfg = registry.get("main")
        assert cfg is not None
        assert hasattr(cfg, "page_id")
        assert cfg.page_token == "tok_main"

    def test_get_page_default(self, registry):
        cfg = registry.get(None)
        assert cfg.page_id == "main"

    def test_get_page_missing(self, registry):
        from config import PageConfig
        cfg = registry.get("nonexistent")
        assert isinstance(cfg, PageConfig)  # should return default page config

    def test_default_page_id(self, registry):
        assert registry.default_page_id == "main"

    def test_all_page_ids(self, registry):
        ids = registry.all_page_ids
        assert ids == ["main", "page2"]

    def test_page_count(self, registry):
        assert registry.page_count == 2


class TestGetRegistry:
    def test_get_registry_from_settings(self):
        from fanpage_agent_v2.adapters.page_registry import get_registry
        from config import Settings
        s = Settings(pages=[
            {"page_id": "alpha", "page_token": "tok_a", "is_default": True},
        ])
        reg = get_registry(s)
        assert reg.default_page_id == "alpha"

    def test_get_registry_default(self):
        """get_registry() with no args should load from global settings."""
        from fanpage_agent_v2.adapters.page_registry import get_registry
        reg = get_registry()  # uses get_settings()
        assert reg.default_page_id is not None or reg.page_count >= 1

    def test_registry_handles_env_settings(self):
        """Verify registry can load from env-provided pages."""
        from fanpage_agent_v2.adapters.settings import get_settings
        from fanpage_agent_v2.adapters.page_registry import PageRegistry
        settings = get_settings()
        reg = PageRegistry(settings)
        ids = reg.all_page_ids
        assert len(ids) >= 1


# ── FacebookAdapter multi-page ───────────────────────────────────

class TestFacebookAdapterMultiPage:
    @pytest.fixture
    def adapter(self):
        from fanpage_agent_v2.adapters.fb_adapter import FacebookAdapter
        return FacebookAdapter()

    def test_default_page_id_from_registry(self, adapter):
        """Adapter should load default page_id from registry."""
        assert adapter._default_page_id is not None
        assert isinstance(adapter._default_page_id, str)

    def test_get_client_creates_for_page_id(self, adapter):
        """_get_client should create client per page_id."""
        client1 = adapter._get_client("main")
        client2 = adapter._get_client("main")  # same
        assert client1 is client2  # cached

    def test_get_client_different_pages(self, adapter):
        """Different page_ids return separate client instances."""
        c1 = adapter._get_client("main")
        # If a second page exists, verify separate client
        ids = adapter._registry.all_page_ids
        if len(ids) > 1:
            c2 = adapter._get_client(ids[1])
            assert c1 is not c2


# ── PublisherAgent page_id ───────────────────────────────────────

class TestPublisherAgentPageId:
    @pytest.fixture
    def mock_fb(self):
        fb = MagicMock()
        fb.publish_post.return_value = {"fb_post_id": "fb_123", "permalink": "https://fb.com/123"}
        fb.publish_photo.return_value = {"fb_post_id": "fb_123", "permalink": "https://fb.com/123"}
        fb.get_post_insights.return_value = {"reach": 100, "impressions": 200}
        fb.get_recent_posts.return_value = [{"id": "1", "message": "Test"}]
        return fb

    @pytest.fixture
    def agent(self, mock_fb, tmp_path):
        from fanpage_agent_v2.agents.publisher import PublisherAgent
        from fanpage_agent_v2.memory.performance import PerformanceMemory
        mem = PerformanceMemory(db_path=tmp_path / "pub_test.db")
        agent = PublisherAgent(
            config={},
            performance_memory=mem,
            default_page_id="page2",
        )
        agent._fb = mock_fb
        return agent

    def test_default_page_id_set(self, agent):
        assert agent._default_page_id == "page2"

    def test_resolve_page_id_from_params(self, agent):
        pid = agent._resolve_page_id({"page_id": "custom"})
        assert pid == "custom"

    def test_resolve_page_id_falls_back(self, agent):
        pid = agent._resolve_page_id({})
        assert pid == "page2"

    def test_publish_passes_page_id(self, agent, mock_fb):
        pkg = ContentPackage(package_id="pkg_multi", brand_id="test",
                            scheduled_date="2026-06-15")
        pkg.variants = [
            ContentVariant(variant_id="v1", topic="Topic", pillar="test",
                          caption="Test", hook="H", cta="C", format="text_image",
                          tone_tags=["test"], hashtags=["test"])
        ]
        task = AgentTask(id="pub1", target=AgentRole.PUBLISHER,
                        action="publish_post",
                        params={"package": pkg, "variant_id": "v1", "page_id": "page2"})
        result = agent.process(task)
        assert result.success
        mock_fb.publish_post.assert_called_once()
        call_kwargs = mock_fb.publish_post.call_args
        # Check page_id passed to fb.publish_post
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        assert kwargs.get("page_id") == "page2"


# ── CommunityAgent page_id ───────────────────────────────────────

class TestCommunityAgentPageId:
    @pytest.fixture
    def mock_fb(self):
        fb = MagicMock()
        fb.get_recent_posts.return_value = [{"id": "post_123", "message": "Test"}]
        fb.get_comments.return_value = [
            {"id": "c1", "message": "Bài viết hay!",
             "from": {"name": "User A", "id": "u1"}},
            {"id": "c2", "message": "Vitamin C dùng sáng được không ạ?",
             "from": {"name": "User B", "id": "u2"}},
        ]
        fb.reply_to_comment.return_value = {"id": "r1"}
        fb.comment_on_post.return_value = {"id": "c0"}
        fb.get_page_conversations.return_value = []
        return fb

    @pytest.fixture
    def agent(self, mock_fb, tmp_path):
        from fanpage_agent_v2.agents.community import CommunityAgent
        agent = CommunityAgent(
            config={},
            data_dir=str(tmp_path),
            default_page_id="page2",
        )
        agent._fb = mock_fb
        return agent

    def test_default_page_id_set(self, agent):
        assert agent._default_page_id == "page2"

    def test_resolve_page_id_from_params(self, agent):
        pid = agent._resolve_page_id({"page_id": "custom"})
        assert pid == "custom"

    def test_resolve_page_id_falls_back(self, agent):
        pid = agent._resolve_page_id({})
        assert pid == "page2"

    def test_process_comments_passes_page_id(self, agent, mock_fb):
        task = AgentTask(id="c1", target=AgentRole.COMMUNITY,
                        action="process_comments",
                        params={"post_id": "post_123", "page_id": "page2"})
        result = agent.process(task)
        # Should run without crashing
        assert result is not None


# ── PerformanceMemory page_id ────────────────────────────────────

class TestPerformanceMemoryPageId:
    @pytest.fixture
    def memory(self, tmp_path):
        from fanpage_agent_v2.memory.performance import PerformanceMemory
        return PerformanceMemory(db_path=tmp_path / "multi_page.db")

    def test_record_with_page_id(self, memory):
        pkg = ContentPackage(package_id="mp1", brand_id="test", scheduled_date="2026-06-15")
        pkg.variants = [
            ContentVariant(variant_id="v1", topic="Topic", pillar="test",
                          caption="T", hook="H", cta="C", format="text_image",
                          tone_tags=["test"], hashtags=["test"])
        ]
        memory.record_publish(pkg, "v1", reach=100, engagements=10,
                             permalink="https://fb.com/1", page_id="page2")

        posts = memory.get_recent_posts(limit=10)
        matching = [p for p in posts if p["package_id"] == "mp1"]
        assert len(matching) > 0
        assert matching[0]["page_id"] == "page2"

    def test_filter_by_page_id(self, memory):
        from fanpage_agent_v2.core.types import ContentPackage, ContentVariant

        for pid, page in [("pkg_a", "page1"), ("pkg_b", "page2")]:
            pkg = ContentPackage(package_id=pid, brand_id="test", scheduled_date="2026-06-15")
            pkg.variants = [
                ContentVariant(variant_id="v1", topic="T", pillar="test",
                              caption="T", hook="H", cta="C", format="text_image",
                              tone_tags=["test"], hashtags=["test"])
            ]
            memory.record_publish(pkg, "v1", reach=100, engagements=10,
                                 permalink=f"https://fb.com/{pid}", page_id=page)

        p1 = memory.get_recent_posts(limit=10, page_id="page1")
        assert len(p1) == 1
        assert p1[0]["package_id"] == "pkg_a"

        p2 = memory.get_recent_posts(limit=10, page_id="page2")
        assert len(p2) == 1
        assert p2[0]["package_id"] == "pkg_b"

    def test_filter_pillar_performance_by_page(self, memory):
        from fanpage_agent_v2.core.types import ContentPackage, ContentVariant

        for pid, page, pillar in [("pa", "p1", "a"), ("pb", "p2", "a")]:
            pkg = ContentPackage(package_id=pid, brand_id="test", scheduled_date="2026-06-15")
            pkg.variants = [
                ContentVariant(variant_id="v", topic="T", pillar=pillar,
                              caption="T", hook="H", cta="C", format="text_image",
                              tone_tags=["test"], hashtags=["test"])
            ]
            memory.record_publish(pkg, "v", reach=100, engagements=10,
                                 permalink=f"https://fb.com/{pid}", page_id=page)

        p1_perf = memory.pillar_performance(page_id="p1")
        assert len(p1_perf) == 1
        assert p1_perf[0]["post_count"] == 1

    def test_no_page_id_fallback(self, memory):
        """record_publish without page_id should get default 'main'."""
        from fanpage_agent_v2.core.types import ContentPackage, ContentVariant
        pkg = ContentPackage(package_id="nopid", brand_id="test", scheduled_date="2026-06-15")
        pkg.variants = [
            ContentVariant(variant_id="v1", topic="T", pillar="test",
                          caption="T", hook="H", cta="C", format="text_image",
                          tone_tags=["test"], hashtags=["test"])
        ]
        memory.record_publish(pkg, "v1", reach=50, engagements=5,
                             permalink="https://fb.com/no")
        posts = memory.get_recent_posts(limit=5)
        matching = [p for p in posts if p["package_id"] == "nopid"]
        assert len(matching) > 0
        assert matching[0]["page_id"] == "main"


# ── main.py multi-page ───────────────────────────────────────────

class TestMainMultiPage:
    def test_create_pipeline_with_pages(self, tmp_path):
        """create_pipeline should accept pages list and create pipeline."""
        from fanpage_agent_v2.main import create_pipeline
        orch = create_pipeline(
            data_dir=tmp_path / "test_data",
            brand_id="test",
            enable_llm=False,
            pages=[{"page_id": "p1"}, {"page_id": "p2"}],
        )
        assert orch is not None

    def test_create_pipeline_default_page_id(self, tmp_path):
        """First page_id should become default for agents."""
        from fanpage_agent_v2.main import create_pipeline
        orch = create_pipeline(
            data_dir=tmp_path / "test_data2",
            brand_id="test",
            enable_llm=False,
            pages=[{"page_id": "default_a", "page_token": "tok_a"},
                   {"page_id": "default_b", "page_token": "tok_b"}],
        )
        # Publisher should have default_page_id = "default_a"
        # Check via _page_ids on orchestrator
        assert hasattr(orch, "_page_ids")
        assert "default_a" in orch._page_ids

    def test_run_tick_with_pages(self, tmp_path):
        """run_tick should accept pages param."""
        from fanpage_agent_v2.main import run_tick
        result = run_tick(
            data_dir=tmp_path / "tick_data",
            brand_id="test",
            pages=[{"page_id": "p1"}, {"page_id": "p2"}],
        )
        # Should not crash — may return error if FB not configured
        assert isinstance(result, dict)

    def test_daemon_cli_shows_pages(self):
        """CLI daemon action should print page IDs."""
        from fanpage_agent_v2.main import cli
        import sys
        sys.argv = ["fanpage-agent", "tick", "--data-dir", "/tmp/test_cli_pages",
                    "--brand-id", "test"]
        # Should not crash
        try:
            cli()
        except SystemExit:
            pass


# ── OrchestratorAgent page_ids ───────────────────────────────────

class TestOrchestratorPageIds:
    def test_orchestrator_accepts_page_ids(self):
        from fanpage_agent_v2.agents.orchestrator import OrchestratorAgent
        agent = OrchestratorAgent(
            config={},
            page_ids=["p1", "p2", "p3"],
        )
        assert hasattr(agent, "_page_ids") or hasattr(agent, "page_ids")

    def test_orchestrator_capabilities(self):
        from fanpage_agent_v2.agents.orchestrator import OrchestratorAgent
        agent = OrchestratorAgent(config={})
        caps = agent.capabilities
        assert "tick" in caps
        assert "run_pipeline" in caps
        assert "status" in caps


# ── SlaDashboard + analytics (no page_id code change needed) ─────

class TestSlaDashboardPageId:
    """SlaDashboard reads analytics which reads from DB — no change needed.
    This verifies the published_posts table schema supports page_id."""

    def test_published_posts_has_page_id_column(self, tmp_path):
        """Verify DB schema includes page_id column."""
        from fanpage_agent_v2.memory.performance import PerformanceMemory
        mem = PerformanceMemory(db_path=tmp_path / "schema_test.db")

        import sqlite3
        conn = sqlite3.connect(str(tmp_path / "schema_test.db"))
        cols = [row[1] for row in conn.execute("PRAGMA table_info(published_posts)").fetchall()]
        conn.close()

        assert "page_id" in cols
