"""V2 main entry point — wires all agents and starts the pipeline.

Supports multi-page: reads ``pages`` from config (``Settings`` / ``config.py``)
and passes them to the orchestrator for round-robin page cycling.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from fanpage_agent_v2.audit.auditor import AuditManager
from fanpage_agent_v2.core.bus import AgentBus
from fanpage_agent_v2.core.harness import AgentHarness
from fanpage_agent_v2.core.types import AgentRole, AgentTask, ActionPriority
from fanpage_agent_v2.agents.orchestrator import OrchestratorAgent
from fanpage_agent_v2.agents.strategist import StrategistAgent
from fanpage_agent_v2.agents.writer import WriterAgent
from fanpage_agent_v2.agents.designer import DesignerAgent
from fanpage_agent_v2.agents.community import CommunityAgent
from fanpage_agent_v2.agents.analyst import AnalystAgent
from fanpage_agent_v2.agents.publisher import PublisherAgent
from fanpage_agent_v2.agents.researcher import ResearchAgent
from fanpage_agent_v2.memory.performance import PerformanceMemory


def _load_pages() -> list[dict[str, Any]]:
    """Load page configs from Settings if available."""
    try:
        from config import Settings

        settings = Settings()
        if hasattr(settings, "pages") and settings.pages:
            return [dict(p) for p in settings.pages]
    except Exception:
        pass
    # Fallback: single "main" page
    return [{"page_id": "main"}]


def create_pipeline(
    data_dir: str | Path = "data/v2",
    brand_id: str = "skincare_genz",
    enable_llm: bool = True,
    pages: list[dict[str, Any]] | None = None,
) -> OrchestratorAgent:
    """Create and wire up the full V2 pipeline.

    Args:
        data_dir: Data directory for state/memory.
        brand_id: Brand identifier.
        enable_llm: If True, initialise LLM adapter for agents.
        pages: List of page config dicts. Each must have at least ``page_id``.
               If None, loads from ``config.Settings.pages`` or defaults to ``["main"]``.

    Returns a ready-to-run OrchestratorAgent with all agents registered.
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    if pages is None:
        pages = _load_pages()

    page_ids = [p.get("page_id", "main") for p in pages]

    # ── Memory layer ────────────────────────────────────────────
    memory = PerformanceMemory(db_path=data_path / "memory.db")

    # ── LLM adapter (optional) ──────────────────────────────────
    llm: Any = None
    if enable_llm:
        try:
            from fanpage_agent_v2.adapters.llm_adapter import LLMAdapter as _RealLLM

            llm = _RealLLM()
        except Exception as e:
            print(f"⚠️  LLM init failed (falling back to templates): {e}")

    # First page_id is the "default" for agents that need one
    default_page_id = page_ids[0] if page_ids else None

    # ── Agents ──────────────────────────────────────────────────
    researcher = ResearchAgent(
        config={},
        llm=llm,
    )
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

    # ── Facebook Adapter (shared across agents that need it) ─────
    try:
        from fanpage_agent_v2.adapters.fb_adapter import FacebookAdapter

        fb_adapter = FacebookAdapter()
        # Inject FB adapter into agents that need live Facebook data
        community._fb = fb_adapter
    except Exception as e:
        print(f"⚠️  FB adapter init failed (community fetch disabled): {e}")
        fb_adapter = None

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

    # ── Bus / harness ───────────────────────────────────────────
    audit_manager = AuditManager(db_dir=str(data_path))
    bus = AgentBus(harness=AgentHarness(audit_manager=audit_manager))

    # ── Orchestrator ────────────────────────────────────────────
    orchestrator = OrchestratorAgent(
        config={},
        bus=bus,
        state_path=data_path / "state.json",
        page_ids=page_ids,
    )

    orchestrator.register_all([
        researcher, strategist, writer, designer, community, publisher, analyst,
    ])

    return orchestrator


