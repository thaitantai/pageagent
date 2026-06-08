from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.config import Settings
from fanpage_agent.tools.publishing.delivery import DeliveryTool
from fanpage_agent.core.types import ContentPackage, ContentVariant
from fanpage_agent.tools.publishing.telegram_formatter import TelegramFormatterTool
from fanpage_agent.utils import dump_json
from fanpage_agent.loaders.brand_loader import load_brand_profile

from .parser import ROOT_DIR, add_store_backend_arg, with_default_store_backend
from .content import _content_package_from_caption_item, enrich_items_with_variant_scores
from .research import summarize_calendar_items, summarize_triage_items, build_triage_store_payload


def build_calendar_store_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    items = build_store(settings=settings, args=with_default_store_backend(args)).list_calendar_items(
        status=getattr(args, "status", None),
        approval_status=getattr(args, "approval_status", None),
        date=getattr(args, "date", None),
        limit=getattr(args, "limit", None),
    )
    if getattr(args, "metrics_pending", False):
        items = [i for i in items if not i.get("metrics_recorded", False)]
    if getattr(args, "score_variants", False):
        items = enrich_items_with_variant_scores(items, memory_db=args.memory_db)
    return {
        "items": items,
        "summary": summarize_calendar_items(items),
    }


def build_approval_audit_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    cutoff = datetime.fromisoformat(args.as_of).replace(tzinfo=timezone.utc).timestamp()
    items = store.list_calendar_items(status="published", limit=args.limit)
    audit_items = []
    breached = 0
    sla_seconds = args.sla_days * 86400
    for item in items:
        approved_at = cast(float, item.get("approved_at", 0))
        published_at = cast(float, item.get("published_at", 0))
        if not approved_at or not published_at:
            continue
        if published_at > cutoff:
            continue
        lag = published_at - approved_at
        item = dict(item)
        item["approval_lag_hours"] = round(lag / 3600, 1)
        item["approval_lag_breach"] = lag > sla_seconds
        if lag > sla_seconds:
            breached += 1
        audit_items.append(item)
    return {
        "audit_items": audit_items,
        "summary": {
            "total_audited": len(audit_items),
            "breached": breached,
            "breach_rate": round(breached / max(len(audit_items), 1), 3),
            "sla_days": args.sla_days,
            "as_of": args.as_of,
        },
    }


def _publish_blockers_for_operator(calendar_items: list[dict]) -> list[dict]:
    blockers: list[dict] = []
    now = datetime.now(tz=timezone.utc).timestamp()
    for item in calendar_items:
        issues: list[str] = []
        if item.get("status") != "approved":
            issues.append("not_approved")
        if float(item.get("scheduled_time", 0)) > now + 86400:
            issues.append("too_far_in_future")
        if not item.get("approved_by"):
            issues.append("no_approver")
        if issues:
            blockers.append({
                "calendar_id": item.get("calendar_id"),
                "date": item.get("date"),
                "pillar": item.get("pillar"),
                "blockers": issues,
            })
    return blockers


def build_operator_digest_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=with_default_store_backend(args))

    calendar_items = store.list_calendar_items(
        status=getattr(args, "calendar_status", "planned"),
        approval_status=getattr(args, "approval_status", "pending"),
        date=getattr(args, "date", None),
        limit=getattr(args, "limit", None),
    )
    triage_items = store.list_triage_items(
        status=getattr(args, "triage_status", "approved"),
        limit=getattr(args, "limit", None),
    )
    metrics_items = store.list_calendar_items(
        status=getattr(args, "metrics_status", "published"),
        limit=getattr(args, "limit", None),
    )
    metrics_pending = [i for i in metrics_items if not i.get("metrics_recorded", False)]

    payload: dict[str, Any] = {
        "calendar_pending": calendar_items,
        "calendar_pending_count": len(calendar_items),
        "triage_approved": triage_items,
        "triage_approved_count": len(triage_items),
        "metrics_pending": metrics_pending,
        "metrics_pending_count": len(metrics_pending),
        "publish_blockers": _publish_blockers_for_operator(calendar_items),
    }
    return payload


# ── triage community ──────────────────────────────

