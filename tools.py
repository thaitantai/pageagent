"""Tool registry — wraps existing pipeline logic as callable tools.

Each tool has:
- A JSON schema (OpenAI tools format) so the LLM can call it
- A Python callable that the orchestrator can dispatch to

Moved from fanpage_agent/agent/tools.py.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.adapters.telegram_client import TelegramClient
from fanpage_agent.config import Settings
from fanpage_agent.legacy_cli import build_daily_artifacts, build_ops_status_payload
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.models import BrandProfile
from fanpage_agent.services.calendar_gap_service import CalendarGapService
from fanpage_agent.services.community_triage import CommunityTriageService
from fanpage_agent.services.content_stats import compute_content_stats
from fanpage_agent.services.daily_ops import DailyOpsService
from fanpage_agent.services.metrics_auto_fetch import MetricsAutoFetchService
from fanpage_agent.services.planner import PlannerService
from fanpage_agent.services.research import ResearchService
from fanpage_agent.services.scheduled_publish import ScheduledPublishService
from fanpage_agent.services.verifier import VerifierService
from fanpage_agent.services.writer import WriterService

# ── helpers shared by tools ────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parent  # project root (now at root level)
DEFAULT_CALENDAR = ROOT_DIR / "data" / "real" / "content_calendar.csv"
DEFAULT_HISTORY = ROOT_DIR / "data" / "real" / "post_history.csv"
DEFAULT_COMMENT = ROOT_DIR / "data" / "real" / "comment_inbox.csv"
DEFAULT_METRICS = ROOT_DIR / "data" / "real" / "post_metrics.csv"
DEFAULT_BRAND = ROOT_DIR / "data" / "real" / "brand_profile.json"


def _settings() -> Settings:
    return Settings.from_env(root_dir=ROOT_DIR)


def _local_store() -> LocalSheetStore:
    """Build a LocalSheetStore with default data paths."""
    return LocalSheetStore(
        calendar_csv=DEFAULT_CALENDAR,
        history_csv=DEFAULT_HISTORY,
        metrics_csv=DEFAULT_METRICS,
        triage_csv=DEFAULT_COMMENT,
    )


def _profile(settings: Settings | None = None) -> BrandProfile:
    settings or _settings()
    path = DEFAULT_BRAND if DEFAULT_BRAND.exists() else ROOT_DIR / "data" / "sample" / "brand_profile.json"
    if not path.exists():
        raise FileNotFoundError(f"Brand profile not found at {path}")
    return load_brand_profile(path)


# ── internal helpers ───────────────────────────────────────────


def _list_calendar_items_summary(store: LocalSheetStore) -> dict:
    """Get calendar stats via the store's list_calendar_items API."""
    items = store.list_calendar_items()
    return {
        "total": len(items),
        "pending_approval": len([i for i in items if i.get("approval_status", "").lower() == "pending"]),
        "approved_ready": len([i for i in items if i.get("approval_status", "").lower() == "approved"]),
        "published": len([i for i in items if i.get("status", "").lower() == "published"]),
    }


def _list_triage_items_summary(store: LocalSheetStore) -> dict:
    """Get triage stats via the store's list_triage_items API."""
    items = store.list_triage_items()
    return {
        "total": len(items),
        "pending": len([t for t in items if t.get("status", "").lower() == "pending_triage"]),
        "approved": len([t for t in items if t.get("status", "").lower() in ("approved", "reply_approved")]),
        "rejected": len([t for t in items if t.get("status", "").lower() == "rejected"]),
    }


# ── tool definitions ───────────────────────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "ops_status",
            "description": "Get current pipeline status — calendar, community, artifacts freshness",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why you're checking status (e.g. 'cycle start', 'after action')"},
                },
                "required": ["reason"],
            },
        },
    },
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
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_triage_items",
            "description": "List community triage items with counts by status",
            "parameters": {
                "type": "object",
                "properties": {},
            },
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
            "name": "write_caption",
            "description": "Generate a caption for a given topic (uses brand voice + tone validation)",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to write about"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_daily",
            "description": "Run the full daily pipeline: research → plan → write → verify → queue",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scheduled_publish",
            "description": "Publish any calendar items that are due for automated publishing",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_post_metrics",
            "description": "Auto-fetch and record metrics for recently published posts",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_fb_comments",
            "description": "Fetch recent comments from Facebook page posts",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_message",
            "description": "Send a text message to the operator's Telegram",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Message text"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "content_stats",
            "description": "Get content performance stats — which pillars/formats are performing best. Use this to decide what to write next.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "description": "Number of days to look back (default 14)"},
                },
            },
        },
    },
]


