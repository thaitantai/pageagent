"""CLI helpers for research packet and competitor-learning operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fanpage_agent.config import Settings


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
    from fanpage_agent.adapters.page_registry import PageRegistry
    from fanpage_agent.tools.research.research_packet import (
        build_research_packet,
        save_research_packet,
    )

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
    from fanpage_agent.adapters.page_registry import PageRegistry

    registry = PageRegistry(Settings.from_env())
    pages = registry.list_pages()
    packet_dir = Path(output_dir)
    packets: list[dict[str, Any]] = []

    for packet_file in sorted(
        packet_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        try:
            payload = json.loads(packet_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        packet_page_id = str(payload.get("page_id", ""))
        if page_id and packet_page_id != page_id:
            continue

        brief = payload.get("brief", {}) if isinstance(payload.get("brief"), dict) else {}
        packets.append(
            {
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
            }
        )
        if len(packets) >= limit:
            break

    print(
        json.dumps(
            {
                "status": "ok",
                "page_filter": page_id or "all",
                "pages": pages,
                "research_packets_dir": str(packet_dir),
                "research_packets": packets,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _run_competitor_learn(
    competitor_names: list[str] | None = None,
    auto_discover: bool = False,
    show_summary: bool = False,
    promote_min_score: float = 3.0,
    no_save: bool = False,
    data_dir: str = "data/agent",
) -> None:
    from fanpage_agent.adapters.sqlite_store import UnifiedStore
    from fanpage_agent.tools.research.competitor_learning_engine import (
        CompetitorLearningEngine,
    )
    from fanpage_agent.tools.research.competitor_page_discovery import (
        CompetitorPageDiscoveryTool,
    )

    store = UnifiedStore(db_path=str(Path(data_dir) / "agent.db"))
    discovery_tool = CompetitorPageDiscoveryTool()
    engine = CompetitorLearningEngine(
        discovery_tool=discovery_tool,
        store=store,
    )

    if show_summary:
        print(json.dumps(engine.get_learning_summary(), ensure_ascii=False, indent=2))
        return

    if auto_discover:
        result = engine.scan_auto_discover(min_score=promote_min_score)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    names = competitor_names or [c["name"] for c in store.list_competitors(active_only=True)]
    if not names:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "No competitor names provided and no tracked competitors in DB. "
                    "Use --competitor-names 'Name1' 'Name2'",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    result = engine.scan(
        competitor_names=names,
        save_snapshot=not no_save,
        discover_new=not no_save,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
