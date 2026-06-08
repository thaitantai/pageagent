from __future__ import annotations

import argparse
import json

from fanpage_agent.config import Settings
from fanpage_agent.main import (
    DEFAULT_CALENDAR_FILE,
    DEFAULT_HISTORY_FILE,
    DEFAULT_METRICS_FILE,
    DEFAULT_TRIAGE_FILE,
    ROOT_DIR,
    build_approval_audit_payload,
    build_calendar_store_payload,
    build_operator_digest_payload,
)
from fanpage_agent.tools.publishing.delivery import DeliveryTool
from fanpage_agent.utils import dump_json


def add_store_backend_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store-backend", choices=["local", "google"])


def register_subcommand(subparsers) -> None:
    # ── approval-audit ──
    p = subparsers.add_parser("approval-audit")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--as-of", required=True)
    p.add_argument("--sla-days", type=int, default=2)
    p.add_argument("--limit", type=int)
    p.add_argument("--save", action="store_true")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_approval_audit)

    # ── deliver-approval-audit ──
    p = subparsers.add_parser("deliver-approval-audit")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--as-of", required=True)
    p.add_argument("--sla-days", type=int, default=2)
    p.add_argument("--limit", type=int)
    p.add_argument("--save", action="store_true")
    p.add_argument("--chat-id")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_deliver_approval_audit)

    # ── deliver-approval-queue ──
    p = subparsers.add_parser("deliver-approval-queue")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--status")
    p.add_argument("--approval-status", default="pending")
    p.add_argument("--date")
    p.add_argument("--limit", type=int)
    p.add_argument("--save", action="store_true")
    p.add_argument("--chat-id")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_deliver_approval_queue)

    # ── deliver-metrics-backlog ──
    p = subparsers.add_parser("deliver-metrics-backlog")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--status", default="published")
    p.add_argument("--approval-status")
    p.add_argument("--date")
    p.add_argument("--metrics-pending", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument("--save", action="store_true")
    p.add_argument("--chat-id")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_deliver_metrics_backlog)

    # ── deliver-operator-digest ──
    p = subparsers.add_parser("deliver-operator-digest")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    p.add_argument("--calendar-status", default="planned")
    p.add_argument("--approval-status", default="pending")
    p.add_argument("--triage-status", default="approved")
    p.add_argument("--metrics-status", default="published")
    p.add_argument("--date")
    p.add_argument("--limit", type=int)
    p.add_argument("--skip-empty", action="store_true")
    p.add_argument("--save", action="store_true")
    p.add_argument("--chat-id")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_deliver_operator_digest)

    # ── list-calendar-items ──
    p = subparsers.add_parser("list-calendar-items")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--status")
    p.add_argument("--approval-status")
    p.add_argument("--date")
    p.add_argument("--metrics-pending", action="store_true")
    p.add_argument("--limit", type=int)
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_list_calendar_items)


# ── Command handlers (copied verbatim from fanpage_agent/main.py) ──

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
    if args.save:
        dump_json(settings.artifacts_dir / "approvals" / "approval-audit.json", payload)
    payload["delivery"] = DeliveryTool(settings).deliver_approval_audit(payload, chat_id=args.chat_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_approval_queue(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    payload = build_calendar_store_payload(args)
    if args.save:
        dump_json(settings.artifacts_dir / "approvals" / "approval-queue.json", payload)
    payload["delivery"] = DeliveryTool(settings).deliver_approval_queue(payload, chat_id=args.chat_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_metrics_backlog(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    payload = build_calendar_store_payload(args)
    if args.save:
        dump_json(settings.artifacts_dir / "metrics" / "metrics-backlog.json", payload)
    payload["delivery"] = DeliveryTool(settings).deliver_metrics_backlog(payload, chat_id=args.chat_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_operator_digest(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    payload = build_operator_digest_payload(args)
    if args.save:
        dump_json(settings.artifacts_dir / "ops" / "operator-digest.json", payload)
    if args.skip_empty and not any(payload["summary"].values()):
        payload["delivery"] = {
            "sent_count": 0,
            "results": [],
            "skipped": True,
            "reason": "empty_digest",
        }
    else:
        payload["delivery"] = DeliveryTool(settings).deliver_operator_digest(payload, chat_id=args.chat_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_list_calendar_items(args: argparse.Namespace) -> int:
    payload = build_calendar_store_payload(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0