# ── tool implementations ───────────────────────────────────────


def _make_tool_ops_status(reason: str = "status check") -> dict:
    s = _settings()
    return build_ops_status_payload(s)


def _make_tool_fill_calendar_gaps(lookahead_days: int = 3, max_items: int = 3) -> dict:
    s = _settings()
    profile = _profile(s)
    store = _local_store()
    llm_client = build_llm_client(s)
    planner = PlannerService(llm_client=llm_client)
    writer = WriterService(llm_client=llm_client)
    verifier = VerifierService()
    service = CalendarGapService(
        planner=planner,
        writer=writer,
        verifier=verifier,
        artifacts_dir=s.artifacts_dir / "captions",
    )
    result = service.fill_gaps(
        profile=profile,
        store=store,
        lookahead_days=lookahead_days,
        max_items=max_items,
    )
    return result.to_dict()


def _make_tool_list_calendar_items() -> dict:
    store = _local_store()
    return _list_calendar_items_summary(store)


def _make_tool_list_triage_items() -> dict:
    store = _local_store()
    return _list_triage_items_summary(store)


def _make_tool_triage_community(max_items: int = 10) -> dict:
    s = _settings()
    profile = _profile(s)
    service = CommunityTriageService()
    batch = service.triage_from_csv(profile=profile, comment_csv=str(DEFAULT_COMMENT))
    # Apply max_items limit
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


def _make_tool_approve_triage_reply(item_id: str) -> dict:
    _settings()
    store = _local_store()
    now = datetime.now(timezone.utc).isoformat()
    result = store.approve_triage_reply(item_id, approved_by="agent", approved_at=now)
    return {"approved": item_id, "result": result}


def _make_tool_reject_triage_reply(item_id: str, reason: str = "") -> dict:
    _settings()
    store = _local_store()
    now = datetime.now(timezone.utc).isoformat()
    result = store.reject_triage_reply(item_id, reason=reason or "Rejected by agent", rejected_at=now)
    return {"rejected": item_id, "result": result}


def _make_tool_approve_calendar_item(calendar_id: str) -> dict:
    _settings()
    store = _local_store()
    now = datetime.now(timezone.utc).isoformat()
    result = store.approve_calendar_item(calendar_id, approved_by="agent", final_caption_ref="", approved_at=now)
    return {"approved": calendar_id, "result": result}


def _make_tool_reject_calendar_item(calendar_id: str) -> dict:
    _settings()
    store = _local_store()
    now = datetime.now(timezone.utc).isoformat()
    result = store.reject_calendar_item(calendar_id, reason="Rejected by agent", rejected_at=now)
    return {"rejected": calendar_id, "result": result}


def _make_tool_write_caption(topic: str | None = None) -> dict:
    s = _settings()
    profile = _profile(s)
    topic_val = topic or ""
    writer = WriterService(llm_client=build_llm_client(s), settings=s)
    result = writer.write_caption(
        brand_profile=profile,
        topic=topic_val,
        pillar="",
        objective="",
    )
    return json.loads(result.model_dump_json())


def _make_tool_run_daily() -> dict:
    s = _settings()
    profile = _profile(s)
    llm_client = build_llm_client(s)
    store = _local_store()
    run_date = date.today().isoformat()

    research_brief = ResearchService().build_brief(
        store=store,
        comment_csv=str(DEFAULT_COMMENT),
        campaign_notes_file=None,
    )
    packet = DailyOpsService(
        planner=PlannerService(llm_client=llm_client),
        writer=WriterService(llm_client=llm_client),
    ).build_packet(
        profile=profile,
        run_date=run_date,
        store=store,
        days=7,
        write_calendar=True,
        research_brief=research_brief,
    )

    packet["artifacts"] = build_daily_artifacts(s, packet, run_date)
    return packet


