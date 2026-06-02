from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.adapters.telegram_client import TelegramClient
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.services.analytics import AnalyticsService
from fanpage_agent.services.community_triage import CommunityTriageService
from fanpage_agent.services.daily_ops import DailyOpsService
from fanpage_agent.services.delivery import DeliveryService
from fanpage_agent.services.evals import EvalService
from fanpage_agent.services.planner import PlannerService
from fanpage_agent.services.research import ResearchService
from fanpage_agent.services.telegram_formatter import TelegramFormatterService
from fanpage_agent.services.auto_approval import (
    AutoApprovalConfig,
    AutoApprovalEngine,
)
from fanpage_agent.services.scheduled_publish import ScheduledPublishService
from fanpage_agent.services.verifier import VerifierService
from fanpage_agent.services.writer import WriterService
from fanpage_agent.utils import dump_json


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CALENDAR_FILE = ROOT_DIR / "data" / "content_calendar.csv"
DEFAULT_HISTORY_FILE = ROOT_DIR / "data" / "post_history.csv"
DEFAULT_METRICS_FILE = ROOT_DIR / "data" / "post_metrics.csv"
DEFAULT_COMMENT_FILE = ROOT_DIR / "data" / "comment_inbox.csv"
DEFAULT_TRIAGE_FILE = ROOT_DIR / "data" / "comment_triage.csv"
DEFAULT_CAMPAIGN_FILE = ROOT_DIR / "data" / "campaign_notes.json"
DEFAULT_HERMES_CRON_JOBS_FILE = Path.home() / ".hermes" / "cron" / "jobs.json"
DEFAULT_HERMES_SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"

EXPECTED_HERMES_CRON_JOBS = {
    "fanpage-agent research brief": {
        "schedule": "30 0 * * *",
        "script": "fanpage-agent-research-brief.sh",
        "project_script": "scripts/run_research_brief.sh",
    },
    "fanpage-agent daily packet": {
        "schedule": "0 1 * * *",
        "script": "fanpage-agent-daily-packet.sh",
        "project_script": "scripts/run_daily_packet.sh",
    },
    "fanpage-agent approval queue": {
        "schedule": "30 1 * * *",
        "script": "fanpage-agent-approval-queue.sh",
        "project_script": "scripts/run_approval_queue.sh",
    },
    "fanpage-agent operator digest": {
        "schedule": "0 2 * * *",
        "script": "fanpage-agent-operator-digest.sh",
        "project_script": "scripts/run_operator_digest.sh",
    },
    "fanpage-agent weekly report": {
        "schedule": "0 2 * * 1",
        "script": "fanpage-agent-weekly-report.sh",
        "project_script": "scripts/run_weekly_report.sh",
    },
    "fanpage-agent approval audit": {
        "schedule": "0 3 * * *",
        "script": "fanpage-agent-approval-audit.sh",
        "project_script": "scripts/run_approval_audit.sh",
    },
    "fanpage-agent metrics backlog": {
        "schedule": "30 3 * * *",
        "script": "fanpage-agent-metrics-backlog.sh",
        "project_script": "scripts/run_metrics_backlog.sh",
    },
    "fanpage-agent triage community": {
        "schedule": "0 */2 * * *",
        "script": "fanpage-agent-triage-community.sh",
        "project_script": "scripts/run_triage_community.sh",
    },
    "fanpage-agent approved triage replies": {
        "schedule": "15 */2 * * *",
        "script": "fanpage-agent-approved-triage-replies.sh",
        "project_script": "scripts/run_approved_triage_replies.sh",
    },
}

OPS_ARTIFACT_FRESHNESS_HOURS = {
    "daily_ops_latest": 30.0,
    "operator_digest": 30.0,
    "approval_audit": 30.0,
    "weekly_report": 192.0,
    "research_brief": 30.0,
    "eval_latest": 30.0,
}


