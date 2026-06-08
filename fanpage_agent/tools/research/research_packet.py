from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.models import ResearchPacket
from fanpage_agent.scraping.source_collector import ScraplingSourceCollector
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.tools.research.research_sources import SourceRegistry
from fanpage_agent.tools.research.source_discovery import WebSourceDiscovery

DEFAULT_RESEARCH_OUTPUT_DIR = Path("data/research_packets")


def build_research_packet(
    history_file: str | Path,
    metrics_file: str | Path,
    comment_file: str | Path | None = None,
    campaign_file: str | Path | None = None,
    calendar_file: str | Path = "data/content_calendar.csv",
    job_id: str | None = None,
    fetch_external_trends: bool = True,
    page_id: str | None = None,
    page_context: dict[str, object] | None = None,
    source_registry_file: str | Path | None = None,
    fetch_source_documents: bool = False,
    source_cache_dir: str | Path | None = None,
    discover_sources: bool = False,
    max_discovered_sources: int = 5,
    discover_product_topics: bool = False,
    max_product_topics: int = 8,
) -> ResearchPacket:
    store = LocalSheetStore(
        calendar_csv=calendar_file,
        history_csv=history_file,
        metrics_csv=metrics_file,
    )
    effective_page_context = page_context or {}
    topic_focus = effective_page_context.get("topic_focus", [])
    if isinstance(topic_focus, str):
        topic_focus = [topic_focus]
    elif not isinstance(topic_focus, list):
        topic_focus = []
    registry = SourceRegistry.from_file(source_registry_file)
    selected_sources = registry.select(
        page_id=page_id or str(effective_page_context.get("page_id", "")),
        topics=[str(item) for item in topic_focus],
    )
    if fetch_source_documents:
        registry_documents = ScraplingSourceCollector(cache_dir=source_cache_dir).collect(selected_sources)
    else:
        registry_documents = registry.to_documents(
            page_id=page_id or str(effective_page_context.get("page_id", "")),
            topics=[str(item) for item in topic_focus],
        )
    source_candidates = []
    if discover_sources:
        discovery_queries = [str(item) for item in topic_focus if str(item).strip()]
        if not discovery_queries:
            content_pillars = effective_page_context.get("content_pillars", [])
            discovery_queries = [str(item) for item in content_pillars if str(item).strip()] if isinstance(content_pillars, list) else []
        source_candidates = (
            WebSourceDiscovery().discover(queries=discovery_queries, max_candidates=max_discovered_sources)
            if discovery_queries
            else []
        )
    brief = ResearchTool().build_brief(
        store=store,
        comment_csv=comment_file,
        campaign_notes_file=campaign_file,
        fetch_external_trends=fetch_external_trends,
        source_documents=registry_documents,
        source_candidates=source_candidates,
        page_context=effective_page_context,
        discover_product_topics=discover_product_topics,
        max_product_topics=max_product_topics,
    )
    packet_job_id = job_id or f"research-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    status, gate_reasons, handoff_policy = research_handoff_policy(brief)
    return ResearchPacket(
        packet_id=f"rpkt-{uuid4().hex[:12]}",
        job_id=packet_job_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        gate_reasons=gate_reasons,
        handoff_policy=handoff_policy,
        page_id=page_id or str((page_context or {}).get("page_id", "")),
        page_context=page_context or {},
        source_files={
            "history_file": str(history_file),
            "metrics_file": str(metrics_file),
            "comment_file": str(comment_file or ""),
            "campaign_file": str(campaign_file or ""),
            "calendar_file": str(calendar_file),
            "source_registry_file": str(source_registry_file or ""),
            "source_cache_dir": str(source_cache_dir or ""),
            "discover_sources": str(discover_sources),
        },
        brief=brief,
    )


def save_research_packet(packet: ResearchPacket, output_dir: str | Path = DEFAULT_RESEARCH_OUTPUT_DIR) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / f"{packet.created_at[:10]}-{packet.job_id}-{packet.packet_id}.json"
    file_path.write_text(
        json.dumps(packet.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return file_path


def packet_to_brief_payload(packet: ResearchPacket) -> dict[str, Any]:
    payload = packet.brief.model_dump(mode="json")
    payload["research_status"] = packet.status
    payload["gate_reasons"] = packet.gate_reasons
    payload["handoff_policy"] = packet.handoff_policy
    payload["research_packet_id"] = packet.packet_id
    payload["research_packet_created_at"] = packet.created_at
    payload["research_packet_job_id"] = packet.job_id
    payload["page_id"] = packet.page_id
    payload["page_context"] = packet.page_context
    return payload


def research_handoff_policy(brief: Any) -> tuple[str, list[str], dict[str, object]]:
    """Classify how safely downstream agents may use this research packet."""
    warnings = list(getattr(brief, "quality_warnings", []) or [])
    topic_scores = list(getattr(brief, "topic_scores", []) or [])
    source_documents = list(getattr(brief, "source_documents", []) or [])
    source_candidates = list(getattr(brief, "source_candidates", []) or [])
    confidence = float(getattr(brief, "confidence_score", 0.0) or 0.0)

    gate_reasons: list[str] = []
    if confidence < 0.5:
        gate_reasons.append(f"confidence thấp ({confidence:.2f})")
    if warnings:
        gate_reasons.append(f"còn {len(warnings)} quality warning")
    if not source_documents:
        gate_reasons.append("chưa có source_documents đã kiểm chứng")
    if source_candidates:
        gate_reasons.append(f"có {len(source_candidates)} nguồn ứng viên chưa duyệt")
    high_risk_topics = [item.topic for item in topic_scores if getattr(item, "risk_level", "") == "high"]
    if high_risk_topics:
        gate_reasons.append(f"có {len(high_risk_topics)} topic high-risk cần duyệt evidence")

    if high_risk_topics or confidence < 0.35:
        status = "blocked"
    elif gate_reasons:
        status = "needs_review"
    else:
        status = "ready"

    handoff_policy = {
        "allow_writer_claims": status == "ready",
        "allow_affiliate_recommendations": status == "ready" and not high_risk_topics,
        "requires_human_review": status != "ready",
        "requires_source_approval": bool(source_candidates),
        "max_safe_use": "draft_questions_only"
        if status == "blocked"
        else ("draft_with_citations" if status == "needs_review" else "draft_with_claims"),
    }
    return status, gate_reasons, handoff_policy
