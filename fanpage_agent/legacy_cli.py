from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, cast

from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.adapters.page_registry import PageRegistry
from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.adapters.telegram_client import TelegramClient
from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.config import Settings
from fanpage_agent.core.types import ContentPackage, ContentVariant
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.memory.performance import PerformanceMemory
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
from fanpage_agent.services.auto_content import AutoContentOrchestrator
from fanpage_agent.services.hashtag import HashtagService
from fanpage_agent.services.metrics_auto_fetch import MetricsAutoFetchService
from fanpage_agent.services.scheduled_publish import ScheduledPublishService
from fanpage_agent.services.research_packet import build_research_packet, packet_to_brief_payload, save_research_packet
from fanpage_agent.services.variant_scorer import VariantScorer
from fanpage_agent.services.verifier import VerifierService
from fanpage_agent.services.writer import WriterService
from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer
from fanpage_agent.scraping.web_search import WebSearchClient
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


def with_default_store_backend(args: argparse.Namespace, backend: str = "local") -> argparse.Namespace:
    if getattr(args, "store_backend", None) is not None:
        return args
    store_options = vars(args).copy()
    store_options["store_backend"] = backend
    return argparse.Namespace(**store_options)


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

    # ── search-trends: web search + scrape ────────────────────
    search_trends_parser = subparsers.add_parser("search-trends")
    search_trends_parser.add_argument("queries", nargs="+", help="Search queries")
    search_trends_parser.add_argument("--max-per-query", type=int, default=3, help="URLs per query")
    search_trends_parser.add_argument("--max-articles", type=int, default=10, help="Total max items")
    search_trends_parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout")

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
    daily_parser.add_argument("--source-registry-file")
    daily_parser.add_argument("--fetch-source-documents", action="store_true")
    daily_parser.add_argument("--source-cache-dir", default="data/research_source_cache")
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
    daily_delivery_parser.add_argument("--source-registry-file")
    daily_delivery_parser.add_argument("--fetch-source-documents", action="store_true")
    daily_delivery_parser.add_argument("--source-cache-dir", default="data/research_source_cache")
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
    approval_queue_parser.add_argument("--score-variants", action="store_true")
    approval_queue_parser.add_argument("--memory-db", default=str(ROOT_DIR / "data" / "agent" / "memory.db"))
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
    publish_parser.add_argument(
        "--allow-unapproved",
        action="store_true",
        help="Override safety guard and record a publish for an item that is not approved.",
    )
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
    scheduled_parser.add_argument("--hashtag-file")
    scheduled_parser.add_argument("--reference-date")
    scheduled_parser.add_argument("--brand-file", default=str(ROOT_DIR / "data" / "sample" / "brand_profile.json"))

    # ── generate-image: generate an image from a visual brief ──
    img_parser = subparsers.add_parser("generate-image")
    img_parser.add_argument("prompt", nargs="?", help="Visual brief text (reads from stdin if omitted)")
    img_parser.add_argument("--output", help="Output file path (auto-generates if omitted)")

    # ── list-calendar: browse content calendar items ──────────
    cal_list = subparsers.add_parser("list-calendar")
    cal_list.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    cal_list.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    cal_list.add_argument("--brand-id", help="Filter by brand_id")
    cal_list.add_argument("--status", help="Filter by status (planned/approved/published)")
    cal_list.add_argument("--approval-status", help="Filter by approval_status (pending/approved/rejected)")
    cal_list.add_argument("--date", help="Filter by exact date (YYYY-MM-DD)")
    cal_list.add_argument("--limit", type=int, default=20, help="Max items to show")
    cal_list.add_argument("--json", action="store_true", help="Output raw JSON")

    # ── approve-calendar-item: approve a calendar item ───────
    cal_approve = subparsers.add_parser("approve-calendar-item")
    cal_approve.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    cal_approve.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    cal_approve.add_argument("--calendar-id", required=True)
    cal_approve.add_argument("--final-caption-ref", help="Path to final caption JSON")
    cal_approve.add_argument("--approved-by", default="admin", help="Who approved")

    # ── reject-calendar-item: reject a calendar item ─────────
    cal_reject = subparsers.add_parser("reject-calendar-item")
    cal_reject.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    cal_reject.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    cal_reject.add_argument("--calendar-id", required=True)
    cal_reject.add_argument("--reason", default="Needs revision", help="Rejection reason")

    # ── check-calendar-gaps: find scheduling gaps ────────────
    cal_gaps = subparsers.add_parser("check-calendar-gaps")
    cal_gaps.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    cal_gaps.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    cal_gaps.add_argument("--brand-id", help="Filter by brand_id")
    cal_gaps.add_argument("--start-date", help="Start date (YYYY-MM-DD, default: today)")
    cal_gaps.add_argument("--end-date", help="End date (YYYY-MM-DD, default: today+14)")
    cal_gaps.add_argument("--max-gap-days", type=int, default=3, help="Alert on gaps longer than N days")
    cal_gaps.add_argument("--json", action="store_true", help="Output raw JSON")

    # ── fill-calendar-gaps: auto-detect + fill gaps ────────────
    fill_gaps = subparsers.add_parser("fill-calendar-gaps")
    fill_gaps.add_argument("--brand-file", required=True)
    fill_gaps.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    fill_gaps.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    fill_gaps.add_argument("--start-date", help="Start date (YYYY-MM-DD, default: today)")
    fill_gaps.add_argument("--lookahead-days", type=int, default=3, help="How many days forward to scan")
    fill_gaps.add_argument("--max-items", type=int, default=3, help="Max items to fill per run")
    fill_gaps.add_argument("--json", action="store_true", help="Output raw JSON")

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

    analytics_parser = subparsers.add_parser("analytics-review")
    analytics_parser.add_argument("--brand-file", required=True)
    analytics_parser.add_argument("--days", type=int, default=7)
    analytics_parser.add_argument("--record", action="store_true", help="Write metrics to store (without --record, preview only)")
    analytics_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    analytics_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    analytics_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    analytics_parser.add_argument("--save", action="store_true")
    analytics_parser.add_argument("--now")
    add_store_backend_arg(analytics_parser)

    analytics_delivery_parser = subparsers.add_parser("deliver-analytics-review")
    analytics_delivery_parser.add_argument("--brand-file", required=True)
    analytics_delivery_parser.add_argument("--days", type=int, default=7)
    analytics_delivery_parser.add_argument("--record", action="store_true", help="Write metrics to store (without --record, preview only)")
    analytics_delivery_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    analytics_delivery_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    analytics_delivery_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    analytics_delivery_parser.add_argument("--save", action="store_true")
    analytics_delivery_parser.add_argument("--chat-id")
    analytics_delivery_parser.add_argument("--now")
    add_store_backend_arg(analytics_delivery_parser)

    BRAND_FILE_DEFAULT: str = str(ROOT_DIR / "data" / "brand_profile.json")
    dashboard_parser = subparsers.add_parser("generate-dashboard")
    dashboard_parser.add_argument("--brand-file", default=BRAND_FILE_DEFAULT)
    dashboard_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    dashboard_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    dashboard_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    dashboard_parser.add_argument("--days", type=int, default=7)
    dashboard_parser.add_argument("--save", action="store_true", help="Save dashboard HTML to artifacts")
    add_store_backend_arg(dashboard_parser)

    dashboard_delivery_parser = subparsers.add_parser("deliver-dashboard")
    dashboard_delivery_parser.add_argument("--brand-file", default=BRAND_FILE_DEFAULT)
    dashboard_delivery_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    dashboard_delivery_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    dashboard_delivery_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    dashboard_delivery_parser.add_argument("--days", type=int, default=7)
    dashboard_delivery_parser.add_argument("--chat-id")
    add_store_backend_arg(dashboard_delivery_parser)

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

    # ── research-trends: scrape web + analyze trends ──────────
    research_trends_parser = subparsers.add_parser("research-trends")
    research_trends_parser.add_argument("--timeout", type=int, default=30, help="Timeout per request (sec)")
    research_trends_parser.add_argument("--tldr", action="store_true", help="Only print summary (no full report)")
    research_trends_parser.add_argument("--save", action="store_true", help="Save report to JSON")

    # ── generate-hashtags: LLM-powered hashtag generation ────
    hashtag_parser = subparsers.add_parser("generate-hashtags")
    hashtag_parser.add_argument("--brand-file", required=True)
    hashtag_parser.add_argument("--topic", required=True)
    hashtag_parser.add_argument("--pillar", required=True)
    hashtag_parser.add_argument("--objective", default="engagement")
    hashtag_parser.add_argument("--angle", default="")
    hashtag_parser.add_argument("--brand-id", default="", help="Override brand_id if brand file has multiple")
    hashtag_parser.add_argument("--no-llm", action="store_true", help="Use rule-based fallback only")
    hashtag_parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted text")

    # ── auto-fetch-metrics: fetch missing FB metrics ────────
    metrics_fetch_parser = subparsers.add_parser("auto-fetch-metrics")
    metrics_fetch_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    metrics_fetch_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    metrics_fetch_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    metrics_fetch_parser.add_argument("--days-back", type=int, default=30, help="Process items within this many days")
    metrics_fetch_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    add_store_backend_arg(metrics_fetch_parser)

    # ── fetch-fb-comments: pull real comments from FB API ─────
    fb_comment_parser = subparsers.add_parser("fetch-fb-comments")
    fb_comment_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    fb_comment_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    fb_comment_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    fb_comment_parser.add_argument("--post-limit", type=int, default=10, help="Max recent posts to scan")
    fb_comment_parser.add_argument("--comment-limit", type=int, default=50, help="Max comments per post")
    fb_comment_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # ── agent commands ──────────────────────────────────
    tick_parser = subparsers.add_parser("agent-tick", help="Run one autonomous agent cycle")
    tick_parser.add_argument("--config", help="Path to agent config JSON")
    tick_parser.add_argument("--max-actions", type=int, default=5, help="Max actions per tick")

    daemon_parser = subparsers.add_parser("agent-daemon", help="Run agent in daemon mode (infinite loop)")
    daemon_parser.add_argument("--config", help="Path to agent config JSON")
    daemon_parser.add_argument("--interval", type=int, default=7200, help="Tick interval in seconds")

    # ── auto-content-cycle: autonomous content agent loop ──────
    auto_parser = subparsers.add_parser("auto-content-cycle")
    auto_parser.add_argument("--brand-file", help="Path to brand profile JSON (cần cho draft)")
    auto_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    auto_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    auto_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    auto_parser.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE))
    auto_parser.add_argument("--draft", action="store_true", help="Sinh draft caption cho top gaps")
    auto_parser.add_argument("--max-gaps", type=int, default=10, help="Số gap tối đa phân tích")
    auto_parser.add_argument("--save", action="store_true", help="Lưu report ra artifacts")
    add_store_backend_arg(auto_parser)

    return parser


