from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timezone

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

logger = logging.getLogger(__name__)


def build_calendar_store_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    items = build_store(settings=settings, args=with_default_store_backend(args)).list_calendar_items(
        status=getattr(args, "status", None),
        approval_status=getattr(args, "approval_status", None),
        date=getattr(args, "date", None),
        metrics_pending=getattr(args, "metrics_pending", False),
        limit=getattr(args, "limit", None),
    )
    if getattr(args, "score_variants", False):
        items = enrich_items_with_variant_scores(items, memory_db=args.memory_db)
    return {
        "items": items,
        "summary": summarize_calendar_items(items),
    }


def build_approval_audit_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    rows = build_store(settings=settings, args=args).list_calendar_items()
    as_of = date.fromisoformat(args.as_of)
    pending: list[dict] = []
    approved: list[dict] = []
    rejected: list[dict] = []
    overdue: list[dict] = []
    for row in rows:
        approval_status = row.get("approval_status", "") or "unknown"
        if approval_status == "pending":
            pending_item = dict(row)
            basis = pending_item.get("last_updated") or pending_item.get("date") or args.as_of
            days_pending = max((as_of - date.fromisoformat(basis[:10])).days, 0)
            pending_item["days_pending"] = days_pending
            pending.append(pending_item)
            if days_pending > args.sla_days:
                overdue.append(pending_item)
        elif approval_status == "approved":
            approved.append(row)
        elif approval_status == "rejected":
            rejected.append(row)
    overdue.sort(key=lambda item: item.get("days_pending", 0), reverse=True)
    if args.limit is not None:
        overdue = overdue[: args.limit]
    return {
        "summary": {
            "total_audited": len(rows),
            "pending": len(pending),
            "overdue_pending": len([item for item in pending if item.get("days_pending", 0) > args.sla_days]),
            "approved": len(approved),
            "rejected": len(rejected),
            "sla_days": args.sla_days,
            "as_of": args.as_of,
        },
        "overdue_items": overdue,
        "recent_rejections": rejected[-(args.limit or 5) :],
    }