def add_store_backend_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store-backend", choices=["local", "google"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fanpage-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan-week")
    plan_parser.add_argument("--brand-file", required=True)
    plan_parser.add_argument("--start-date", required=True)
    plan_parser.add_argument("--days", type=int, default=7)
    plan_parser.add_argument("--save", action="store_true")
    plan_parser.add_argument("--write-calendar", action="store_true")
    plan_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    plan_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    add_store_backend_arg(plan_parser)

    research_parser = subparsers.add_parser("research-brief")
    research_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    research_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    research_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    research_parser.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE))
    research_parser.add_argument("--save", action="store_true")
    research_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    add_store_backend_arg(research_parser)

    research_delivery_parser = subparsers.add_parser("deliver-research-brief")
    research_delivery_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    research_delivery_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    research_delivery_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    research_delivery_parser.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE))
    research_delivery_parser.add_argument("--save", action="store_true")
    research_delivery_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    research_delivery_parser.add_argument("--chat-id")
    add_store_backend_arg(research_delivery_parser)

    daily_parser = subparsers.add_parser("run-daily")
    daily_parser.add_argument("--brand-file", required=True)
    daily_parser.add_argument("--run-date", required=True)
    daily_parser.add_argument("--days", type=int, default=1)
    daily_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    daily_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    daily_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    daily_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    daily_parser.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE))
    daily_parser.add_argument("--write-calendar", action="store_true")
    daily_parser.add_argument("--save", action="store_true")
    add_store_backend_arg(daily_parser)

    daily_delivery_parser = subparsers.add_parser("deliver-daily-packet")
    daily_delivery_parser.add_argument("--brand-file", required=True)
    daily_delivery_parser.add_argument("--run-date", required=True)
    daily_delivery_parser.add_argument("--days", type=int, default=1)
    daily_delivery_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    daily_delivery_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    daily_delivery_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    daily_delivery_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    daily_delivery_parser.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE))
    daily_delivery_parser.add_argument("--write-calendar", action="store_true")
    daily_delivery_parser.add_argument("--save", action="store_true")
    daily_delivery_parser.add_argument("--chat-id")
    add_store_backend_arg(daily_delivery_parser)

    triage_parser = subparsers.add_parser("triage-community")
    triage_parser.add_argument("--brand-file", required=True)
    triage_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    triage_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_parser.add_argument("--write-store", action="store_true")
    triage_parser.add_argument("--save", action="store_true")
    add_store_backend_arg(triage_parser)

    triage_delivery_parser = subparsers.add_parser("deliver-triage-community")
    triage_delivery_parser.add_argument("--brand-file", required=True)
    triage_delivery_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    triage_delivery_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_delivery_parser.add_argument("--write-store", action="store_true")
    triage_delivery_parser.add_argument("--from-store", action="store_true")
    triage_delivery_parser.add_argument("--status")
    triage_delivery_parser.add_argument("--priority")
    triage_delivery_parser.add_argument("--assigned-to")
    triage_delivery_parser.add_argument("--limit", type=int)
    triage_delivery_parser.add_argument("--save", action="store_true")
    triage_delivery_parser.add_argument("--chat-id")
    add_store_backend_arg(triage_delivery_parser)

    approved_replies_parser = subparsers.add_parser("deliver-approved-triage-replies")
    approved_replies_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    approved_replies_parser.add_argument("--status", default="approved")
    approved_replies_parser.add_argument("--priority")
    approved_replies_parser.add_argument("--assigned-to")
    approved_replies_parser.add_argument("--limit", type=int)
    approved_replies_parser.add_argument("--save", action="store_true")
    approved_replies_parser.add_argument("--chat-id")
    approved_replies_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    approved_replies_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    approved_replies_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(approved_replies_parser)

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

    triage_resolve_parser = subparsers.add_parser("resolve-triage-item")
    triage_resolve_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_resolve_parser.add_argument("--triage-id", required=True)
    triage_resolve_parser.add_argument("--resolved-at", required=True)
    triage_resolve_parser.add_argument("--assigned-to", default="")
    triage_resolve_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    triage_resolve_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    triage_resolve_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(triage_resolve_parser)

    triage_reopen_parser = subparsers.add_parser("reopen-triage-item")
    triage_reopen_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    triage_reopen_parser.add_argument("--triage-id", required=True)
    triage_reopen_parser.add_argument("--reopened-at", required=True)
    triage_reopen_parser.add_argument("--assigned-to", default="")
    triage_reopen_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    triage_reopen_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    triage_reopen_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(triage_reopen_parser)

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

    calendar_list_parser = subparsers.add_parser("list-calendar-items")
    calendar_list_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    calendar_list_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    calendar_list_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    calendar_list_parser.add_argument("--status")
    calendar_list_parser.add_argument("--approval-status")
    calendar_list_parser.add_argument("--date")
    calendar_list_parser.add_argument("--metrics-pending", action="store_true")
    calendar_list_parser.add_argument("--limit", type=int)
    add_store_backend_arg(calendar_list_parser)

    approval_queue_parser = subparsers.add_parser("deliver-approval-queue")
    approval_queue_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    approval_queue_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    approval_queue_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    approval_queue_parser.add_argument("--status")
    approval_queue_parser.add_argument("--approval-status", default="pending")
    approval_queue_parser.add_argument("--date")
    approval_queue_parser.add_argument("--limit", type=int)
    approval_queue_parser.add_argument("--save", action="store_true")
    approval_queue_parser.add_argument("--chat-id")
    add_store_backend_arg(approval_queue_parser)

    approval_audit_parser = subparsers.add_parser("approval-audit")
    approval_audit_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    approval_audit_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    approval_audit_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    approval_audit_parser.add_argument("--as-of", required=True)
    approval_audit_parser.add_argument("--sla-days", type=int, default=2)
    approval_audit_parser.add_argument("--limit", type=int)
    approval_audit_parser.add_argument("--save", action="store_true")
    add_store_backend_arg(approval_audit_parser)

    approval_audit_delivery_parser = subparsers.add_parser("deliver-approval-audit")
    approval_audit_delivery_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    approval_audit_delivery_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    approval_audit_delivery_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    approval_audit_delivery_parser.add_argument("--as-of", required=True)
    approval_audit_delivery_parser.add_argument("--sla-days", type=int, default=2)
    approval_audit_delivery_parser.add_argument("--limit", type=int)
    approval_audit_delivery_parser.add_argument("--save", action="store_true")
    approval_audit_delivery_parser.add_argument("--chat-id")
    add_store_backend_arg(approval_audit_delivery_parser)

    metrics_backlog_parser = subparsers.add_parser("deliver-metrics-backlog")
    metrics_backlog_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    metrics_backlog_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    metrics_backlog_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    metrics_backlog_parser.add_argument("--status", default="published")
    metrics_backlog_parser.add_argument("--approval-status")
    metrics_backlog_parser.add_argument("--date")
    metrics_backlog_parser.add_argument("--metrics-pending", action="store_true")
    metrics_backlog_parser.add_argument("--limit", type=int)
    metrics_backlog_parser.add_argument("--save", action="store_true")
    metrics_backlog_parser.add_argument("--chat-id")
    add_store_backend_arg(metrics_backlog_parser)

    operator_digest_parser = subparsers.add_parser("deliver-operator-digest")
    operator_digest_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    operator_digest_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    operator_digest_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    operator_digest_parser.add_argument("--triage-file", default=str(DEFAULT_TRIAGE_FILE))
    operator_digest_parser.add_argument("--calendar-status", default="planned")
    operator_digest_parser.add_argument("--approval-status", default="pending")
    operator_digest_parser.add_argument("--triage-status", default="approved")
    operator_digest_parser.add_argument("--metrics-status", default="published")
    operator_digest_parser.add_argument("--date")
    operator_digest_parser.add_argument("--limit", type=int)
    operator_digest_parser.add_argument("--skip-empty", action="store_true")
    operator_digest_parser.add_argument("--save", action="store_true")
    operator_digest_parser.add_argument("--chat-id")
    add_store_backend_arg(operator_digest_parser)

    caption_parser = subparsers.add_parser("write-caption")
    caption_parser.add_argument("--brand-file", required=True)
    caption_parser.add_argument("--topic", required=True)
    caption_parser.add_argument("--pillar", required=True)
    caption_parser.add_argument("--objective", required=True)
    caption_parser.add_argument("--format", default="post_short")
    caption_parser.add_argument("--save", action="store_true")

    approve_parser = subparsers.add_parser("approve-caption")
    approve_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    approve_parser.add_argument("--calendar-id", required=True)
    approve_parser.add_argument("--approved-by", required=True)
    approve_parser.add_argument("--caption-file", required=True)
    approve_parser.add_argument("--approved-at", required=True)
    approve_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    approve_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(approve_parser)

    reject_parser = subparsers.add_parser("reject-caption")
    reject_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    reject_parser.add_argument("--calendar-id", required=True)
    reject_parser.add_argument("--reason", required=True)
    reject_parser.add_argument("--rejected-at", required=True)
    reject_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    reject_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(reject_parser)

    publish_parser = subparsers.add_parser("publish-post")
    publish_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    publish_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    publish_parser.add_argument("--calendar-id", required=True)
    publish_parser.add_argument("--published-at", required=True)
    publish_parser.add_argument("--permalink", required=True)
    publish_parser.add_argument("--reach", type=int, default=0)
    publish_parser.add_argument("--engagement-rate", type=float, default=0.0)
    publish_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(publish_parser)

    # ── process-pending: auto-approve eligible items ──────────
    process_parser = subparsers.add_parser("process-pending")
    process_parser.add_argument("--brand-file", required=True)
    process_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    process_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    process_parser.add_argument("--no-verify", action="store_true")
    process_parser.add_argument("--skip-ban", action="store_true")
    process_parser.add_argument("--skip-duplicate", action="store_true")

    # ── scheduled-publish: publish approved + due items ───────
    scheduled_parser = subparsers.add_parser("scheduled-publish")
    scheduled_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    scheduled_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    scheduled_parser.add_argument("--reference-date")
    scheduled_parser.add_argument("--brand-file", default=str(ROOT_DIR / "data" / "sample" / "brand_profile.json"))

    record_metrics_parser = subparsers.add_parser("record-post-metrics")
    record_metrics_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    record_metrics_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    record_metrics_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    record_metrics_parser.add_argument("--calendar-id", required=True)
    record_metrics_parser.add_argument("--reach", type=int, required=True)
    record_metrics_parser.add_argument("--engagements", type=int, required=True)
    record_metrics_parser.add_argument("--leads", type=int, required=True)
    record_metrics_parser.add_argument("--recorded-at", required=True)
    add_store_backend_arg(record_metrics_parser)

    report_parser = subparsers.add_parser("weekly-report")
    report_parser.add_argument("--brand-file", required=True)
    report_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    report_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    report_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    report_parser.add_argument("--save", action="store_true")
    add_store_backend_arg(report_parser)

    report_delivery_parser = subparsers.add_parser("deliver-weekly-report")
    report_delivery_parser.add_argument("--brand-file", required=True)
    report_delivery_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    report_delivery_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    report_delivery_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    report_delivery_parser.add_argument("--save", action="store_true")
    report_delivery_parser.add_argument("--chat-id")
    add_store_backend_arg(report_delivery_parser)

    ops_status_parser = subparsers.add_parser("ops-status")
    ops_status_parser.add_argument(
        "--max-age-hours",
        action="append",
        default=[],
        help="Override freshness threshold, e.g. operator_digest=24 or operator_digest=24,weekly_report=192.",
    )
    ops_status_parser.add_argument(
        "--now",
        help="Timestamp used for freshness checks. Accepts ISO-8601 or Unix epoch seconds. Defaults to current time.",
    )
    ops_status_parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Return exit code 1 when any existing artifact is stale.",
    )

    hermes_cron_parser = subparsers.add_parser("hermes-cron-status")
    hermes_cron_parser.add_argument("--jobs-file", default=str(DEFAULT_HERMES_CRON_JOBS_FILE))
    hermes_cron_parser.add_argument("--scripts-dir", default=str(DEFAULT_HERMES_SCRIPTS_DIR))
    hermes_cron_parser.add_argument("--workdir", default=str(ROOT_DIR))

    eval_parser = subparsers.add_parser("eval-all")
    eval_parser.add_argument("--brand-file", required=True)
    eval_parser.add_argument("--start-date", default="2026-06-20")
    eval_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    eval_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    eval_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    eval_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    eval_parser.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE))
    eval_parser.add_argument("--save", action="store_true")
    add_store_backend_arg(eval_parser)

    telegram_parser = subparsers.add_parser("preview-telegram")
    telegram_parser.add_argument("--artifact-type", required=True, choices=["plan", "caption", "report", "triage", "approved_replies", "approval", "approval_audit", "metrics", "operator", "research"])
    telegram_parser.add_argument("--input-file", required=True)

    telegram_send_parser = subparsers.add_parser("send-telegram-preview")
    telegram_send_parser.add_argument("--artifact-type", required=True, choices=["plan", "caption", "report", "triage", "approved_replies", "approval", "approval_audit", "metrics", "operator", "research"])
    telegram_send_parser.add_argument("--input-file", required=True)
    telegram_send_parser.add_argument("--chat-id")

    return parser


