"""Runtime pipeline construction and orchestration helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fanpage_agent.agents.analyst import AnalystAgent
from fanpage_agent.agents.community import CommunityAgent
from fanpage_agent.agents.designer import DesignerAgent
from fanpage_agent.agents.orchestrator import OrchestratorAgent
from fanpage_agent.agents.publisher import PublisherAgent
from fanpage_agent.agents.researcher import ResearchAgent
from fanpage_agent.agents.strategist import StrategistAgent
from fanpage_agent.agents.writer import WriterAgent
from fanpage_agent.audit.auditor import AuditManager
from fanpage_agent.config import Settings
from fanpage_agent.core.bus import AgentBus
from fanpage_agent.core.harness import AgentHarness
from fanpage_agent.core.types import ActionPriority, AgentRole, AgentTask
from fanpage_agent.memory import PerformanceMemory


def _load_pages() -> list[dict[str, Any]]:
    """Load page configs from Settings when available."""
    try:
        settings = Settings()
        if hasattr(settings, "pages") and settings.pages:
            return [dict(page) for page in settings.pages]
    except Exception:
        pass
    return [{"page_id": "main"}]


def create_pipeline(
    data_dir: str | Path = "data/agent",
    brand_id: str = "skincare_genz",
    enable_llm: bool = True,
    pages: list[dict[str, Any]] | None = None,
) -> OrchestratorAgent:
    """Build a ready-to-run orchestrator with all runtime agents wired."""
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    if pages is None:
        pages = _load_pages()

    page_ids = [page.get("page_id", "main") for page in pages]
    memory = PerformanceMemory(db_path=data_path / "memory.db")

    llm: Any = None
    if enable_llm:
        try:
            from fanpage_agent.adapters.llm_adapter import LLMAdapter as _RealLLM

            llm = _RealLLM()
        except Exception as exc:
            print(f"⚠️ LLM init failed (falling back templates): {exc}")

    default_page_id = page_ids[0] if page_ids else None

    researcher = ResearchAgent(config={}, llm=llm)
    strategist = StrategistAgent(
        config={},
        performance_memory=memory,
        brand_id=brand_id,
        llm=llm,
    )
    writer = WriterAgent(
        config={},
        brand_id=brand_id,
        default_variants=2,
        llm=llm,
        memory_dir=str(data_path),
    )
    designer = DesignerAgent(config={})
    community = CommunityAgent(
        config={},
        llm=llm,
        data_dir=str(data_path),
        default_page_id=default_page_id,
    )

    fb_adapter = None
    try:
        from fanpage_agent.adapters.fb_adapter import FacebookAdapter

        fb_adapter = FacebookAdapter()
        community._fb = fb_adapter
    except Exception as exc:
        print(f"⚠️ FB adapter init failed (community fetch disabled): {exc}")

    publisher = PublisherAgent(
        config={},
        performance_memory=memory,
        default_page_id=default_page_id,
    )
    if fb_adapter:
        publisher._fb = fb_adapter

    analyst = AnalystAgent(
        config={},
        performance_memory=memory,
    )

    audit_manager = AuditManager(db_dir=str(data_path))
    bus = AgentBus(harness=AgentHarness(audit_manager=audit_manager))

    orchestrator = OrchestratorAgent(
        config={},
        bus=bus,
        state_path=data_path / "state.json",
        page_ids=page_ids,
    )
    orchestrator.register_all(
        [
            researcher,
            strategist,
            writer,
            designer,
            community,
            publisher,
            analyst,
        ]
    )
    return orchestrator


def run_tick(
    data_dir: str | Path = "data/agent",
    brand_id: str = "skincare_genz",
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a single pipeline tick."""
    orchestrator = create_pipeline(data_dir=data_dir, brand_id=brand_id, pages=pages)
    result = orchestrator.process(
        AgentTask(
            id="cli-tick",
            target=AgentRole.ORCHESTRATOR,
            action="tick",
            priority=ActionPriority.HIGH,
        )
    )
    return result.data if result.success else {"error": result.error, "success": False}


def run_status(
    data_dir: str | Path = "data/agent",
    brand_id: str = "skincare_genz",
) -> dict[str, Any]:
    """Get pipeline status."""
    orchestrator = create_pipeline(data_dir=data_dir, brand_id=brand_id)
    result = orchestrator.process(
        AgentTask(
            id="cli-status",
            target=AgentRole.ORCHESTRATOR,
            action="status",
        )
    )
    return result.data if result.success else {"error": result.error, "success": False}
