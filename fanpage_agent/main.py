"""Main entry point — wires all agents and starts the pipeline.

Supports multi-page: reads ``pages`` from config (``Settings`` / ``config.py``)
and passes them to the orchestrator for round-robin page cycling.
"""

from __future__ import annotations

import json
import sys
import time
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
from fanpage_agent.core.bus import AgentBus
from fanpage_agent.core.harness import AgentHarness
from fanpage_agent.core.types import ActionPriority, AgentRole, AgentTask
from fanpage_agent.legacy_cli import (
    DEFAULT_CALENDAR_FILE,
    DEFAULT_CAMPAIGN_FILE,
    DEFAULT_COMMENT_FILE,
    DEFAULT_HERMES_CRON_JOBS_FILE,
    DEFAULT_HERMES_SCRIPTS_DIR,
    DEFAULT_HISTORY_FILE,
    DEFAULT_METRICS_FILE,
    DEFAULT_TRIAGE_FILE,
    OPS_ARTIFACT_FRESHNESS_HOURS,
    ROOT_DIR,
    add_store_backend_arg,
    build_approval_audit_payload,
    build_calendar_store_payload,
    build_daily_artifacts,
    build_operator_digest_payload,
    build_research_brief,
    build_triage_store_payload,
)
from fanpage_agent.legacy_cli import EXPECTED_HERMES_CRON_JOBS as EXPECTED_HERMES_CRON_JOBS
from fanpage_agent.legacy_cli import (
    main as legacy_cli_main,
)
from fanpage_agent.memory import PerformanceMemory


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
    data_dir: str | Path = "data/agent",
    brand_id: str = "skincare_genz",
    enable_llm: bool = True,
    pages: list[dict[str, Any]] | None = None,
) -> OrchestratorAgent:
    """Create and wire up the full pipeline.

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
            from fanpage_agent.adapters.llm_adapter import LLMAdapter as _RealLLM

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
        from fanpage_agent.adapters.fb_adapter import FacebookAdapter

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
    data_dir: str | Path = "data/agent",
    brand_id: str = "skincare_genz",
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a single pipeline tick."""
    orchestrator = create_pipeline(data_dir=data_dir, brand_id=brand_id, pages=pages)
    result = orchestrator.process(AgentTask(
        id="cli-tick",
        target=AgentRole.ORCHESTRATOR,
        action="tick",
        priority=ActionPriority.HIGH,
    ))
    return result.data if result.success else {"error": result.error, "success": False}


def run_status(
    data_dir: str | Path = "data/agent",
    brand_id: str = "skincare_genz",
) -> dict[str, Any]:
    """Get pipeline status."""
    orchestrator = create_pipeline(data_dir=data_dir, brand_id=brand_id)
    result = orchestrator.process(AgentTask(
        id="cli-status",
        target=AgentRole.ORCHESTRATOR,
        action="status",
    ))
    return result.data if result.success else {"error": result.error, "success": False}


