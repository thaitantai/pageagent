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
        registry_documents = ScraplingSourceCollector(cache_dir=source_cache_dir).collect(
            selected_sources
        )
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
            discovery_queries = (
                [str(item) for item in content_pillars if str(item).strip()]
                if isinstance(content_pillars, list)
                else []
            )
        source_candidates = (
            WebSourceDiscovery().discover(
                queries=discovery_queries, max_candidates=max_discovered_sources
            )
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


def save_research_packet(
    packet: ResearchPacket, output_dir: str | Path = DEFAULT_RESEARCH_OUTPUT_DIR
) -> Path:
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


def _field(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _normalised_domain(url: str) -> str:
    if not url:
        return ""
    from urllib.parse import urlparse

    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _is_affiliate_topic(item: Any) -> bool:
    reason_codes = [str(code) for code in (_field(item, "reason_codes", []) or [])]
    rationale = str(_field(item, "rationale", "") or "").lower()
    topic = str(_field(item, "topic", "") or "").lower()
    return (
        "affiliate_offer" in reason_codes
        or "affiliate_disclosure_required" in reason_codes
        or "khuyến nghị mua" in rationale
        or "review" in topic
        or "so sánh" in topic
        or "mua" in topic
    )


def _has_affiliate_disclosure(brief: Any, affiliate_topics: list[Any]) -> bool:
    for text in list(_field(brief, "recommendations", []) or []) + list(
        _field(brief, "quality_warnings", []) or []
    ):
        lowered = str(text).lower()
        if "affiliate" in lowered or "tiếp thị liên kết" in lowered or "hoa hồng" in lowered:
            return True
    return False


def _affiliate_evidence_stats(brief: Any, affiliate_topics: list[Any]) -> dict[str, Any]:
    evidence = list(_field(brief, "evidence", []) or [])
    source_documents = list(_field(brief, "source_documents", []) or [])
    topic_text = " ".join(str(_field(topic, "topic", "")) for topic in affiliate_topics).lower()
    matched_evidence = []
    for item in evidence:
        claim = str(_field(item, "claim", "") or "").lower()
        source = str(_field(item, "source", "") or "")
        url = str(_field(item, "url", "") or "")
        if (
            not affiliate_topics
            or claim in topic_text
            or any(token and token in claim for token in topic_text.split()[:12])
        ):
            matched_evidence.append(item)
        elif source or url:
            matched_evidence.append(item)
    urls = {str(_field(item, "url", "") or "") for item in matched_evidence}
    urls.update(str(_field(doc, "url", "") or "") for doc in source_documents)
    urls = {url for url in urls if url.startswith(("http://", "https://"))}
    source_keys = {
        str(
            _field(item, "source_id", "")
            or _field(item, "source", "")
            or _normalised_domain(str(_field(item, "url", "") or ""))
        )
        for item in matched_evidence
    }
    source_keys.update(
        str(
            _field(doc, "source_id", "")
            or _field(doc, "source_name", "")
            or _normalised_domain(str(_field(doc, "url", "") or ""))
        )
        for doc in source_documents
    )
    domains = {_normalised_domain(url) for url in urls}
    confidences = [float(_field(item, "confidence", 0.0) or 0.0) for item in matched_evidence]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return {
        "url_count": len(urls),
        "source_count": len({key for key in source_keys if key}),
        "domain_count": len({domain for domain in domains if domain}),
        "avg_confidence": avg_confidence,
        "evidence_count": len(matched_evidence),
    }


def research_handoff_policy(brief: Any) -> tuple[str, list[str], dict[str, object]]:
    """Classify how safely downstream agents may use this research packet."""
    warnings = list(_field(brief, "quality_warnings", []) or [])
    topic_scores = list(_field(brief, "topic_scores", []) or [])
    source_documents = list(_field(brief, "source_documents", []) or [])
    source_candidates = list(_field(brief, "source_candidates", []) or [])
    confidence = float(_field(brief, "confidence_score", 0.0) or 0.0)

    affiliate_topics = [item for item in topic_scores if _is_affiliate_topic(item)]
    affiliate_stats = _affiliate_evidence_stats(brief, affiliate_topics) if affiliate_topics else {}
    has_disclosure = (
        _has_affiliate_disclosure(brief, affiliate_topics) if affiliate_topics else False
    )

    gate_reasons: list[str] = []
    if confidence < 0.5:
        gate_reasons.append(f"confidence thấp ({confidence:.2f})")
    if warnings:
        gate_reasons.append(f"còn {len(warnings)} quality warning")
    if not source_documents:
        gate_reasons.append("chưa có source_documents đã kiểm chứng")
    if source_candidates:
        gate_reasons.append(f"có {len(source_candidates)} nguồn ứng viên chưa duyệt")
    high_risk_topics = [
        str(_field(item, "topic", ""))
        for item in topic_scores
        if _field(item, "risk_level", "") == "high"
    ]
    if high_risk_topics:
        gate_reasons.append(f"có {len(high_risk_topics)} topic high-risk cần duyệt evidence")

    affiliate_blockers: list[str] = []
    affiliate_review: list[str] = []
    if affiliate_topics:
        if affiliate_stats.get("url_count", 0) < 2:
            affiliate_blockers.append("affiliate recommendation cần tối thiểu 2 URL evidence")
        if affiliate_stats.get("source_count", 0) < 2 or affiliate_stats.get("domain_count", 0) < 2:
            affiliate_blockers.append("affiliate recommendation cần tối thiểu 2 nguồn độc lập")
        if affiliate_stats.get("avg_confidence", 0.0) < 0.6:
            affiliate_blockers.append(
                f"affiliate evidence confidence thấp ({affiliate_stats.get('avg_confidence', 0.0):.2f})"
            )
        if not has_disclosure:
            affiliate_blockers.append("affiliate recommendation thiếu disclosure")
        if any(
            "claim_guard_required" in (_field(item, "reason_codes", []) or [])
            for item in affiliate_topics
        ):
            affiliate_review.append("affiliate claim guard/pros-cons cần human review")
    gate_reasons.extend(affiliate_blockers)
    gate_reasons.extend(affiliate_review)

    if high_risk_topics or confidence < 0.35 or affiliate_blockers:
        status = "blocked"
    elif gate_reasons:
        status = "needs_review"
    else:
        status = "ready"

    affiliate_ready = bool(affiliate_topics) and not affiliate_blockers and status == "ready"
    handoff_policy = {
        "allow_writer_claims": status == "ready",
        "allow_affiliate_recommendations": affiliate_ready,
        "requires_human_review": status != "ready" or bool(affiliate_review),
        "requires_source_approval": bool(source_candidates),
        "requires_affiliate_disclosure": bool(affiliate_topics),
        "affiliate_evidence": affiliate_stats,
        "max_safe_use": "draft_questions_only"
        if status == "blocked"
        else ("draft_with_citations" if status == "needs_review" else "draft_with_claims"),
    }
    return status, gate_reasons, handoff_policy