def build_research_brief(args: argparse.Namespace):
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    return ResearchService().build_brief(
        store=store,
        comment_csv=args.comment_file,
        campaign_notes_file=args.campaign_file,
    )


def summarize_triage_items(items: list[dict]) -> dict:
    summary: dict[str, object] = {
        "total_items": len(items),
        "by_category": {},
        "by_priority": {},
        "by_status": {},
        "escalation_count": 0,
        "approval_required_count": 0,
    }
    by_category: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_status: dict[str, int] = {}
    escalation_count = 0
    approval_required_count = 0
    for item in items:
        category = str(item.get("category", "") or "unknown")
        priority = str(item.get("priority", "") or "unknown")
        status = str(item.get("status", "") or "unknown")
        by_category[category] = by_category.get(category, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        if str(item.get("escalation_required", "")).lower() == "true":
            escalation_count += 1
        if str(item.get("requires_human_approval", "")).lower() == "true":
            approval_required_count += 1
    summary["by_category"] = by_category
    summary["by_priority"] = by_priority
    summary["by_status"] = by_status
    summary["escalation_count"] = escalation_count
    summary["approval_required_count"] = approval_required_count
    return summary


def summarize_calendar_items(items: list[dict]) -> dict:
    summary: dict[str, object] = {
        "total_items": len(items),
        "by_status": {},
        "by_approval_status": {},
        "by_pillar": {},
    }
    by_status: dict[str, int] = {}
    by_approval_status: dict[str, int] = {}
    by_pillar: dict[str, int] = {}
    for item in items:
        status = str(item.get("status", "") or "unknown")
        approval_status = str(item.get("approval_status", "") or "unknown")
        pillar = str(item.get("pillar", "") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_approval_status[approval_status] = by_approval_status.get(approval_status, 0) + 1
        by_pillar[pillar] = by_pillar.get(pillar, 0) + 1
    summary["by_status"] = by_status
    summary["by_approval_status"] = by_approval_status
    summary["by_pillar"] = by_pillar
    return summary


def build_daily_artifacts(settings: Settings, packet: dict, run_date: str) -> dict[str, str]:
    packet_path = settings.artifacts_dir / "ops" / f"daily-ops-{run_date}.json"
    calendar_id = str(packet.get("calendar_id", "daily-packet")).replace("/", "-")
    caption_path = settings.artifacts_dir / "captions" / f"daily-caption-{calendar_id}.json"
    dump_json(packet_path, packet)
    dump_json(caption_path, packet.get("caption_package", {}))
    return {
        "packet": str(packet_path),
        "caption_package": str(caption_path),
    }


def build_triage_store_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    items = build_store(settings=settings, args=args).list_triage_items(
        status=getattr(args, "status", None),
        priority=getattr(args, "priority", None),
        assigned_to=getattr(args, "assigned_to", None),
        limit=getattr(args, "limit", None),
    )
    return {
        "items": items,
        "summary": summarize_triage_items(items),
    }


def build_calendar_store_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    items = build_store(settings=settings, args=args).list_calendar_items(
        status=getattr(args, "status", None),
        approval_status=getattr(args, "approval_status", None),
        date=getattr(args, "date", None),
        metrics_pending=getattr(args, "metrics_pending", False),
        limit=getattr(args, "limit", None),
    )
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
            "total_items": len(rows),
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


def build_operator_digest_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    limit = getattr(args, "limit", None)
    approval_items = store.list_calendar_items(
        status=getattr(args, "calendar_status", None),
        approval_status=getattr(args, "approval_status", "pending"),
        date=getattr(args, "date", None),
        metrics_pending=False,
        limit=limit,
    )
    approved_replies = store.list_triage_items(
        status=getattr(args, "triage_status", "approved"),
        priority=None,
        assigned_to=None,
        limit=limit,
    )
    metrics_backlog = store.list_calendar_items(
        status=getattr(args, "metrics_status", "published"),
        approval_status=None,
        date=getattr(args, "date", None),
        metrics_pending=True,
        limit=limit,
    )
    return {
        "summary": {
            "pending_captions": len(approval_items),
            "approved_replies": len(approved_replies),
            "metrics_backlog": len(metrics_backlog),
        },
        "approval_queue": {
            "items": approval_items,
            "summary": summarize_calendar_items(approval_items),
        },
        "approved_replies": {
            "items": approved_replies,
            "summary": summarize_triage_items(approved_replies),
        },
        "metrics_backlog": {
            "items": metrics_backlog,
            "summary": summarize_calendar_items(metrics_backlog),
        },
    }


def cmd_plan_week(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    planner = PlannerService(llm_client=build_llm_client(settings))
    verifier = VerifierService()
    store = build_store(settings=settings, args=args)
    plan = planner.plan_week(profile, args.start_date, args.days)
    verification = verifier.verify_plan(profile, plan, history=store.read_post_history(limit=30))
    payload = plan.model_dump(mode="json")
    payload["verification"] = verification.model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "plans" / f"{plan.plan_title}.json", payload)
    if args.write_calendar:
        store.append_plan(profile.brand_id, plan)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if verification.passed else 1


def cmd_research_brief(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    brief = build_research_brief(args)
    payload = brief.model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "research" / "research-brief.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_research_brief(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    brief = build_research_brief(args)
    payload = brief.model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "research" / "research-brief.json", payload)
    payload["delivery"] = DeliveryService(settings).deliver_research_brief(payload, chat_id=args.chat_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_run_daily(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings)
    store = build_store(settings=settings, args=args)
    research_brief = ResearchService().build_brief(
        store=store,
        comment_csv=args.comment_file,
        campaign_notes_file=args.campaign_file,
    )
    packet = DailyOpsService(
        planner=PlannerService(llm_client=llm_client),
        writer=WriterService(llm_client=llm_client),
    ).build_packet(
        profile=profile,
        run_date=args.run_date,
        store=store,
        days=args.days,
        write_calendar=args.write_calendar,
        research_brief=research_brief,
    )
    if args.save:
        packet["artifacts"] = build_daily_artifacts(settings, packet, args.run_date)
        if args.write_calendar:
            packet["store"] = {
                "calendar": store.attach_draft_caption_ref(
                    calendar_id=packet["calendar_id"],
                    caption_ref=packet["artifacts"]["caption_package"],
                    updated_at=args.run_date,
                )
            }
    print(json.dumps(packet, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_daily_packet(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings)
    store = build_store(settings=settings, args=args)
    research_brief = ResearchService().build_brief(
        store=store,
        comment_csv=args.comment_file,
        campaign_notes_file=args.campaign_file,
    )
    packet = DailyOpsService(
        planner=PlannerService(llm_client=llm_client),
        writer=WriterService(llm_client=llm_client),
    ).build_packet(
        profile=profile,
        run_date=args.run_date,
        store=store,
        days=args.days,
        write_calendar=args.write_calendar,
        research_brief=research_brief,
    )
    if args.save:
        packet["artifacts"] = build_daily_artifacts(settings, packet, args.run_date)
        if args.write_calendar:
            packet["store"] = {
                "calendar": store.attach_draft_caption_ref(
                    calendar_id=packet["calendar_id"],
                    caption_ref=packet["artifacts"]["caption_package"],
                    updated_at=args.run_date,
                )
            }
    packet["delivery"] = DeliveryService(settings).deliver_daily_packet(packet, chat_id=args.chat_id)
    print(json.dumps(packet, ensure_ascii=False, indent=2))
    return 0


def cmd_write_caption(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    writer = WriterService(llm_client=build_llm_client(settings))
    verifier = VerifierService()
    package = writer.write_caption(profile, args.topic, args.pillar, args.objective, args.format)
    verification = verifier.verify_caption_package(profile, package)
    payload = package.model_dump(mode="json")
    payload["verification"] = verification.model_dump(mode="json")
    if args.save:
        safe_name = args.topic.lower().replace(" ", "-")[:40]
        dump_json(settings.artifacts_dir / "captions" / f"{safe_name}.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if verification.passed else 1


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


def cmd_deliver_triage_community(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    if args.from_store:
        payload = build_triage_store_payload(args)
    else:
        profile = load_brand_profile(args.brand_file)
        batch = CommunityTriageService().triage_from_csv(profile=profile, comment_csv=args.comment_file)
        payload = batch.model_dump(mode="json")
        if args.write_store:
            payload["store"] = {
                "persisted": build_store(settings=settings, args=args).upsert_triage_items(profile.brand_id, batch.items)
            }
    if args.save:
        dump_json(settings.artifacts_dir / "community" / "community-triage.json", payload)
    payload["delivery"] = DeliveryService(settings).deliver_community_triage(payload, chat_id=args.chat_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_approved_triage_replies(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    payload = build_triage_store_payload(args)
    if args.save:
        dump_json(settings.artifacts_dir / "community" / "approved-triage-replies.json", payload)
    payload["delivery"] = DeliveryService(settings).deliver_approved_triage_replies(payload, chat_id=args.chat_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_list_triage_items(args: argparse.Namespace) -> int:
    payload = build_triage_store_payload(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_list_calendar_items(args: argparse.Namespace) -> int:
    payload = build_calendar_store_payload(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_approval_queue(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    payload = build_calendar_store_payload(args)
    if args.save:
        dump_json(settings.artifacts_dir / "approvals" / "approval-queue.json", payload)
    payload["delivery"] = DeliveryService(settings).deliver_approval_queue(payload, chat_id=args.chat_id)
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
    if args.save:
        dump_json(settings.artifacts_dir / "approvals" / "approval-audit.json", payload)
    payload["delivery"] = DeliveryService(settings).deliver_approval_audit(payload, chat_id=args.chat_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_metrics_backlog(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    payload = build_calendar_store_payload(args)
    if args.save:
        dump_json(settings.artifacts_dir / "metrics" / "metrics-backlog.json", payload)
    payload["delivery"] = DeliveryService(settings).deliver_metrics_backlog(payload, chat_id=args.chat_id)
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
        payload["delivery"] = DeliveryService(settings).deliver_operator_digest(payload, chat_id=args.chat_id)
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


def cmd_approve_caption(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=args).approve_calendar_item(
        calendar_id=args.calendar_id,
        approved_by=args.approved_by,
        final_caption_ref=args.caption_file,
        approved_at=args.approved_at,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_reject_caption(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=args).reject_calendar_item(
        calendar_id=args.calendar_id,
        reason=args.reason,
        rejected_at=args.rejected_at,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_publish_post(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=args).publish_calendar_item(
        calendar_id=args.calendar_id,
        published_at=args.published_at,
        permalink=args.permalink,
        reach=args.reach,
        engagement_rate=args.engagement_rate,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_process_pending(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    store = LocalSheetStore(
        calendar_csv=args.calendar_file,
        history_csv=args.history_file,
    )
    verifier = VerifierService()

    config = AutoApprovalConfig(
        skip_banned_phrases=not args.skip_ban,
        skip_duplicate_topics=not args.skip_duplicate,
        require_verification_pass=not args.no_verify,
    )
    engine = AutoApprovalEngine(
        brand_profile=profile,
        store=store,
        verifier=verifier,
        config=config,
    )
    result = engine.process_pending()
    payload = result.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_scheduled_publish(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    store = LocalSheetStore(
        calendar_csv=args.calendar_file,
        history_csv=args.history_file,
    )

    service = ScheduledPublishService(
        store=store,
        brand_id=profile.brand_id,
        verifier=VerifierService(),
        brand_profile=profile,
    )
    result = service.publish_due(reference_date=args.reference_date)
    payload = result.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_record_post_metrics(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    payload = build_store(settings=settings, args=args).record_post_metrics(
        calendar_id=args.calendar_id,
        reach=args.reach,
        engagements=args.engagements,
        leads=args.leads,
        recorded_at=args.recorded_at,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_weekly_report(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    _ = load_brand_profile(args.brand_file)
    metrics = build_store(settings=settings, args=args).read_post_metrics()
    report = AnalyticsService().build_weekly_report(metrics)
    payload = report.model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "reports" / "weekly-report.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_weekly_report(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    _ = load_brand_profile(args.brand_file)
    metrics = build_store(settings=settings, args=args).read_post_metrics()
    payload = AnalyticsService().build_weekly_report(metrics).model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "reports" / "weekly-report.json", payload)
    payload["delivery"] = DeliveryService(settings).deliver_weekly_report(payload, chat_id=args.chat_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_timestamp(raw: str | None) -> float:
    if not raw:
        return time.time()
    try:
        return float(raw)
    except ValueError:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()


def _parse_freshness_thresholds(overrides: list[str] | None = None) -> dict[str, float]:
    thresholds = dict(OPS_ARTIFACT_FRESHNESS_HOURS)
    for raw in overrides or []:
        for pair in raw.split(","):
            if not pair.strip():
                continue
            if "=" not in pair:
                raise ValueError(f"Invalid --max-age-hours value: {pair!r}. Expected name=hours.")
            name, hours = pair.split("=", 1)
            artifact_name = name.strip()
            if artifact_name not in thresholds:
                raise ValueError(
                    f"Unknown artifact for --max-age-hours: {artifact_name!r}. "
                    f"Expected one of: {', '.join(sorted(thresholds))}."
                )
            thresholds[artifact_name] = float(hours.strip())
    return thresholds


def _artifact_status(name: str, path: Path, *, now_timestamp: float, max_age_hours: float) -> dict:
    status = {
        "name": name,
        "path": str(path),
        "exists": path.exists(),
        "freshness": {
            "max_age_hours": max_age_hours,
        },
    }
    if not path.exists():
        status["freshness"].update({"stale": False, "reason": "missing"})
        return status
    stat = path.stat()
    age_hours = max(0.0, (now_timestamp - stat.st_mtime) / 3600)
    status["size_bytes"] = stat.st_size
    status["modified_at"] = stat.st_mtime
    status["freshness"].update(
        {
            "age_hours": round(age_hours, 3),
            "stale": age_hours > max_age_hours,
        }
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        status["json_valid"] = False
        return status
    status["json_valid"] = True
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        status["summary"] = payload["summary"]
    if isinstance(payload, dict) and isinstance(payload.get("delivery"), dict):
        delivery = payload["delivery"]
        status["delivery"] = {
            "sent_count": delivery.get("sent_count"),
            "skipped": delivery.get("skipped", False),
            "reason": delivery.get("reason", ""),
        }
    return status


def _latest_artifact(
    name: str,
    directory: Path,
    pattern: str,
    *,
    now_timestamp: float,
    max_age_hours: float,
) -> dict:
    matches = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    if not matches:
        return {
            "name": name,
            "path": str(directory / pattern),
            "exists": False,
            "freshness": {
                "max_age_hours": max_age_hours,
                "stale": False,
                "reason": "missing",
            },
        }
    return _artifact_status(name, matches[0], now_timestamp=now_timestamp, max_age_hours=max_age_hours)


def build_ops_status_payload(
    settings: Settings,
    *,
    now_timestamp: float | None = None,
    freshness_thresholds: dict[str, float] | None = None,
) -> dict:
    now = time.time() if now_timestamp is None else now_timestamp
    thresholds = freshness_thresholds or dict(OPS_ARTIFACT_FRESHNESS_HOURS)
    artifacts = [
        _latest_artifact(
            "daily_ops_latest",
            settings.artifacts_dir / "ops",
            "daily-ops-*.json",
            now_timestamp=now,
            max_age_hours=thresholds["daily_ops_latest"],
        ),
        _artifact_status(
            "operator_digest",
            settings.artifacts_dir / "ops" / "operator-digest.json",
            now_timestamp=now,
            max_age_hours=thresholds["operator_digest"],
        ),
        _artifact_status(
            "approval_audit",
            settings.artifacts_dir / "approvals" / "approval-audit.json",
            now_timestamp=now,
            max_age_hours=thresholds["approval_audit"],
        ),
        _artifact_status(
            "weekly_report",
            settings.artifacts_dir / "reports" / "weekly-report.json",
            now_timestamp=now,
            max_age_hours=thresholds["weekly_report"],
        ),
        _artifact_status(
            "research_brief",
            settings.artifacts_dir / "research" / "research-brief.json",
            now_timestamp=now,
            max_age_hours=thresholds["research_brief"],
        ),
        _latest_artifact(
            "eval_latest",
            settings.artifacts_dir / "evals",
            "eval-summary-*.json",
            now_timestamp=now,
            max_age_hours=thresholds["eval_latest"],
        ),
    ]
    existing = sum(1 for item in artifacts if item["exists"])
    stale = sum(1 for item in artifacts if item["exists"] and item.get("freshness", {}).get("stale"))
    fresh = sum(1 for item in artifacts if item["exists"] and not item.get("freshness", {}).get("stale"))
    return {
        "artifacts_dir": str(settings.artifacts_dir),
        "freshness_checked_at": now,
        "summary": {
            "existing": existing,
            "missing": len(artifacts) - existing,
            "fresh": fresh,
            "stale": stale,
        },
        "artifacts": artifacts,
    }


def cmd_ops_status(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    try:
        now_timestamp = _parse_timestamp(args.now)
        thresholds = _parse_freshness_thresholds(args.max_age_hours)
    except ValueError as exc:
        raise SystemExit(f"ops-status: {exc}") from exc
    payload = build_ops_status_payload(settings, now_timestamp=now_timestamp, freshness_thresholds=thresholds)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if args.fail_on_stale and payload["summary"]["stale"] else 0


def _cron_schedule_display(job: dict) -> str:
    if job.get("schedule_display"):
        return str(job["schedule_display"])
    schedule = job.get("schedule")
    if isinstance(schedule, dict):
        return str(schedule.get("display") or schedule.get("expr") or "")
    return str(schedule or "")


def _load_hermes_jobs(jobs_file: Path) -> list[dict]:
    if not jobs_file.exists():
        return []
    payload = json.loads(jobs_file.read_text(encoding="utf-8"))
    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        return []
    return [job for job in jobs if isinstance(job, dict)]


def _check_wrapper(wrapper_path: Path, project_script: str) -> dict:
    status = {
        "path": str(wrapper_path),
        "exists": wrapper_path.exists(),
        "executable": wrapper_path.exists() and wrapper_path.stat().st_mode & 0o111 != 0,
        "targets_project_script": False,
    }
    if wrapper_path.exists():
        text = wrapper_path.read_text(encoding="utf-8")
        status["targets_project_script"] = project_script in text
    return status


def build_hermes_cron_status_payload(jobs_file: Path, scripts_dir: Path, expected_workdir: str) -> dict:
    jobs = _load_hermes_jobs(jobs_file)
    jobs_by_name = {str(job.get("name", "")): job for job in jobs}
    checks = []
    for name, expected in EXPECTED_HERMES_CRON_JOBS.items():
        job = jobs_by_name.get(name)
        wrapper = _check_wrapper(scripts_dir / expected["script"], expected["project_script"])
        errors: list[str] = []
        if job is None:
            errors.append("missing_job")
            actual = {}
        else:
            actual = {
                "job_id": job.get("id") or job.get("job_id"),
                "schedule": _cron_schedule_display(job),
                "script": job.get("script"),
                "no_agent": job.get("no_agent"),
                "deliver": job.get("deliver"),
                "workdir": job.get("workdir"),
                "enabled": job.get("enabled"),
                "state": job.get("state"),
                "last_status": job.get("last_status"),
                "last_delivery_error": job.get("last_delivery_error"),
            }
            if actual["schedule"] != expected["schedule"]:
                errors.append("wrong_schedule")
            if actual["script"] != expected["script"]:
                errors.append("wrong_script")
            if actual["no_agent"] is not True:
                errors.append("not_no_agent")
            if actual["deliver"] != "local":
                errors.append("wrong_deliver")
            if actual["workdir"] != expected_workdir:
                errors.append("wrong_workdir")
            if actual["enabled"] is not True:
                errors.append("not_enabled")
            if actual["last_delivery_error"]:
                errors.append("last_delivery_error")
        if not wrapper["exists"]:
            errors.append("missing_wrapper")
        if wrapper["exists"] and not wrapper["executable"]:
            errors.append("wrapper_not_executable")
        if wrapper["exists"] and not wrapper["targets_project_script"]:
            errors.append("wrapper_wrong_target")
        checks.append({
            "name": name,
            "expected": expected,
            "actual": actual,
            "wrapper": wrapper,
            "ok": not errors,
            "errors": errors,
        })
    ok_count = sum(1 for item in checks if item["ok"])
    return {
        "jobs_file": str(jobs_file),
        "jobs_file_exists": jobs_file.exists(),
        "scripts_dir": str(scripts_dir),
        "expected_workdir": expected_workdir,
        "summary": {
            "expected": len(EXPECTED_HERMES_CRON_JOBS),
            "configured": sum(1 for item in checks if item["actual"]),
            "ok": ok_count,
            "failed": len(checks) - ok_count,
        },
        "checks": checks,
    }


def cmd_hermes_cron_status(args: argparse.Namespace) -> int:
    payload = build_hermes_cron_status_payload(
        jobs_file=Path(args.jobs_file),
        scripts_dir=Path(args.scripts_dir),
        expected_workdir=args.workdir,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["summary"]["failed"] == 0 else 1


def cmd_eval_all(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    store = build_store(settings=settings, args=args)
    payload = EvalService(llm_client=build_llm_client(settings)).run_all(
        profile=profile,
        store=store,
        comment_csv=args.comment_file,
        campaign_notes_file=args.campaign_file,
        start_date=args.start_date,
    )
    if args.save:
        dump_json(settings.artifacts_dir / "evals" / f"eval-summary-{args.start_date}.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["summary"]["failed"] == 0 else 1


def render_telegram_preview(artifact_type: str, input_file: str) -> str:
    payload = json.loads(Path(input_file).read_text(encoding="utf-8"))
    formatter = TelegramFormatterService()
    if artifact_type == "plan":
        return formatter.format_weekly_plan(payload)
    if artifact_type == "caption":
        return formatter.format_caption_package(payload)
    if artifact_type == "report":
        return formatter.format_weekly_report(payload)
    if artifact_type == "triage":
        return formatter.format_community_triage(payload)
    if artifact_type == "approved_replies":
        return formatter.format_approved_triage_replies(payload)
    if artifact_type == "approval":
        return formatter.format_approval_queue(payload)
    if artifact_type == "approval_audit":
        return formatter.format_approval_audit(payload)
    if artifact_type == "metrics":
        return formatter.format_metrics_backlog(payload)
    if artifact_type == "operator":
        return formatter.format_operator_digest(payload)
    if artifact_type == "research":
        return formatter.format_research_brief(payload)
    raise ValueError(f"Unsupported artifact type: {artifact_type}")


def cmd_preview_telegram(args: argparse.Namespace) -> int:
    print(render_telegram_preview(args.artifact_type, args.input_file))
    return 0


def cmd_send_telegram_preview(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    message = render_telegram_preview(args.artifact_type, args.input_file)
    result = TelegramClient(settings).send_message(message, chat_id=args.chat_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "plan-week":
        return cmd_plan_week(args)
    if args.command == "research-brief":
        return cmd_research_brief(args)
    if args.command == "deliver-research-brief":
        return cmd_deliver_research_brief(args)
    if args.command == "run-daily":
        return cmd_run_daily(args)
    if args.command == "deliver-daily-packet":
        return cmd_deliver_daily_packet(args)
    if args.command == "triage-community":
        return cmd_triage_community(args)
    if args.command == "deliver-triage-community":
        return cmd_deliver_triage_community(args)
    if args.command == "deliver-approved-triage-replies":
        return cmd_deliver_approved_triage_replies(args)
    if args.command == "list-triage-items":
        return cmd_list_triage_items(args)
    if args.command == "list-calendar-items":
        return cmd_list_calendar_items(args)
    if args.command == "deliver-approval-queue":
        return cmd_deliver_approval_queue(args)
    if args.command == "approval-audit":
        return cmd_approval_audit(args)
    if args.command == "deliver-approval-audit":
        return cmd_deliver_approval_audit(args)
    if args.command == "deliver-metrics-backlog":
        return cmd_deliver_metrics_backlog(args)
    if args.command == "deliver-operator-digest":
        return cmd_deliver_operator_digest(args)
    if args.command == "resolve-triage-item":
        return cmd_resolve_triage_item(args)
    if args.command == "reopen-triage-item":
        return cmd_reopen_triage_item(args)
    if args.command == "approve-triage-reply":
        return cmd_approve_triage_reply(args)
    if args.command == "reject-triage-reply":
        return cmd_reject_triage_reply(args)
    if args.command == "mark-triage-reply-sent":
        return cmd_mark_triage_reply_sent(args)
    if args.command == "write-caption":
        return cmd_write_caption(args)
    if args.command == "approve-caption":
        return cmd_approve_caption(args)
    if args.command == "reject-caption":
        return cmd_reject_caption(args)
    if args.command == "publish-post":
        return cmd_publish_post(args)
    if args.command == "process-pending":
        return cmd_process_pending(args)
    if args.command == "scheduled-publish":
        return cmd_scheduled_publish(args)
    if args.command == "record-post-metrics":
        return cmd_record_post_metrics(args)
    if args.command == "weekly-report":
        return cmd_weekly_report(args)
    if args.command == "deliver-weekly-report":
        return cmd_deliver_weekly_report(args)
    if args.command == "ops-status":
        return cmd_ops_status(args)
    if args.command == "hermes-cron-status":
        return cmd_hermes_cron_status(args)
    if args.command == "eval-all":
        return cmd_eval_all(args)
    if args.command == "preview-telegram":
        return cmd_preview_telegram(args)
    if args.command == "send-telegram-preview":
        return cmd_send_telegram_preview(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