def cmd_triage_community(args: argparse.Namespace) -> int:
    from fanpage_agent.tools.community_triage import CommunityTriageTool

    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    tool = CommunityTriageTool(profile=profile, settings=settings)
    result = tool.triage(comment_csv=args.comment_file, triage_csv=args.triage_file, write_store=args.write_store)
    payload = result.model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "community" / f"community-triage-{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_triage_community(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    items = store.list_triage_items(
        status=getattr(args, "status", None),
        priority=getattr(args, "priority", None),
        assigned_to=getattr(args, "assigned_to", None),
        limit=getattr(args, "limit", None),
    )
    payload: dict[str, Any] = {"items": items, "summary": summarize_triage_items(items)}
    payload["delivery"] = DeliveryTool(settings).deliver_community_triage(payload, chat_id=args.chat_id)
    if args.save:
        dump_json(settings.artifacts_dir / "community" / "community-triage-delivered.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_approved_triage_replies(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    items = build_store(settings=settings, args=with_default_store_backend(args)).list_triage_items(
        status=args.status or "approved",
        priority=getattr(args, "priority", None),
        assigned_to=getattr(args, "assigned_to", None),
        limit=getattr(args, "limit", None),
    )
    payload = {"items": items}
    payload["delivery"] = DeliveryTool(settings).deliver_approved_triage_replies(payload, chat_id=args.chat_id)
    if args.save:
        dump_json(settings.artifacts_dir / "community" / f"approved-triage-replies-{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


# ── list + resolve/reopen ──────────────────────────

def cmd_list_triage_items(args: argparse.Namespace) -> int:
    payload = build_triage_store_payload(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_list_calendar_items(args: argparse.Namespace) -> int:
    payload = build_calendar_store_payload(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


# ── approval queue + audit ─────────────────────────

def cmd_deliver_approval_queue(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    items = build_store(settings=settings, args=with_default_store_backend(args)).list_calendar_items(
        status=getattr(args, "status", None),
        approval_status=args.approval_status or "pending",
        date=getattr(args, "date", None),
        limit=getattr(args, "limit", None),
    )
    if getattr(args, "score_variants", False):
        items = enrich_items_with_variant_scores(items, memory_db=args.memory_db)
    payload: dict[str, Any] = {"items": items, "summary": summarize_calendar_items(items)}
    payload["delivery"] = DeliveryTool(settings).deliver_approval_queue(payload, chat_id=args.chat_id)
    if args.save:
        dump_json(settings.artifacts_dir / "approvals" / f"approval-queue-{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_approval_audit(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    payload = build_approval_audit_payload(args)
    if args.save:
        dump_json(settings.artifacts_dir / "approvals" / "approval-audit.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_approval_audit(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    payload = build_approval_audit_payload(args)
    payload["delivery"] = DeliveryTool(settings).deliver_approval_audit(payload, chat_id=args.chat_id)
    if args.save:
        dump_json(settings.artifacts_dir / "approvals" / "approval-audit.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_metrics_backlog(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    items = build_store(settings=settings, args=with_default_store_backend(args)).list_calendar_items(
        status=getattr(args, "status", "published"),
        approval_status=getattr(args, "approval_status", None),
        date=getattr(args, "date", None),
        limit=getattr(args, "limit", None),
    )
    if getattr(args, "metrics_pending", False):
        items = [i for i in items if not i.get("metrics_recorded", False)]
    payload: dict[str, Any] = {"items": items, "summary": summarize_calendar_items(items)}
    payload["delivery"] = DeliveryTool(settings).deliver_metrics_backlog(payload, chat_id=args.chat_id)
    if args.save:
        dump_json(settings.artifacts_dir / "metrics" / f"metrics-backlog-{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_operator_digest(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    if getattr(args, "skip_empty", False):
        items = build_store(settings=settings, args=with_default_store_backend(args)).list_calendar_items(
            status=getattr(args, "calendar_status", "planned"),
            approval_status=getattr(args, "approval_status", "pending"),
            date=getattr(args, "date", None),
            limit=getattr(args, "limit", None),
        )
        triage_items = build_store(settings=settings, args=with_default_store_backend(args)).list_triage_items(
            status=getattr(args, "triage_status", "approved"),
            limit=getattr(args, "limit", None),
        )
        if not items and not triage_items:
            print("ℹ️ No pending action items — skipping digest.")
            return 0
    payload = build_operator_digest_payload(args)
    payload["delivery"] = DeliveryTool(settings).deliver_operator_digest(payload, chat_id=args.chat_id)
    if args.save:
        dump_json(settings.artifacts_dir / "ops" / "operator-digest.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


# ── resolve / reopen / approve / reject ─────────────

def cmd_resolve_triage_item(args: argparse.Namespace) -> int:
    payload = build_triage_store_payload(args)
    items = payload["items"]
    resolved = build_store(settings=Settings.from_env(root_dir=ROOT_DIR), args=with_default_store_backend(args)).resolve_triage_item(
        triage_id=args.triage_id,
        resolved_at=args.resolved_at,
        assigned_to=args.assigned_to,
        items=items,
    )
    print(json.dumps(resolved, ensure_ascii=False, indent=2))
    return 0


def cmd_reopen_triage_item(args: argparse.Namespace) -> int:
    payload = build_triage_store_payload(args)
    items = payload["items"]
    reopened = build_store(settings=Settings.from_env(root_dir=ROOT_DIR), args=with_default_store_backend(args)).reopen_triage_item(
        triage_id=args.triage_id,
        reopened_at=args.reopened_at,
        assigned_to=args.assigned_to,
        items=items,
    )
    print(json.dumps(reopened, ensure_ascii=False, indent=2))
    return 0


def cmd_approve_triage_reply(args: argparse.Namespace) -> int:
    payload = build_triage_store_payload(args)
    items = payload["items"]
    approved = build_store(settings=Settings.from_env(root_dir=ROOT_DIR), args=with_default_store_backend(args)).approve_triage_reply(
        triage_id=args.triage_id,
        approved_by=args.approved_by,
        approved_at=args.approved_at,
        assigned_to=args.assigned_to,
        items=items,
    )
    print(json.dumps(approved, ensure_ascii=False, indent=2))
    return 0


def cmd_reject_triage_reply(args: argparse.Namespace) -> int:
    payload = build_triage_store_payload(args)
    items = payload["items"]
    rejected = build_store(settings=Settings.from_env(root_dir=ROOT_DIR), args=with_default_store_backend(args)).reject_triage_reply(
        triage_id=args.triage_id,
        reason=args.reason,
        rejected_at=args.rejected_at,
        assigned_to=args.assigned_to,
        items=items,
    )
    print(json.dumps(rejected, ensure_ascii=False, indent=2))
    return 0


def cmd_mark_triage_reply_sent(args: argparse.Namespace) -> int:
    payload = build_triage_store_payload(args)
    items = payload["items"]
    sent = build_store(settings=Settings.from_env(root_dir=ROOT_DIR), args=with_default_store_backend(args)).mark_triage_reply_sent(
        triage_id=args.triage_id,
        sent_at=args.sent_at,
        reply_permalink=args.reply_permalink,
        assigned_to=args.assigned_to,
        items=items,
    )
    print(json.dumps(sent, ensure_ascii=False, indent=2))
    return 0


def cmd_approve_caption(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=with_default_store_backend(args))
    caption_path = Path(args.caption_file)
    caption_payload = json.loads(caption_path.read_text(encoding="utf-8"))
    updated = store.approve_caption(
        calendar_id=args.calendar_id,
        approved_by=args.approved_by,
        approved_at=args.approved_at,
        caption_payload=caption_payload,
    )
    print(json.dumps(updated, ensure_ascii=False, indent=2))
    return 0


def cmd_reject_caption(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=with_default_store_backend(args))
    updated = store.reject_caption(
        calendar_id=args.calendar_id,
        reason=args.reason,
        rejected_at=args.rejected_at,
    )
    print(json.dumps(updated, ensure_ascii=False, indent=2))
    return 0


def _find_calendar_item_for_publish(store: Any, calendar_id: str, allow_unapproved: bool = False) -> dict | None:
    items = store.list_calendar_items()
    for item in items:
        if str(item.get("calendar_id", "")) == calendar_id:
            if not allow_unapproved and item.get("approval_status") != "approved":
                return None
            return item
    return None


def _build_publish_block_payload(
    item: dict,
    published_at: str,
    permalink: str,
    reach: int = 0,
    engagement_rate: float = 0.0,
) -> dict:
    return {
        "calendar_id": item["calendar_id"],
        "date": item.get("date"),
        "pillar": item.get("pillar"),
        "published_at": published_at,
        "permalink": permalink,
        "reach": reach,
        "engagement_rate": engagement_rate,
        "block": {
            "is_approved": item.get("approval_status") == "approved",
            "has_caption": bool(item.get("caption_ideas") or item.get("variants")),
            "has_schedule": bool(item.get("scheduled_time")),
        },
    }