def cli() -> None:
    """CLI entry point."""
    import argparse

    from fanpage_agent.utils import ensure_utf8_stdio

    ensure_utf8_stdio()

    runtime_actions = {
        "tick", "status", "daemon", "backup", "restore", "list-backups",
        "check-db", "harness-status", "roadmap-status", "research-standalone",
        "page-status", "competitor-learn",
    }
    if len(sys.argv) > 1 and sys.argv[1] not in runtime_actions:
        raise SystemExit(legacy_cli_main())

    parser = argparse.ArgumentParser(description="Fanpage Agent")
    parser.add_argument(
        "action",
        choices=sorted(runtime_actions),
        help="Action to perform",
    )
    parser.add_argument("--data-dir", default="data/agent",
                       help="agent data directory")
    parser.add_argument("--brand-id", default="skincare_genz",
                       help="Brand identifier")
    parser.add_argument("--interval", type=int, default=7200,
                       help="Daemon interval (seconds, default 7200=2h)")
    parser.add_argument("--backup-idx", type=int, default=1,
                       help="Backup index for restore (1=most recent)")
    parser.add_argument("--keep", type=int, default=7,
                       help="Number of backup copies to keep (default: 7)")
    parser.add_argument("--limit", type=int, default=20,
                       help="Number of recent rows for status views")
    parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE),
                       help="post history CSV for research-standalone")
    parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE),
                       help="post metrics CSV for research-standalone")
    parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE),
                       help="comment inbox CSV for research-standalone")
    parser.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE),
                       help="campaign notes JSON for research-standalone")
    parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE),
                       help="calendar CSV for research-standalone")
    parser.add_argument("--output-dir", default="data/research_packets",
                       help="directory to write ResearchPacket JSON")
    parser.add_argument("--job-id",
                       help="optional stable job id for standalone research")
    parser.add_argument("--page-id",
                       help="page id whose profile should guide research/strategy")
    parser.add_argument("--source-registry-file",
                       help="JSON registry of trusted research sources")
    parser.add_argument("--fetch-source-documents", action="store_true",
                       help="fetch registry URLs with Scrapling and store extracted text")
    parser.add_argument("--source-cache-dir", default="data/research_source_cache",
                       help="cache directory for fetched source documents")
    parser.add_argument("--discover-sources", action="store_true",
                       help="discover new web source candidates from page topics")
    parser.add_argument("--max-discovered-sources", type=int, default=5,
                       help="maximum dynamic source candidates to include")
    parser.add_argument("--discover-product-topics", action="store_true",
                       help="derive topic candidates from page product/customer context")
    parser.add_argument("--max-product-topics", type=int, default=8,
                       help="maximum product-aware topic candidates to include")
    parser.add_argument("--no-external-trends", action="store_true",
                       help="skip external trend fetch for deterministic/offline runs")
    parser.add_argument("--competitor-names", nargs="*",
                       help="competitor names to scan (default: from DB tracked list)")
    parser.add_argument("--auto-discover", action="store_true",
                       help="run auto-discovery: scan candidates + promote")
    parser.add_argument("--show-summary", action="store_true",
                       help="show learning summary (no scan)")
    parser.add_argument("--promote-min-score", type=float, default=3.0,
                       help="minimum candidate score to auto-promote (default: 3.0)")
    parser.add_argument("--no-save", action="store_true",
                       help="dry run: don't save to DB")

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

    elif args.action == "harness-status":
        _run_harness_status(data_dir=args.data_dir, limit=args.limit)

    elif args.action == "roadmap-status":
        _run_roadmap_status()

    elif args.action == "research-standalone":
        _run_research_standalone(
            history_file=args.history_file,
            metrics_file=args.metrics_file,
            comment_file=args.comment_file,
            campaign_file=args.campaign_file,
            calendar_file=args.calendar_file,
            output_dir=args.output_dir,
            job_id=args.job_id,
            page_id=args.page_id,
            source_registry_file=args.source_registry_file,
            fetch_source_documents=args.fetch_source_documents,
            source_cache_dir=args.source_cache_dir,
            discover_sources=args.discover_sources,
            max_discovered_sources=args.max_discovered_sources,
            discover_product_topics=args.discover_product_topics,
            max_product_topics=args.max_product_topics,
            fetch_external_trends=not args.no_external_trends,
        )

    elif args.action == "page-status":
        _run_page_status(
            output_dir=args.output_dir,
            page_id=args.page_id,
            limit=args.limit,
        )

    elif args.action == "competitor-learn":
        _run_competitor_learn(
            competitor_names=args.competitor_names,
            auto_discover=args.auto_discover,
            show_summary=args.show_summary,
            promote_min_score=args.promote_min_score,
            no_save=args.no_save,
            data_dir=args.data_dir,
        )

    elif args.action == "daemon":
        pages = _load_pages()
        print(f"🔁 Agent daemon starting — tick every {args.interval}s")
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
    from fanpage_agent.memory import PerformanceMemory
    memory = PerformanceMemory(Path(data_dir) / "memory.db")
    path = memory.backup(keep=keep)
    print(json.dumps({
        "status": "ok",
        "backup_path": str(path),
        "backups_kept": keep,
        "available": memory.list_backups(),
    }, ensure_ascii=False, indent=2))


