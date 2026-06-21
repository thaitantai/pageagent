"""Shared downstream handoff normalization for research outputs."""

from __future__ import annotations

from typing import Any


def _as_brief(packet: dict[str, Any]) -> dict[str, Any]:
    brief = packet.get("brief")
    return brief if isinstance(brief, dict) else packet


def _safe_use_from_packet(packet: dict[str, Any]) -> str:
    policy = packet.get("handoff_policy") or {}
    max_safe_use = policy.get("max_safe_use") if isinstance(policy, dict) else None
    if max_safe_use:
        return str(max_safe_use)
    status = str(packet.get("status") or "ready")
    if status == "blocked":
        return "draft_questions_only"
    if status == "needs_review":
        return "human_review"
    return "public_draft"


def _normalise_topic(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic": str(item.get("topic", "")),
        "total_score": item.get("total_score", 0),
        "duplication_risk": item.get("duplication_risk", 0),
        "reason_codes": list(item.get("reason_codes", [])),
    }


def _normalise_evidence_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim": item.get("claim", ""),
        "source": item.get("source") or item.get("source_id", ""),
        "url": item.get("url", ""),
        "confidence": item.get("confidence", 0.0),
    }


def normalize_research_handoff(packet: dict[str, Any] | None) -> dict[str, Any]:
    """Return a stable downstream contract for ResearchPacket or legacy brief shapes."""
    raw_packet = packet if isinstance(packet, dict) else {}
    brief = _as_brief(raw_packet)
    safe_use = _safe_use_from_packet(raw_packet)

    topics = [
        _normalise_topic(item)
        for item in brief.get("topic_scores", [])[:10]
        if isinstance(item, dict) and item.get("topic")
    ]
    if safe_use == "draft_questions_only":
        priority_topics: list[dict[str, Any]] = []
        blocked_topics = topics
    else:
        priority_topics = topics
        blocked_topics = []

    if not priority_topics:
        priority_topics = [
            {"topic": str(item), "total_score": 0, "duplication_risk": 0, "reason_codes": []}
            for item in brief.get("next_angles", [])[:10]
            if str(item).strip()
        ]

    evidence_refs = [
        _normalise_evidence_ref(item)
        for item in brief.get("evidence", [])[:3]
        if isinstance(item, dict)
    ]
    findings = [str(item) for item in brief.get("findings", [])[:10]]
    quality_warnings = [str(item) for item in brief.get("quality_warnings", [])]
    gate_reasons = [str(item) for item in raw_packet.get("gate_reasons", [])]
    page_context = raw_packet.get("page_context", {})
    if not isinstance(page_context, dict):
        page_context = {}

    return {
        "packet_id": str(raw_packet.get("packet_id", "")),
        "status": str(raw_packet.get("status") or "ready"),
        "safe_use": safe_use,
        "confidence_score": brief.get("confidence_score", brief.get("confidence", 0)),
        "page_context": page_context,
        "priority_topics": priority_topics,
        "blocked_topics": blocked_topics,
        "evidence_refs": evidence_refs,
        "findings": findings,
        "quality_warnings": quality_warnings,
        "gate_reasons": gate_reasons,
    }