def _make_tool_scheduled_publish() -> dict:
    s = _settings()
    profile = _profile(s)
    store = _local_store()
    service = ScheduledPublishService(
        store=store,
        brand_id=profile.brand_id,
    )
    result = service.publish_due()
    return {"result": result.to_dict()}


def _make_tool_record_post_metrics() -> dict:
    s = _settings()
    store = _local_store()
    service = MetricsAutoFetchService(settings=s)
    result = service.auto_fetch(store=store)
    return result


def _make_tool_fetch_fb_comments() -> dict:
    s = _settings()
    fb = FacebookClient(s)
    try:
        posts = fb.get_page_posts(limit=5)
    except Exception as e:
        return {"error": f"Failed to fetch posts: {e}"}
    all_comments = []
    for post in posts:
        post_id = post.get("id", "")
        if not post_id:
            continue
        try:
            comments = fb.get_comments(post_id, limit=20)
        except Exception:
            comments = []
        for c in comments:
            c["post_id"] = post_id
            all_comments.append(c)
    return {"total_comments": len(all_comments), "posts_checked": len(posts)}


def _make_tool_send_telegram_message(text: str) -> dict:
    s = _settings()
    client = TelegramClient(s)
    client.send_message(text=text, chat_id=s.telegram_chat_id, parse_mode="Markdown")
    return {"sent": True}


def _make_tool_content_stats(days_back: int = 14) -> dict:
    store = _local_store()
    return compute_content_stats(store, days_back=days_back)


# ── wire registry ──────────────────────────────────────────────

TOOL_REGISTRY: dict[str, Any] = {}

REGISTRY_BUILDERS: dict[str, Any] = {
    "ops_status": (_make_tool_ops_status, {}),
    "fill_calendar_gaps": (_make_tool_fill_calendar_gaps, {"lookahead_days": 3, "max_items": 3}),
    "list_triage_items": (_make_tool_list_triage_items, {}),
    "triage_community": (_make_tool_triage_community, {"max_items": 10}),
    "approve_triage_reply": (_make_tool_approve_triage_reply, {"item_id": ""}),
    "reject_triage_reply": (_make_tool_reject_triage_reply, {"item_id": "", "reason": ""}),
    "list_calendar_items": (_make_tool_list_calendar_items, {}),
    "approve_calendar_item": (_make_tool_approve_calendar_item, {"calendar_id": ""}),
    "reject_calendar_item": (_make_tool_reject_calendar_item, {"calendar_id": ""}),
    "write_caption": (_make_tool_write_caption, {"topic": None}),
    "run_daily": (_make_tool_run_daily, {}),
    "scheduled_publish": (_make_tool_scheduled_publish, {}),
    "record_post_metrics": (_make_tool_record_post_metrics, {}),
    "fetch_fb_comments": (_make_tool_fetch_fb_comments, {}),
    "send_telegram_message": (_make_tool_send_telegram_message, {"text": ""}),
    "content_stats": (_make_tool_content_stats, {"days_back": 14}),
}

for name, (fn, _) in REGISTRY_BUILDERS.items():
    TOOL_REGISTRY[name] = fn


# ── public API ─────────────────────────────────────────────────


def get_tool_definitions() -> list[dict]:
    """Return the full tool definitions list (OpenAI tools format)."""
    return TOOL_DEFINITIONS


def dispatch_tool(name: str, args: dict | None = None) -> dict:
    """Look up and call a tool by name."""
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {name}"}
    resolved_args = args or {}
    fn = TOOL_REGISTRY[name]
    try:
        result = fn(**resolved_args)
    except TypeError:
        result = fn()
    if not isinstance(result, dict):
        return {"result": str(result)}
    return result


def tool_ops_status(args: dict | None = None) -> dict:
    """Shorthand — call ops_status tool directly."""
    return dispatch_tool("ops_status", args)
