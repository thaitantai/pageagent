from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.models import ResearchPacket
from fanpage_agent.services.research import ResearchService


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
) -> ResearchPacket:
    store = LocalSheetStore(
        calendar_csv=calendar_file,
        history_csv=history_file,
        metrics_csv=metrics_file,
    )
    brief = ResearchService().build_brief(
        store=store,
        comment_csv=comment_file,
        campaign_notes_file=campaign_file,
        fetch_external_trends=fetch_external_trends,
    )
    packet_job_id = job_id or f"research-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    return ResearchPacket(
        packet_id=f"rpkt-{uuid4().hex[:12]}",
        job_id=packet_job_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        page_id=page_id or str((page_context or {}).get("page_id", "")),
        page_context=page_context or {},
        source_files={
            "history_file": str(history_file),
            "metrics_file": str(metrics_file),
            "comment_file": str(comment_file or ""),
            "campaign_file": str(campaign_file or ""),
            "calendar_file": str(calendar_file),
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
    payload["research_packet_id"] = packet.packet_id
    payload["research_packet_created_at"] = packet.created_at
    payload["research_packet_job_id"] = packet.job_id
    payload["page_id"] = packet.page_id
    payload["page_context"] = packet.page_context
    return payload