def _build_research_service(timeout: int = 15) -> ResearchService:
    """Build ResearchService với TrendScraper + WebSearchClient tích hợp."""
    web_search = WebSearchClient()
    scraper = TrendScraper(timeout=timeout, web_search=web_search)
    return ResearchService(trend_scraper=scraper)


def build_research_brief(args: argparse.Namespace):
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=with_default_store_backend(args))
    return _build_research_service().build_brief(
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
    items = build_store(settings=settings, args=with_default_store_backend(args)).list_triage_items(
        status=getattr(args, "status", None),
        priority=getattr(args, "priority", None),
        assigned_to=getattr(args, "assigned_to", None),
        limit=getattr(args, "limit", None),
    )
    return {
        "items": items,
        "summary": summarize_triage_items(items),
    }


def _content_package_from_caption_item(item: dict) -> ContentPackage | None:
    caption_ref = str(item.get("draft_caption_ref", "") or "")
    if not caption_ref:
        return None
    caption_path = Path(caption_ref)
    if not caption_path.is_absolute():
        caption_path = ROOT_DIR / caption_path
    if not caption_path.exists():
        return None

    raw = json.loads(caption_path.read_text(encoding="utf-8"))
    variants = []
    for index, raw_variant in enumerate(raw.get("variants", []), start=1):
        label = str(raw_variant.get("label") or raw_variant.get("variant_id") or index)
        variants.append(
            ContentVariant(
                variant_id=label,
                topic=str(raw.get("topic") or item.get("topic", "")),
                pillar=str(item.get("pillar", "")),
                caption=str(raw_variant.get("caption", "")),
                hook=str(raw_variant.get("hook", "")),
                cta=str(raw_variant.get("cta", "")),
                format=str(item.get("format", "") or "post_short"),
                tone_tags=list(raw_variant.get("tone_tags", []) or []),
                visual_brief=raw_variant.get("visual_brief"),
            )
        )
    return ContentPackage(
        package_id=str(item.get("calendar_id") or caption_path.stem),
        brand_id=str(item.get("brand_id") or ""),
        scheduled_date=str(item.get("date") or ""),
        variants=variants,
    )


def enrich_items_with_variant_scores(items: list[dict], memory_db: str | Path | None) -> dict:
    if not memory_db:
        return {"scored_items": 0, "skipped_items": len(items)}

    scorer = VariantScorer(PerformanceMemory(db_path=Path(memory_db)))
    scored = 0
    skipped = 0
    for item in items:
        package = _content_package_from_caption_item(item)
        if package is None or not package.variants:
            skipped += 1
            continue
        breakdowns = scorer.score_package(package)
        item["variant_scores"] = [
            {
                "variant_id": breakdown.variant_id,
                "score": breakdown.score,
                "matched_patterns": breakdown.matched_patterns,
            }
            for breakdown in breakdowns
        ]
        if package.winning_variant:
            item["recommended_variant"] = {
                "variant_id": package.winning_variant.variant_id,
                "score": package.winning_variant.score,
                "caption_preview": package.winning_variant.caption[:160],
            }
        scored += 1
    return {"scored_items": scored, "skipped_items": skipped}


def build_calendar_store_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    items = build_store(settings=settings, args=args).list_calendar_items(
        status=getattr(args, "status", None),
        approval_status=getattr(args, "approval_status", None),
        date=getattr(args, "date", None),
        metrics_pending=getattr(args, "metrics_pending", False),
        limit=getattr(args, "limit", None),
    )
    payload = {
        "items": items,
        "summary": summarize_calendar_items(items),
    }
    if getattr(args, "score_variants", False):
        payload["variant_scoring"] = enrich_items_with_variant_scores(
            items,
            getattr(args, "memory_db", None),
        )
    return payload


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


def _publish_blockers_for_operator(items: list[dict]) -> list[dict]:
    blockers: list[dict] = []
    for item in items:
        status = item.get("status", "") or "unknown"
        if status in {"published", "posted"}:
            continue
        approval_status = item.get("approval_status", "") or "unknown"
        final_caption_ref = item.get("final_caption_ref")
        reason_codes: list[str] = []
        next_step = "ready_for_scheduled_publish"
        if approval_status != "approved":
            reason_codes.append("approval_status_not_approved")
            next_step = "approve-caption"
        elif not final_caption_ref:
            reason_codes.append("missing_final_caption_ref")
            next_step = "approve-caption"
        if reason_codes:
            blocked = dict(item)
            blocked["reason_codes"] = reason_codes
            blocked["next_step"] = next_step
            blockers.append(blocked)
    return blockers


def build_operator_digest_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    limit = getattr(args, "limit", None)
    publish_candidates = store.list_calendar_items(
        status=getattr(args, "calendar_status", None),
        approval_status=None,
        date=getattr(args, "date", None),
        metrics_pending=False,
        limit=limit,
    )
    approval_items = [
        item for item in publish_candidates
        if (item.get("approval_status") or "pending") == getattr(args, "approval_status", "pending")
    ]
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
    publish_blockers = _publish_blockers_for_operator(publish_candidates)
    return {
        "summary": {
            "pending_captions": len(approval_items),
            "approved_replies": len(approved_replies),
            "metrics_backlog": len(metrics_backlog),
            "publish_blockers": len(publish_blockers),
        },
        "approval_queue": {
            "items": approval_items[:limit] if limit is not None else approval_items,
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
        "publish_blockers": {
            "items": publish_blockers[:limit] if limit is not None else publish_blockers,
            "summary": summarize_calendar_items(publish_blockers),
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


def cmd_search_trends(args: argparse.Namespace) -> int:
    """CLI command: search web → scrape URLs → print TrendItems as JSON."""
    web_search = WebSearchClient()
    scraper = TrendScraper(timeout=args.timeout, web_search=web_search)
    results = scraper.search_trends(
        queries=args.queries,
        max_results_per_query=args.max_per_query,
        max_articles=args.max_articles,
    )
    payload = [r.model_dump(mode="json") for r in results]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n📦 Tổng cộng: {len(results)} TrendItem", file=sys.stderr)
    return 0


def cmd_auto_content_cycle(args: argparse.Namespace) -> int:
    """CLI command: autonomous content agent loop.

    Pipeline:
      1. Research — web search + scrape → trends
      2. Gap analysis — trends vs published history → gaps
      3. Draft — sinh caption cho top gaps (nếu --draft + --brand-file)
      4. Report — in JSON + optional Telegram format
    """
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)

    research_service = _build_research_service()

    brand_profile = None
    if args.brand_file:
        try:
            brand_profile = load_brand_profile(args.brand_file)
        except Exception as exc:
            print(f"⚠️  Không load được brand profile: {exc}", file=sys.stderr)

    writer_service = WriterService(llm_client=build_llm_client(settings)) if brand_profile and args.draft else None
    orchestrator = AutoContentOrchestrator(
        research_service=research_service,
        writer_service=writer_service,
    )

    report = orchestrator.run_cycle(
        store=store,
        brand_profile=brand_profile,
        comment_csv=getattr(args, "comment_file", None),
        campaign_file=getattr(args, "campaign_file", None),
        draft_content=bool(args.draft and brand_profile),
        max_gaps=args.max_gaps,
    )

    payload = report.to_dict()

    if args.save:
        out_dir = settings.artifacts_dir / "auto_content"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"auto-content-cycle-{report.run_date}.json"
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"💾 Report saved: {out_path}", file=sys.stderr)

    # Print JSON to stdout
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    # Print Telegram summary to stderr
    print(file=sys.stderr)
    print(report.format_telegram(), file=sys.stderr)

    return 0


def cmd_run_daily(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings)
    store = build_store(settings=settings, args=args)
    page_context = PageRegistry(settings).page_context(None)
    research_packet = build_research_packet(
        history_file=args.history_file,
        metrics_file=args.metrics_file,
        comment_file=args.comment_file,
        campaign_file=args.campaign_file,
        calendar_file=args.calendar_file,
        job_id=f"daily-{args.run_date}",
        fetch_external_trends=False,
        page_id=str(page_context.get("page_id", "")),
        page_context=page_context,
        source_registry_file=args.source_registry_file,
        fetch_source_documents=args.fetch_source_documents,
        source_cache_dir=args.source_cache_dir,
    )
    research_brief = research_packet.brief
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
    packet["research_packet"] = packet_to_brief_payload(research_packet)
    if args.save:
        packet["artifacts"] = build_daily_artifacts(settings, packet, args.run_date)
        packet["artifacts"]["research_packet"] = str(
            save_research_packet(research_packet, settings.artifacts_dir / "research_packets")
        )
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
    page_context = PageRegistry(settings).page_context(None)
    research_packet = build_research_packet(
        history_file=args.history_file,
        metrics_file=args.metrics_file,
        comment_file=args.comment_file,
        campaign_file=args.campaign_file,
        calendar_file=args.calendar_file,
        job_id=f"daily-{args.run_date}",
        fetch_external_trends=False,
        page_id=str(page_context.get("page_id", "")),
        page_context=page_context,
        source_registry_file=args.source_registry_file,
        fetch_source_documents=args.fetch_source_documents,
        source_cache_dir=args.source_cache_dir,
    )
    research_brief = research_packet.brief
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
    packet["research_packet"] = packet_to_brief_payload(research_packet)
    if args.save:
        packet["artifacts"] = build_daily_artifacts(settings, packet, args.run_date)
        packet["artifacts"]["research_packet"] = str(
            save_research_packet(research_packet, settings.artifacts_dir / "research_packets")
        )
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
        store_args = with_default_store_backend(args)
        payload["store"] = {
            "persisted": build_store(settings=settings, args=store_args).upsert_triage_items(profile.brand_id, batch.items)
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
    args = with_default_store_backend(args)
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
    row = build_store(settings=settings, args=with_default_store_backend(args)).resolve_triage_item(
        triage_id=args.triage_id,
        resolved_at=args.resolved_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_reopen_triage_item(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=with_default_store_backend(args)).reopen_triage_item(
        triage_id=args.triage_id,
        reopened_at=args.reopened_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_approve_triage_reply(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=with_default_store_backend(args)).approve_triage_reply(
        triage_id=args.triage_id,
        approved_by=args.approved_by,
        approved_at=args.approved_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_reject_triage_reply(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=with_default_store_backend(args)).reject_triage_reply(
        triage_id=args.triage_id,
        reason=args.reason,
        rejected_at=args.rejected_at,
        assigned_to=args.assigned_to,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_mark_triage_reply_sent(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=with_default_store_backend(args)).mark_triage_reply_sent(
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


def _find_calendar_item_for_publish(store: object, calendar_id: str) -> dict[str, Any] | None:
    list_items = getattr(store, "list_calendar_items", None)
    if not callable(list_items):
        return None
    try:
        rows = cast(list[dict[str, Any]], list_items(limit=None))
    except TypeError:
        rows = cast(list[dict[str, Any]], list_items())
    for row in rows:
        if str(row.get("calendar_id", "")) == calendar_id:
            return row
    return None


def _build_publish_block_payload(calendar_id: str, row: dict[str, object] | None) -> dict[str, object]:
    approval_status = str((row or {}).get("approval_status", "missing") or "missing")
    status = str((row or {}).get("status", "missing") or "missing")
    final_caption_ref = str((row or {}).get("final_caption_ref", "") or "")
    reason_codes: list[str] = []
    if row is None:
        reason_codes.append("calendar_item_not_found")
    if approval_status != "approved":
        reason_codes.append("approval_status_not_approved")
    if status in {"published", "posted"}:
        reason_codes.append("already_published")
    if not final_caption_ref:
        reason_codes.append("missing_final_caption_ref")
    return {
        "blocked": True,
        "action": "publish-post",
        "calendar_id": calendar_id,
        "reason_codes": reason_codes,
        "approval_status": approval_status,
        "status": status,
        "next_step": "Run approve-caption first, then retry publish-post. Use --allow-unapproved only for manual recovery.",
    }


def cmd_publish_post(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    row = _find_calendar_item_for_publish(store, args.calendar_id)
    if not args.allow_unapproved and (
        row is None
        or row.get("approval_status") != "approved"
        or not row.get("final_caption_ref")
        or row.get("status") in {"published", "posted"}
    ):
        print(json.dumps(_build_publish_block_payload(args.calendar_id, row), ensure_ascii=False, indent=2))
        return 2

    published = store.publish_calendar_item(
        calendar_id=args.calendar_id,
        published_at=args.published_at,
        permalink=args.permalink,
        reach=args.reach,
        engagement_rate=args.engagement_rate,
    )
    print(json.dumps(published, ensure_ascii=False, indent=2))
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
        hashtag_csv=settings.artifacts_dir / "_local_store" / "hashtag_performance.csv",
    )

    # Build Facebook client if credentials are available
    fb_client: FacebookClient | None = None
    if settings.fb_page_id and settings.fb_page_token:
        fb_client = FacebookClient(settings)

    # Build image service (generates images from visual_brief)
    from fanpage_agent.services.image_gen import build_image_service
    image_service = build_image_service(settings)

    service = ScheduledPublishService(
        store=store,
        brand_id=profile.brand_id,
        verifier=VerifierService(),
        brand_profile=profile,
        fb_client=fb_client,
        image_service=image_service,
    )
    result = service.publish_due(reference_date=args.reference_date)
    payload = result.to_dict()
    payload["fb_published"] = fb_client is not None
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_generate_image(args: argparse.Namespace) -> int:
    """Generate an image from a visual brief prompt."""
    settings = Settings.from_env(root_dir=ROOT_DIR)
    from fanpage_agent.services.image_gen import build_image_service

    prompt = args.prompt
    if not prompt:
        prompt = sys.stdin.read().strip()
    if not prompt:
        print("ERROR: No prompt provided. Pass as argument or pipe via stdin.", file=sys.stderr)
        return 1

    svc = build_image_service(settings)
    output = args.output or None
    result_path = svc.generate(prompt, output_dir=output)
    print(json.dumps({"image_path": result_path}, ensure_ascii=False, indent=2))
    return 0


def cmd_list_calendar(args: argparse.Namespace) -> int:
    """List content calendar items with filters."""
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = LocalSheetStore(
        calendar_csv=args.calendar_file,
        history_csv=args.history_file,
    )
    items = store.list_calendar_items(
        brand_id=args.brand_id,
        status=args.status,
        approval_status=args.approval_status,
        date=args.date,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    if not items:
        print("No items found.")
        return 0

    # Table-like output for Telegram/terminal
    print(f"📋 Calendar items ({len(items)}):\n")
    for item in items:
        cid = item.get("calendar_id", "?")
        b = item.get("brand_id", "?")
        d = item.get("date", "?")
        t = item.get("topic", "?")[:50]
        s = item.get("status", "?")
        a = f"{item.get('approval_status', '?')[:8]}"
        p = "📸" if item.get("visual_brief") else ""
        print(f"  [{s}/{a}] {d} | {b} | {cid}\n    {t} {p}")
    return 0


def cmd_approve_calendar_item(args: argparse.Namespace) -> int:
    """Approve a content calendar item."""
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = LocalSheetStore(
        calendar_csv=args.calendar_file,
        history_csv=args.history_file,
    )
    from datetime import datetime as _dt
    now = _dt.now(timezone.utc).isoformat()
    result = store.approve_calendar_item(
        calendar_id=args.calendar_id,
        approved_by=args.approved_by,
        final_caption_ref=args.final_caption_ref or "",
        approved_at=now,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_reject_calendar_item(args: argparse.Namespace) -> int:
    """Reject a content calendar item."""
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = LocalSheetStore(
        calendar_csv=args.calendar_file,
        history_csv=args.history_file,
    )
    from datetime import datetime as _dt
    now = _dt.now(timezone.utc).isoformat()
    result = store.reject_calendar_item(
        calendar_id=args.calendar_id,
        reason=args.reason,
        rejected_at=now,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_check_calendar_gaps(args: argparse.Namespace) -> int:
    """Find gaps in the content calendar."""
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = LocalSheetStore(
        calendar_csv=args.calendar_file,
        history_csv=args.history_file,
    )
    gaps = store.check_calendar_gaps(
        brand_id=args.brand_id,
        start_date=args.start_date,
        end_date=args.end_date,
        max_gap_days=args.max_gap_days,
    )
    if args.json:
        print(json.dumps(gaps, ensure_ascii=False, indent=2))
        return 0
    if not gaps:
        print("✅ No significant gaps found.")
    else:
        for g in gaps:
            print(f"  ⚠️  Gap: {g['start_date']} → {g['end_date']} ({g['gap_days']} days)")
    return 0


def cmd_fill_calendar_gaps(args: argparse.Namespace) -> int:
    """Auto-detect and fill gaps in the content calendar."""
    import json as _json
    from fanpage_agent.services.calendar_gap_service import CalendarGapService
    from fanpage_agent.services.planner import PlannerService
    from fanpage_agent.services.writer import WriterService
    from fanpage_agent.adapters.sheet_store import LocalSheetStore

    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings)
    store = LocalSheetStore(
        calendar_csv=args.calendar_file,
        history_csv=args.history_file,
    )
    gap_svc = CalendarGapService(
        planner=PlannerService(llm_client=llm_client),
        writer=WriterService(llm_client=llm_client),
        artifacts_dir=ROOT_DIR / "artifacts" / "captions",
    )
    result = gap_svc.fill_gaps(
        profile=profile,
        store=store,
        start_date=args.start_date,
        lookahead_days=args.lookahead_days,
        max_items=args.max_items,
    )
    if args.json:
        print(_json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if result.filled_count > 0:
        print(f"✅ Filled {result.filled_count} gap(s):")
        for item in result.filled:
            print(f"  📝 {item['date']} — {item['pillar']}: {item['topic']}")
    else:
        print("ℹ️  No gaps filled.")

    if result.skipped_count > 0:
        print(f"⏭️  Skipped {result.skipped_count}:")
        for item in result.skipped:
            print(f"  {item['date']} — {item['reason']}")

    if result.error_count > 0:
        print(f"❌ {result.error_count} error(s):")
        for item in result.errors:
            print(f"  {item.get('date', item.get('calendar_id', '?'))} — {item['reason']}")

    return 0 if result.error_count == 0 else 1


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


def cmd_analytics_review(args: argparse.Namespace) -> int:
    from fanpage_agent.services.analytics_reviewer import AnalyticsReviewer

    settings = Settings.from_env(root_dir=ROOT_DIR)
    _ = load_brand_profile(args.brand_file)
    store = build_store(settings=settings, args=args)
    fb_client = FacebookClient(settings)
    reviewer = AnalyticsReviewer(settings, fb_client=fb_client)
    payload = reviewer.run_review(store=store, days=args.days, record=args.record)
    if args.save:
        dump_json(settings.artifacts_dir / "reports" / "analytics-review.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_analytics_review(args: argparse.Namespace) -> int:
    from fanpage_agent.services.analytics_reviewer import AnalyticsReviewer

    settings = Settings.from_env(root_dir=ROOT_DIR)
    _ = load_brand_profile(args.brand_file)
    store = build_store(settings=settings, args=args)
    fb_client = FacebookClient(settings)
    reviewer = AnalyticsReviewer(settings, fb_client=fb_client)
    payload = reviewer.run_review(store=store, days=args.days, record=args.record)
    if args.save:
        dump_json(settings.artifacts_dir / "reports" / "analytics-review.json", payload)
    payload["delivery"] = DeliveryService(settings).deliver_analytics_review(payload, chat_id=args.chat_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_generate_dashboard(args: argparse.Namespace) -> int:
    from fanpage_agent.services.analytics_dashboard import AnalyticsDashboardService

    settings = Settings.from_env(root_dir=ROOT_DIR)
    metrics = build_store(settings=settings, args=args).read_post_metrics()
    svc = AnalyticsDashboardService(settings.artifacts_dir)
    result = svc.generate(metrics, days=args.days)
    if args.save:
        pass  # already saved in generate()
    print(f"📊 Dashboard saved: {result['path']}")
    print(f"   Period: {args.days}d | Posts: {result['total_posts']} | Reach: {result['total_reach']} | Eng: {result['total_engagements']}")
    return 0


def cmd_deliver_dashboard(args: argparse.Namespace) -> int:
    from fanpage_agent.services.analytics_dashboard import AnalyticsDashboardService

    settings = Settings.from_env(root_dir=ROOT_DIR)
    metrics = build_store(settings=settings, args=args).read_post_metrics()
    svc = AnalyticsDashboardService(settings.artifacts_dir)
    result = svc.generate(metrics, days=args.days)

    # Send HTML file via delivery service
    payload = {
        "type": "dashboard",
        "path": result["path"],
        "generated_at": result["generated_at"],
        "total_posts": result["total_posts"],
        "total_reach": result["total_reach"],
        "total_engagements": result["total_engagements"],
    }
    payload["delivery"] = DeliveryService(settings).deliver_analytics_review(
        payload, chat_id=args.chat_id
    )
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


def cmd_research_trends(args: argparse.Namespace) -> int:
    """Scrape web trends and analyze for skincare/healthcare topics."""
    scraper = TrendScraper(timeout=args.timeout)
    trends = scraper.fetch_all()

    if not trends:
        print("⚠ Khong lay duoc trend tu nguon nao.")
        return 1

    analyzer = TrendAnalyzer(trends)
    report = analyzer.generate_report()

    if args.tldr:
        print(f"📊 {report['total_trends']} trends tu {len(report['sources'])} nguon\n")
        print("Top keywords:")
        for kw in report["top_keywords"][:10]:
            print(f"  {kw['word']} ({kw['count']})")
        print()
        for label, items in list(report["clusters"].items())[:5]:
            print(f"[{label}] ({len(items)} items)")
        print()
        print("Top relevant cho skincare/healthcare:")
        for item in report["top_relevant"][:5]:
            print(f"  {item['score']:.0%} - {item['title'][:60]}")
    else:
        # Full report
        print(f"=== 🌐 Research Trends ===")
        print(f"Tong: {report['total_trends']} trends tu {len(report['sources'])} nguon\n")

        print("--- Top Keywords ---")
        for kw in report["top_keywords"][:20]:
            print(f"  {kw['word']:20s} ✕ {kw['count']}")

        print("\n--- Top Phrases ---")
        for ph in report["top_phrases"][:15]:
            print(f"  {ph['phrase']:30s} ✕ {ph['count']}")

        print("\n--- Clusters ---")
        for label, items in list(report["clusters"].items())[:10]:
            print(f"  [{label}] ({len(items)} items)")
            for t in items[:3]:
                print(f"    - {t[:60]}")
            if len(items) > 3:
                print(f"    ... +{len(items)-3} more")

        print("\n--- Top Relevant (skincare/healthcare) ---")
        for item in report["top_relevant"][:10]:
            print(f"  {item['score']:.0%} | {item['title'][:55]}")
            print(f"     [{item['source']}]")

    if args.save:
        path = ROOT_DIR / "data" / f"research-trends-{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        dump_json(path, report)
        print(f"\n💾 Saved to {path}")

    return 0


def cmd_generate_hashtags(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings) if settings.llm_provider != "mock-local" or not args.no_llm else None
    service = HashtagService(llm_client=llm_client, settings=settings)

    result = service.generate(
        topic=args.topic,
        pillar=args.pillar,
        objective=args.objective,
        angle=args.angle,
        brand_id=profile.brand_id,
        use_llm=not args.no_llm,
    )

    # Convert to serializable dict
    output = {
        "content_topic": result.content_topic,
        "pillar": result.pillar,
        "objective": result.objective,
        "suggestions": [
            {"tag": s.tag, "tier": s.tier, "relevance_score": s.relevance_score, "reason": s.reason}
            for s in result.suggestions
        ],
        "recommended": result.recommended,
    }

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        formatter = TelegramFormatterService()
        print(formatter.format_hashtag_set(output))

    return 0


def cmd_auto_fetch_metrics(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    service = MetricsAutoFetchService(settings=settings)
    result = service.auto_fetch(store=store, days_back=args.days_back)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        formatter = TelegramFormatterService()
        print(formatter.format_metrics_auto_fetch(result))

    return 0


def cmd_fetch_fb_comments(args: argparse.Namespace) -> int:
    """Fetch real comments from FB API and merge into comment_inbox.csv.

    Get recent published posts → fetch comments → dedup by FB comment id → save.
    """
    import csv
    from fanpage_agent.adapters.facebook_client import FacebookClient

    settings = Settings.from_env(root_dir=ROOT_DIR)
    comment_path = Path(args.comment_file)

    # 1. Fetch recent posts from FB
    fb = FacebookClient(settings)
    print(f"📡 Fetching up to {args.post_limit} recent posts from FB...")
    try:
        posts = fb.get_page_posts(limit=args.post_limit)
    except Exception as e:
        print(f"❌ Failed to fetch posts: {e}")
        return 1

    if not posts:
        print("⚠️  No recent posts found.")
        return 0

    # 2. Fetch comments for each post
    all_comments: list[dict] = []
    for post in posts:
        post_id = post.get("id", "")
        if not post_id:
            continue
        print(f"  📝 Post {post_id}: fetching comments...")
        try:
            comments = fb.get_comments(post_id, limit=args.comment_limit)
        except Exception as e:
            print(f"  ⚠️  Error fetching comments for {post_id}: {e}")
            continue
        for c in comments:
            c["post_id"] = post_id
            all_comments.append(c)

    print(f"✅ Fetched {len(all_comments)} comments across {len(posts)} posts.")

    if not all_comments:
        return 0

    # 3. Read existing comments
    existing_ids: set[str] = set()
    existing_rows: list[dict] = []
    if comment_path.exists():
        with comment_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or ["id", "post_id", "created_at", "source", "message"]
            for row in reader:
                existing_rows.append(row)
                if row.get("id"):
                    existing_ids.add(row["id"])

    # 4. Merge new comments (dedup by FB comment id)
    new_rows: list[dict] = []
    for c in all_comments:
        cid = c.get("id", "")
        if cid and cid in existing_ids:
            continue
        new_rows.append({
            "id": c.get("id", ""),
            "post_id": c.get("post_id", ""),
            "created_at": c.get("created_time", ""),
            "source": "facebook_comment",
            "message": c.get("message", ""),
        })
        if cid:
            existing_ids.add(cid)

    if not new_rows:
        print("ℹ️  No new comments to add.")
        return 0

    # 5. Write back
    all_rows = existing_rows + new_rows
    fieldnames = ["id", "post_id", "created_at", "source", "message"]
    with comment_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"✅ Added {len(new_rows)} new comments. Total: {len(all_rows)}.")
    if args.json:
        print(json.dumps({"added": len(new_rows), "total": len(all_rows)}, ensure_ascii=False))

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
    if args.command == "search-trends":
        return cmd_search_trends(args)
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
    if args.command == "generate-image":
        return cmd_generate_image(args)
    if args.command == "list-calendar":
        return cmd_list_calendar(args)
    if args.command == "approve-calendar-item":
        return cmd_approve_calendar_item(args)
    if args.command == "reject-calendar-item":
        return cmd_reject_calendar_item(args)
    if args.command == "check-calendar-gaps":
        return cmd_check_calendar_gaps(args)
    if args.command == "fill-calendar-gaps":
        return cmd_fill_calendar_gaps(args)
    if args.command == "record-post-metrics":
        return cmd_record_post_metrics(args)
    if args.command == "weekly-report":
        return cmd_weekly_report(args)
    if args.command == "deliver-weekly-report":
        return cmd_deliver_weekly_report(args)
    if args.command == "analytics-review":
        return cmd_analytics_review(args)
    if args.command == "deliver-analytics-review":
        return cmd_deliver_analytics_review(args)
    if args.command == "generate-dashboard":
        return cmd_generate_dashboard(args)
    if args.command == "deliver-dashboard":
        return cmd_deliver_dashboard(args)
    if args.command == "ops-status":
        return cmd_ops_status(args)
    if args.command == "research-trends":
        return cmd_research_trends(args)
    if args.command == "auto-content-cycle":
        return cmd_auto_content_cycle(args)
    if args.command == "generate-hashtags":
        return cmd_generate_hashtags(args)
    if args.command == "auto-fetch-metrics":
        return cmd_auto_fetch_metrics(args)
    if args.command == "hermes-cron-status":
        return cmd_hermes_cron_status(args)
    if args.command == "eval-all":
        return cmd_eval_all(args)
    if args.command == "preview-telegram":
        return cmd_preview_telegram(args)
    if args.command == "send-telegram-preview":
        return cmd_send_telegram_preview(args)
    if args.command == "fetch-fb-comments":
        return cmd_fetch_fb_comments(args)

    # ── agent commands ──────────────────────────────────
    if args.command == "agent-tick":
        from fanpage_agent.agent.config import AgentConfig
        from fanpage_agent.agent.scheduler import tick

        cfg = AgentConfig(max_actions_per_tick=args.max_actions)
        if args.config:
            cfg = __import__("fanpage_agent.agent.scheduler", fromlist=["load_config"]).load_config(args.config)
        import json as _json
        result = tick(cfg)
        print(_json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "agent-daemon":
        from fanpage_agent.agent.config import AgentConfig
        from fanpage_agent.agent.scheduler import daemon

        cfg = AgentConfig(tick_interval_seconds=args.interval)
        if args.config:
            cfg = __import__("fanpage_agent.agent.scheduler", fromlist=["load_config"]).load_config(args.config)
        daemon(cfg)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