def run_tick(
    data_dir: str | Path = "data/v2",
    brand_id: str = "skincare_genz",
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a single V2 pipeline tick."""
    orchestrator = create_pipeline(data_dir=data_dir, brand_id=brand_id, pages=pages)
    result = orchestrator.process(AgentTask(
        id="cli-tick",
        target=AgentRole.ORCHESTRATOR,
        action="tick",
        priority=ActionPriority.HIGH,
    ))
    return result.data if result.success else {"error": result.error, "success": False}


def run_status(
    data_dir: str | Path = "data/v2",
    brand_id: str = "skincare_genz",
) -> dict[str, Any]:
    """Get V2 pipeline status."""
    orchestrator = create_pipeline(data_dir=data_dir, brand_id=brand_id)
    result = orchestrator.process(AgentTask(
        id="cli-status",
        target=AgentRole.ORCHESTRATOR,
        action="status",
    ))
    return result.data if result.success else {"error": result.error, "success": False}


def cli() -> None:
    """CLI entry point for V2."""
    import argparse

    parser = argparse.ArgumentParser(description="Fanpage Agent V2")
    parser.add_argument("action", choices=["tick", "status", "daemon", "backup", "restore", "list-backups", "check-db"],
                       help="Action to perform")
    parser.add_argument("--data-dir", default="data/v2",
                       help="V2 data directory")
    parser.add_argument("--brand-id", default="skincare_genz",
                       help="Brand identifier")
    parser.add_argument("--interval", type=int, default=7200,
                       help="Daemon interval (seconds, default 7200=2h)")
    parser.add_argument("--backup-idx", type=int, default=1,
                       help="Backup index for restore (1=most recent)")
    parser.add_argument("--keep", type=int, default=7,
                       help="Number of backup copies to keep (default: 7)")

    args = parser.parse_args()

    if args.action == "tick":
        result = run_tick(data_dir=args.data_dir, brand_id=args.brand_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "status":
        result = run_status(data_dir=args.data_dir, brand_id=args.brand_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "backup":
        _run_backup(data_dir=args.data_dir, keep=args.keep)

    elif args.action == "restore":
        _run_restore(data_dir=args.data_dir, backup_idx=args.backup_idx)

    elif args.action == "list-backups":
        _run_list_backups(data_dir=args.data_dir)

    elif args.action == "check-db":
        _run_check_db(data_dir=args.data_dir)

    elif args.action == "daemon":
        pages = _load_pages()
        print(f"🔁 V2 daemon starting — tick every {args.interval}s")
        print(f"📂 Data dir: {args.data_dir}")
        print(f"🏷️  Brand: {args.brand_id}")
        print(f"📄 Pages: {[p.get('page_id') for p in pages]}")
        print(f"💾 Auto-backup every {6 * args.interval // 3600}h (every 6 ticks)")
        print("─" * 40)
        orchestrator = create_pipeline(data_dir=args.data_dir, brand_id=args.brand_id, pages=pages)
        tick_count = 0
        while True:
            result = orchestrator.process(AgentTask(
                id=f"daemon-tick-{int(time.time())}",
                target=AgentRole.ORCHESTRATOR,
                action="tick",
                priority=ActionPriority.HIGH,
            ))
            tick_count += 1
            status = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] tick: {'✅ ok' if result.success else '❌ fail'} " \
                     f"({result.metrics.get('elapsed_ms', 0)}ms)"

            # Auto-backup every 6 ticks (~12h at 2h interval)
            if tick_count % 6 == 0:
                try:
                    memory = PerformanceMemory(Path(args.data_dir) / "memory.db")
                    path = memory.backup(keep=args.keep)
                    status += f" | 💾 backed up ({path})"
                except Exception as e:
                    status += f" | ⚠️ backup failed: {e}"

            print(status)
            sys.stdout.flush()
            time.sleep(args.interval)


# ── CLI helper: backup ──────────────────────────────────────────


def _run_backup(data_dir: str, keep: int = 7) -> None:
    from fanpage_agent_v2.memory.performance import PerformanceMemory
    memory = PerformanceMemory(Path(data_dir) / "memory.db")
    path = memory.backup(keep=keep)
    print(json.dumps({
        "status": "ok",
        "backup_path": str(path),
        "backups_kept": keep,
        "available": memory.list_backups(),
    }, ensure_ascii=False, indent=2))


def _run_restore(data_dir: str, backup_idx: int = 1) -> None:
    from fanpage_agent_v2.memory.performance import PerformanceMemory, BackupError
    memory = PerformanceMemory(Path(data_dir) / "memory.db")
    try:
        memory.restore(backup_idx=backup_idx)
        print(json.dumps({
            "status": "ok",
            "restored_from": f"backup #{backup_idx}",
            "db_path": str(memory.db_path),
        }, ensure_ascii=False, indent=2))
    except BackupError as e:
        print(json.dumps({
            "status": "error",
            "error": str(e),
            "available": memory.list_backups(),
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


def _run_list_backups(data_dir: str) -> None:
    from fanpage_agent_v2.memory.performance import PerformanceMemory
    memory = PerformanceMemory(Path(data_dir) / "memory.db")
    backups = memory.list_backups()
    print(json.dumps({
        "status": "ok",
        "count": len(backups),
        "backups": backups,
    }, ensure_ascii=False, indent=2))


def _run_check_db(data_dir: str) -> None:
    from fanpage_agent_v2.memory.performance import PerformanceMemory
    memory = PerformanceMemory(Path(data_dir) / "memory.db")
    errors = memory.integrity_check()
    if errors:
        print(json.dumps({
            "status": "error",
            "integrity_errors": errors,
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps({
        "status": "ok",
        "integrity": "passed",
        "db_path": str(memory.db_path),
        "total_posts": memory._total_posts(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