def _publish_blockers_for_operator(calendar_items: list[dict]) -> list[dict]:
    blockers: list[dict] = []
    now = datetime.now(tz=timezone.utc).timestamp()
    for item in calendar_items:
        issues: list[str] = []
        if item.get("status") != "approved":
            issues.append("approval_status_not_approved")
        if float(item.get("scheduled_time", 0)) > now + 86400:
            issues.append("too_far_in_future")
        if not item.get("approved_by"):
            issues.append("no_approver")
        if issues:
            blockers.append({
                "calendar_id": item.get("calendar_id"),
                "date": item.get("date"),
                "pillar": item.get("pillar"),
                "reason_codes": issues,
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
        metrics_pending=True,
        limit=getattr(args, "limit", None),
    )
    metrics_pending = metrics_items

    payload: dict[str, Any] = {
        "summary": {
            "pending_captions": len(calendar_items),
            "approved_replies": len(triage_items),
            "metrics_backlog": len(metrics_pending),
            "publish_blockers": len(_publish_blockers_for_operator(calendar_items)),
        },
        "approval_queue": {"items": calendar_items},
        "approved_replies": {"items": triage_items},
        "metrics_backlog": {"items": metrics_pending},
        "publish_blockers": {"items": _publish_blockers_for_operator(calendar_items)},
    }
    return payload


def cmd_triage_community(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)

    from fanpage_agent.tools.publishing.community_triage import CommunityTriageTool

    result = CommunityTriageTool().triage_from_csv(profile=profile, comment_csv=args.comment_file)
    payload = result.model_dump(mode="json")

    # Write to store (handles both local CSV and Google Sheets backends)
    store = build_store(settings=settings, args=with_default_store_backend(args))
    store.upsert_triage_items(brand_id=profile.brand_id, items=result.items)

    if args.save:
        dump_json(settings.artifacts_dir / "community" / "community-triage.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_triage_community(args: argparse.Namespace) -> int:
    from fanpage_agent.tools.publishing.community_triage import CommunityTriageTool

    settings = Settings.from_env(root_dir=ROOT_DIR)

    if getattr(args, "from_store", False):
        # Read from store directly (test path)
        store = build_store(settings=settings, args=with_default_store_backend(args))
        items = store.list_triage_items(
            status=getattr(args, "status", None),
            priority=getattr(args, "priority", None),
            assigned_to=getattr(args, "assigned_to", None),
            limit=getattr(args, "limit", None),
        )
        payload = {"items": items, "summary": summarize_triage_items(items)}
    else:
        # Triage comments first, write to store, then deliver
        profile = load_brand_profile(args.brand_file)
        result = CommunityTriageTool().triage_from_csv(profile=profile, comment_csv=args.comment_file)
        payload = result.model_dump(mode="json")
        store = build_store(settings=settings, args=with_default_store_backend(args))
        store.upsert_triage_items(brand_id=profile.brand_id, items=result.items)

    payload["delivery"] = DeliveryTool(settings).deliver_community_triage(payload, chat_id=args.chat_id)
    if args.save:
        dump_json(settings.artifacts_dir / "community" / "community-triage.json", payload)
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
    payload = {"items": items, "summary": {"total_items": len(items)}}
    payload["delivery"] = DeliveryTool(settings).deliver_approved_triage_replies(payload, chat_id=args.chat_id)
    if args.save:
        dump_json(settings.artifacts_dir / "community" / "approved-triage-replies.json", payload)
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
    # Scoring is default-ON (--no-score-variants opts out). enrich mutates
    # items in-place and returns a SUMMARY — the old code assigned that
    # summary over the items list, wiping the queue when --score-variants
    # was passed.
    scoring_summary: dict | None = None
    if not getattr(args, "no_score_variants", False):
        try:
            scoring_summary = enrich_items_with_variant_scores(
                items, memory_db=getattr(args, "memory_db", None)
            )
        except Exception as exc:
            logger.warning("Variant scoring skipped (delivery continues): %s", exc)
            scoring_summary = {"error": str(exc)[:200]}
    payload: dict[str, Any] = {"items": items, "summary": summarize_calendar_items(items)}
    if scoring_summary is not None:
        payload["variant_scoring"] = scoring_summary
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
        metrics_pending=getattr(args, "metrics_pending", False),
        limit=getattr(args, "limit", None),
    )
    payload: dict[str, Any] = {"items": items, "summary": summarize_calendar_items(items)}
    payload["delivery"] = DeliveryTool(settings).deliver_metrics_backlog(payload, chat_id=args.chat_id)
    if args.save:
        dump_json(settings.artifacts_dir / "metrics" / f"metrics-backlog-{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_operator_digest(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    if getattr(args, "skip_empty", False):
        store = build_store(settings=settings, args=with_default_store_backend(args))
        items = store.list_calendar_items(
            status=getattr(args, "calendar_status", "planned"),
            approval_status=getattr(args, "approval_status", "pending"),
            date=getattr(args, "date", None),
            limit=getattr(args, "limit", None),
        )
        triage_items = store.list_triage_items(
            status=getattr(args, "triage_status", "approved"),
            limit=getattr(args, "limit", None),
        )
        if not items and not triage_items:
            payload = {
                "summary": {"pending_captions": 0, "approved_replies": 0, "metrics_backlog": 0},
                "delivery": {"sent_count": 0, "skipped": True, "reason": "empty_digest"},
            }
            if args.save:
                dump_json(settings.artifacts_dir / "ops" / "operator-digest.json", payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
    payload = build_operator_digest_payload(args)
    payload["delivery"] = DeliveryTool(settings).deliver_operator_digest(payload, chat_id=args.chat_id)
    if args.save:
        dump_json(settings.artifacts_dir / "ops" / "operator-digest.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


# ── resolve / reopen / approve / reject ─────────────

def cmd_resolve_triage_item(args: argparse.Namespace) -> int:
    resolved = build_store(settings=Settings.from_env(root_dir=ROOT_DIR), args=with_default_store_backend(args)).resolve_triage_item(
        triage_id=args.triage_id,
        resolved_at=args.resolved_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(resolved, ensure_ascii=False, indent=2))
    return 0


def cmd_reopen_triage_item(args: argparse.Namespace) -> int:
    reopened = build_store(settings=Settings.from_env(root_dir=ROOT_DIR), args=with_default_store_backend(args)).reopen_triage_item(
        triage_id=args.triage_id,
        reopened_at=args.reopened_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(reopened, ensure_ascii=False, indent=2))
    return 0


def cmd_approve_triage_reply(args: argparse.Namespace) -> int:
    approved = build_store(settings=Settings.from_env(root_dir=ROOT_DIR), args=with_default_store_backend(args)).approve_triage_reply(
        triage_id=args.triage_id,
        approved_by=args.approved_by,
        approved_at=args.approved_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(approved, ensure_ascii=False, indent=2))
    return 0


def cmd_reject_triage_reply(args: argparse.Namespace) -> int:
    rejected = build_store(settings=Settings.from_env(root_dir=ROOT_DIR), args=with_default_store_backend(args)).reject_triage_reply(
        triage_id=args.triage_id,
        reason=args.reason,
        rejected_at=args.rejected_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(rejected, ensure_ascii=False, indent=2))
    return 0


def cmd_mark_triage_reply_sent(args: argparse.Namespace) -> int:
    sent = build_store(settings=Settings.from_env(root_dir=ROOT_DIR), args=with_default_store_backend(args)).mark_triage_reply_sent(
        triage_id=args.triage_id,
        sent_at=args.sent_at,
        reply_permalink=args.reply_permalink,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(sent, ensure_ascii=False, indent=2))
    return 0


def cmd_approve_caption(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=with_default_store_backend(args))
    updated = store.approve_calendar_item(
        calendar_id=args.calendar_id,
        approved_by=args.approved_by,
        final_caption_ref=args.caption_file,
        approved_at=args.approved_at,
    )
    print(json.dumps(updated, ensure_ascii=False, indent=2))
    return 0


def cmd_reject_caption(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=with_default_store_backend(args))
    updated = store.reject_calendar_item(
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
