"""Approval workflow tools: calendar management + community triage."""

from __future__ import annotations

from datetime import datetime, timezone

from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.tools.content.verifier import VerifierTool
from fanpage_agent.tools.content.writer import WriterTool
from fanpage_agent.tools.publishing.calendar_gap_service import CalendarGapTool
from fanpage_agent.tools.publishing.community_triage import CommunityTriageTool
from fanpage_agent.tools.publishing.planner import PlannerTool

from .helpers import (
    DEFAULT_COMMENT,
    list_calendar_items_summary,
    list_triage_items_summary,
    local_store,
    profile,
    settings,
)


def tool_fill_calendar_gaps(lookahead_days: int = 3, max_items: int = 3) -> dict:
    s = settings()
    p = profile(s)
    store = local_store()
    llm = build_llm_client(s)
    planner = PlannerTool(llm_client=llm)
    writer = WriterTool(llm_client=llm)
    verifier = VerifierTool()
    service = CalendarGapTool(
        planner=planner,
        writer=writer,
        verifier=verifier,
        artifacts_dir=s.artifacts_dir / "captions",
    )
    result = service.fill_gaps(
        profile=p,
        store=store,
        lookahead_days=lookahead_days,
        max_items=max_items,
    )
    return result.to_dict()


def tool_list_calendar_items() -> dict:
    return list_calendar_items_summary(local_store())


def tool_approve_calendar_item(calendar_id: str) -> dict:
    settings()
    store = local_store()
    now = datetime.now(timezone.utc).isoformat()
    result = store.approve_calendar_item(calendar_id, approved_by="agent", final_caption_ref="", approved_at=now)
    return {"approved": calendar_id, "result": result}


def tool_reject_calendar_item(calendar_id: str) -> dict:
    settings()
    store = local_store()
    now = datetime.now(timezone.utc).isoformat()
    result = store.reject_calendar_item(calendar_id, reason="Rejected by agent", rejected_at=now)
    return {"rejected": calendar_id, "result": result}


def tool_list_triage_items() -> dict:
    return list_triage_items_summary(local_store())


def tool_triage_community(max_items: int = 10) -> dict:
    s = settings()
    p = profile(s)
    service = CommunityTriageTool()
    batch = service.triage_from_csv(profile=p, comment_csv=str(DEFAULT_COMMENT))
    if max_items and max_items < len(batch.items):
        batch.items = batch.items[:max_items]
    return {
        "total": len(batch.items),
        "summary": batch.summary,
        "items": [
            {
                "id": item.triage_id,
                "category": item.category,
                "priority": item.priority,
                "message_preview": item.message[:80],
            }
            for item in batch.items
        ],
    }


def tool_approve_triage_reply(item_id: str) -> dict:
    settings()
    store = local_store()
    now = datetime.now(timezone.utc).isoformat()
    result = store.approve_triage_reply(item_id, approved_by="agent", approved_at=now)
    return {"approved": item_id, "result": result}


def tool_reject_triage_reply(item_id: str, reason: str = "") -> dict:
    settings()
    store = local_store()
    now = datetime.now(timezone.utc).isoformat()
    result = store.reject_triage_reply(item_id, reason=reason or "Rejected by agent", rejected_at=now)
    return {"rejected": item_id, "result": result}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "fill_calendar_gaps",
            "description": "Auto-detect empty days in calendar and fill them: plan → write caption → verify → auto-approve. Lighter than run_daily — only fills 3 days forward, max 3 items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lookahead_days": {"type": "integer", "description": "Days to scan forward (default 3)"},
                    "max_items": {"type": "integer", "description": "Max items to fill (default 3)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_calendar_items",
            "description": "List content calendar items with counts by approval status",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_calendar_item",
            "description": "Approve a calendar item for publishing",
            "parameters": {
                "type": "object",
                "properties": {
                    "calendar_id": {"type": "string", "description": "Calendar item ID"},
                },
                "required": ["calendar_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reject_calendar_item",
            "description": "Reject a calendar item",
            "parameters": {
                "type": "object",
                "properties": {
                    "calendar_id": {"type": "string", "description": "Calendar item ID"},
                },
                "required": ["calendar_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_triage_items",
            "description": "List community triage items with counts by status",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "triage_community",
            "description": "Run LLM triage on pending community comments",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_items": {"type": "integer", "description": "Max comments to triage (default 10)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_triage_reply",
            "description": "Approve a triage reply so it can be sent",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "Triage item ID to approve"},
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reject_triage_reply",
            "description": "Reject a triage reply",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "Triage item ID to reject"},
                    "reason": {"type": "string", "description": "Reason for rejection"},
                },
                "required": ["item_id"],
            },
        },
    },
]

REGISTRY_BUILDERS = {
    "fill_calendar_gaps": (tool_fill_calendar_gaps, {"lookahead_days": 3, "max_items": 3}),
    "list_calendar_items": (tool_list_calendar_items, {}),
    "approve_calendar_item": (tool_approve_calendar_item, {"calendar_id": ""}),
    "reject_calendar_item": (tool_reject_calendar_item, {"calendar_id": ""}),
    "list_triage_items": (tool_list_triage_items, {}),
    "triage_community": (tool_triage_community, {"max_items": 10}),
    "approve_triage_reply": (tool_approve_triage_reply, {"item_id": ""}),
    "reject_triage_reply": (tool_reject_triage_reply, {"item_id": "", "reason": ""}),
}
