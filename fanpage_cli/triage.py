from __future__ import annotations

import argparse
import json

from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.main import (
    DEFAULT_CALENDAR_FILE,
    DEFAULT_COMMENT_FILE,
    DEFAULT_HISTORY_FILE,
    DEFAULT_METRICS_FILE,
    DEFAULT_TRIAGE_FILE,
    ROOT_DIR,
    add_store_backend_arg,
    build_triage_store_payload,
)
from fanpage_agent.services.community_triage import CommunityTriageService
from fanpage_agent.utils import dump_json


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    triage_parser = subparsers.add_parser("triage-community")
    triage_parser.add_argument("--brand-file", required=True)
    triage_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    triage_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_parser.add_argument("--write-store", action="store_true")
    triage_parser.add_argument("--save", action="store_true")
    add_store_backend_arg(triage_parser)
    triage_parser.set_defaults(_handler=cmd_triage_community)

    triage_list_parser = subparsers.add_parser("list-triage-items")
    triage_list_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_list_parser.add_argument("--status")
    triage_list_parser.add_argument("--priority")
    triage_list_parser.add_argument("--assigned-to")
    triage_list_parser.add_argument("--limit", type=int)
    triage_list_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    triage_list_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    triage_list_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(triage_list_parser)
    triage_list_parser.set_defaults(_handler=cmd_list_triage_items)

    triage_resolve_parser = subparsers.add_parser("resolve-triage-item")
    triage_resolve_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_resolve_parser.add_argument("--triage-id", required=True)
    triage_resolve_parser.add_argument("--resolved-at", required=True)
    triage_resolve_parser.add_argument("--assigned-to", default="")
    triage_resolve_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    triage_resolve_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    triage_resolve_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(triage_resolve_parser)
    triage_resolve_parser.set_defaults(_handler=cmd_resolve_triage_item)

    triage_reopen_parser = subparsers.add_parser("reopen-triage-item")
    triage_reopen_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_reopen_parser.add_argument("--triage-id", required=True)
    triage_reopen_parser.add_argument("--reopened-at", required=True)
    triage_reopen_parser.add_argument("--assigned-to", default="")
    triage_reopen_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    triage_reopen_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    triage_reopen_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(triage_reopen_parser)
    triage_reopen_parser.set_defaults(_handler=cmd_reopen_triage_item)

    triage_approve_parser = subparsers.add_parser("approve-triage-reply")
    triage_approve_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_approve_parser.add_argument("--triage-id", required=True)
    triage_approve_parser.add_argument("--approved-by", required=True)
    triage_approve_parser.add_argument("--approved-at", required=True)
    triage_approve_parser.add_argument("--assigned-to", default="")
    triage_approve_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    triage_approve_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    triage_approve_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(triage_approve_parser)
    triage_approve_parser.set_defaults(_handler=cmd_approve_triage_reply)

    triage_reject_parser = subparsers.add_parser("reject-triage-reply")
    triage_reject_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_reject_parser.add_argument("--triage-id", required=True)
    triage_reject_parser.add_argument("--reason", required=True)
    triage_reject_parser.add_argument("--rejected-at", required=True)
    triage_reject_parser.add_argument("--assigned-to", default="")
    triage_reject_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    triage_reject_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    triage_reject_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(triage_reject_parser)
    triage_reject_parser.set_defaults(_handler=cmd_reject_triage_reply)

    triage_sent_parser = subparsers.add_parser("mark-triage-reply-sent")
    triage_sent_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_sent_parser.add_argument("--triage-id", required=True)
    triage_sent_parser.add_argument("--sent-at", required=True)
    triage_sent_parser.add_argument("--reply-permalink", required=True)
    triage_sent_parser.add_argument("--assigned-to", default="")
    triage_sent_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    triage_sent_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    triage_sent_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(triage_sent_parser)
    triage_sent_parser.set_defaults(_handler=cmd_mark_triage_reply_sent)


def cmd_triage_community(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    batch = CommunityTriageService().triage_from_csv(profile=profile, comment_csv=args.comment_file)
    payload = batch.model_dump(mode="json")
    if args.write_store:
        payload["store"] = {
            "persisted": build_store(settings=settings, args=args).upsert_triage_items(profile.brand_id, batch.items)
        }
    if args.save:
        dump_json(settings.artifacts_dir / "community" / "community-triage.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_list_triage_items(args: argparse.Namespace) -> int:
    payload = build_triage_store_payload(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_resolve_triage_item(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=args).resolve_triage_item(
        triage_id=args.triage_id,
        resolved_at=args.resolved_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_reopen_triage_item(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=args).reopen_triage_item(
        triage_id=args.triage_id,
        reopened_at=args.reopened_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_approve_triage_reply(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=args).approve_triage_reply(
        triage_id=args.triage_id,
        approved_by=args.approved_by,
        approved_at=args.approved_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_reject_triage_reply(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=args).reject_triage_reply(
        triage_id=args.triage_id,
        reason=args.reason,
        rejected_at=args.rejected_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_mark_triage_reply_sent(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=args).mark_triage_reply_sent(
        triage_id=args.triage_id,
        sent_at=args.sent_at,
        reply_permalink=args.reply_permalink,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0
