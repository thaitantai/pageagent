from __future__ import annotations

import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
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
    daily_parser.add_argument("--discover-sources", action="store_true")
    daily_parser.add_argument("--max-discovered-sources", type=int, default=5)
    daily_parser.add_argument("--discover-product-topics", action="store_true")
    daily_parser.add_argument("--max-product-topics", type=int, default=8)
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
    daily_delivery_parser.add_argument("--discover-sources", action="store_true")
    daily_delivery_parser.add_argument("--max-discovered-sources", type=int, default=5)
    daily_delivery_parser.add_argument("--discover-product-topics", action="store_true")
    daily_delivery_parser.add_argument("--max-product-topics", type=int, default=8)
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
    ops_status_parser.add_argument(
        "--fail-on-runtime",
        action="store_true",
        help="Return exit code 1 when runtime configuration checks fail.",
    )
    ops_status_parser.add_argument(
        "--include-cron",
        action="store_true",
        help="Include Hermes cron job/wrapper readiness checks in the payload.",
    )
    ops_status_parser.add_argument("--cron-jobs-file", default=str(DEFAULT_HERMES_CRON_JOBS_FILE))
    ops_status_parser.add_argument("--cron-scripts-dir", default=str(DEFAULT_HERMES_SCRIPTS_DIR))
    ops_status_parser.add_argument("--cron-workdir", default=str(ROOT_DIR))
    ops_status_parser.add_argument(
        "--fail-on-cron",
        action="store_true",
        help="Return exit code 1 when included Hermes cron checks fail.",
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

    # ── learn: self-learning cycle ─────────────────────────┬─
    learn_parser = subparsers.add_parser("learn", help="Run or inspect the self-learning cycle")
    learn_parser.add_argument("--optimize", action="store_true", help="Adjust scoring weights")
    learn_parser.add_argument("--calibrate", action="store_true", help="Calibrate confidence thresholds")
    learn_parser.add_argument("--decay", action="store_true", help="Apply time-decay to topic scores")
    learn_parser.add_argument("--all", action="store_true", help="Run optimize + calibrate + decay (default)")
    learn_parser.add_argument("--status", action="store_true", help="Show current weights + recent runs (no changes)")
    learn_parser.add_argument("--history", type=int, nargs="?", const=10, default=0,
                              help="Show last N learning runs")

    # ── fetch-fb-comments: pull real comments from FB API ─────
    fb_comment_parser = subparsers.add_parser("fetch-fb-comments")
    fb_comment_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    fb_comment_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    fb_comment_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    fb_comment_parser.add_argument("--post-limit", type=int, default=10, help="Max recent posts to scan")
    fb_comment_parser.add_argument("--comment-limit", type=int, default=50, help="Max comments per post")
    fb_comment_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # ── fetch-fb-data: pull posts + metrics + comments into store ──
    fb_data_parser = subparsers.add_parser("fetch-fb-data", help="Fetch posts, metrics, comments from FB API → store")
    fb_data_parser.add_argument("--post-limit", type=int, default=90, help="Max posts to fetch")
    fb_data_parser.add_argument("--comment-posts", type=int, default=20, help="How many recent posts to scan for comments")
    fb_data_parser.add_argument("--comment-limit", type=int, default=25, help="Max comments per post")
    fb_data_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    fb_data_parser.add_argument("--skip-comments", action="store_true", help="Skip comment fetching")
    fb_data_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    add_store_backend_arg(fb_data_parser)

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