def _run_restore(data_dir: str, backup_idx: int = 1) -> None:
    from fanpage_agent.memory import BackupError, PerformanceMemory
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
    from fanpage_agent.memory import PerformanceMemory
    memory = PerformanceMemory(Path(data_dir) / "memory.db")
    backups = memory.list_backups()
    print(json.dumps({
        "status": "ok",
        "count": len(backups),
        "backups": backups,
    }, ensure_ascii=False, indent=2))


def _run_check_db(data_dir: str) -> None:
    from fanpage_agent.memory import PerformanceMemory
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


def _run_harness_status(data_dir: str, limit: int = 20) -> None:
    audit = AuditManager(db_dir=str(Path(data_dir)))
    entries = audit.list(source="AgentHarness", limit=limit)
    recent = [
        {
            "id": entry.id,
            "timestamp": entry.timestamp,
            "event_type": entry.event_type,
            "success": entry.success,
            "duration_ms": entry.duration_ms,
            "error": entry.error,
            "event_data": entry.event_data,
        }
        for entry in entries
    ]
    print(json.dumps({
        "status": "ok",
        "audit_db": str(Path(data_dir) / "audit.db"),
        "summary_24h": audit.summary(),
        "harness_events_total": audit.count(source="AgentHarness"),
        "recent": recent,
    }, ensure_ascii=False, indent=2))


def _run_research_standalone(
    history_file: str,
    metrics_file: str,
    comment_file: str | None,
    campaign_file: str | None,
    calendar_file: str,
    output_dir: str,
    job_id: str | None = None,
    page_id: str | None = None,
    source_registry_file: str | None = None,
    fetch_source_documents: bool = False,
    source_cache_dir: str | None = None,
    discover_sources: bool = False,
    max_discovered_sources: int = 5,
    discover_product_topics: bool = False,
    max_product_topics: int = 8,
    fetch_external_trends: bool = True,
) -> None:
    from config import Settings
    from fanpage_agent.adapters.page_registry import PageRegistry
    from fanpage_agent.tools.research.research_packet import build_research_packet, save_research_packet

    page_context = PageRegistry(Settings.from_env()).page_context(page_id)
    packet = build_research_packet(
        history_file=history_file,
        metrics_file=metrics_file,
        comment_file=comment_file,
        campaign_file=campaign_file,
        calendar_file=calendar_file,
        job_id=job_id,
        page_id=str(page_context.get("page_id", page_id or "")),
        page_context=page_context,
        source_registry_file=source_registry_file,
        fetch_source_documents=fetch_source_documents,
        source_cache_dir=source_cache_dir,
        discover_sources=discover_sources,
        max_discovered_sources=max_discovered_sources,
        discover_product_topics=discover_product_topics,
        max_product_topics=max_product_topics,
        fetch_external_trends=fetch_external_trends,
    )
    output_path = save_research_packet(packet, output_dir=output_dir)
    payload = packet.model_dump(mode="json")
    payload["output_file"] = str(output_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))



def _run_page_status(output_dir: str, page_id: str | None = None, limit: int = 20) -> None:
    from config import Settings
    from fanpage_agent.adapters.page_registry import PageRegistry

    registry = PageRegistry(Settings.from_env())
    pages = registry.list_pages()
    packet_dir = Path(output_dir)
    packets: list[dict[str, Any]] = []
    for packet_file in sorted(packet_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(packet_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        packet_page_id = str(payload.get("page_id", ""))
        if page_id and packet_page_id != page_id:
            continue
        brief = payload.get("brief", {}) if isinstance(payload.get("brief"), dict) else {}
        packets.append({
            "packet_id": payload.get("packet_id", ""),
            "job_id": payload.get("job_id", ""),
            "created_at": payload.get("created_at", ""),
            "status": payload.get("status", ""),
            "gate_reasons": payload.get("gate_reasons", []),
            "page_id": packet_page_id,
            "confidence_score": brief.get("confidence_score", 0),
            "quality_warning_count": len(brief.get("quality_warnings") or []),
            "top_topic": (brief.get("topic_scores") or [{}])[0].get("topic", ""),
            "evidence_count": len(brief.get("evidence") or []),
            "file": str(packet_file),
        })
        if len(packets) >= limit:
            break

    print(json.dumps({
        "status": "ok",
        "page_filter": page_id or "all",
        "pages": pages,
        "research_packets_dir": str(packet_dir),
        "research_packets": packets,
    }, ensure_ascii=False, indent=2))


def _run_roadmap_status() -> None:
    roadmap_path = Path(__file__).resolve().parent.parent / "docs" / "roadmap-next.md"
    phases: list[str] = []
    priority_items: list[str] = []
    progress_entries: list[str] = []
    phase_tasks: dict[str, list[str]] = {}
    section: str | None = None
    current_phase: str | None = None

    if roadmap_path.exists():
        for raw_line in roadmap_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("## Phase "):
                current_phase = line.removeprefix("## ").strip()
                phases.append(current_phase)
                phase_tasks.setdefault(current_phase, [])
                section = "phase"
            elif line == "Viec can lam:":
                section = "phase_tasks"
            elif line == "## Ưu tiên thực thi ngay":
                current_phase = None
                section = "priority"
            elif line == "## Tien do thuc thi":
                current_phase = None
                section = "progress"
            elif section == "phase_tasks" and current_phase and line.startswith("- "):
                phase_tasks[current_phase].append(line.removeprefix("- ").strip())
            elif section == "priority" and len(line) > 2 and line[0].isdigit() and line[1] == ".":
                priority_items.append(line)
            elif section == "progress" and line.startswith("- "):
                progress_entries.append(line.removeprefix("- ").strip())

    completed_text = " ".join(progress_entries).lower()
    phase_statuses: list[dict[str, Any]] = []
    for phase in phases:
        tasks = phase_tasks.get(phase, [])
        completed_tasks = [task for task in tasks if task.lower() in completed_text]
        phase_statuses.append({
            "phase": phase,
            "tasks_total": len(tasks),
            "tasks_confirmed_done": len(completed_tasks),
            "status": "done" if tasks and len(completed_tasks) == len(tasks) else "active",
            "remaining_tasks": [task for task in tasks if task not in completed_tasks],
        })

    active_phase = next((item for item in phase_statuses if item["status"] != "done"), None)
    if active_phase is None and phase_statuses:
        active_phase = phase_statuses[-1]

    print(json.dumps({
        "status": "ok",
        "roadmap": roadmap_path.as_posix(),
        "current_phase": active_phase["phase"] if active_phase else "Phase 1: Don dep nen tang va tang kha nang quan sat",
        "next_phase": next((phase for phase in phases if active_phase and phases.index(phase) > phases.index(active_phase["phase"])), None),
        "phases_total": len(phases),
        "phase_statuses": phase_statuses,
        "immediate_priorities": priority_items,
        "progress_entries": progress_entries,
        "next_recommended_actions": (active_phase or {}).get("remaining_tasks", [])[:3],
    }, ensure_ascii=False, indent=2))


def _run_competitor_learn(
    competitor_names: list[str] | None = None,
    auto_discover: bool = False,
    show_summary: bool = False,
    promote_min_score: float = 3.0,
    no_save: bool = False,
    data_dir: str = "data/agent",
) -> None:
    """competitor-learn CLI handler."""
    import os

    from fanpage_agent.adapters.sqlite_store import UnifiedStore
    from fanpage_agent.tools.research.competitor_learning_engine import (
        CompetitorLearningEngine,
    )
    from fanpage_agent.tools.research.competitor_page_discovery import (
        CompetitorPageDiscoveryTool,
    )

    # Build store path
    db_path = Path(data_dir) / "agent.db"

    store = UnifiedStore(db_path=str(db_path))
    discovery_tool = CompetitorPageDiscoveryTool()
    engine = CompetitorLearningEngine(
        discovery_tool=discovery_tool,
        store=store,
    )

    if show_summary:
        summary = engine.get_learning_summary()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if auto_discover:
        result = engine.scan_auto_discover(min_score=promote_min_score)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Scan with specific or all tracked competitors
    names = competitor_names or [
        c["name"] for c in store.list_competitors(active_only=True)
    ]
    if not names:
        print(json.dumps({
            "status": "error",
            "message": "No competitor names provided and no tracked competitors in DB. "
                       "Use --competitor-names 'Name1' 'Name2'",
        }, ensure_ascii=False, indent=2))
        return

    result = engine.scan(
        competitor_names=names,
        save_snapshot=not no_save,
        discover_new=not no_save,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
