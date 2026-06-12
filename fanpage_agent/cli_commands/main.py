from __future__ import annotations

import argparse
from typing import Callable

from .parser import build_parser
from .research import cmd_research_brief, cmd_search_trends, cmd_research_trends, cmd_learn
from .content import cmd_write_caption, cmd_generate_hashtags
from .publishing import (
    cmd_plan_week,
    cmd_deliver_research_brief,
    cmd_auto_content_cycle,
    cmd_build_strategy,
    cmd_run_daily,
    cmd_deliver_daily_packet,
    cmd_publish_post,
    cmd_process_pending,
    cmd_scheduled_publish,
    cmd_generate_image,
    cmd_list_calendar,
    cmd_approve_calendar_item,
    cmd_reject_calendar_item,
    cmd_check_calendar_gaps,
    cmd_fill_calendar_gaps,
    cmd_record_post_metrics,
    cmd_weekly_report,
    cmd_deliver_weekly_report,
    # Phase 4: Content Queue
    cmd_queue_show,
    cmd_queue_enqueue,
    cmd_queue_approve,
    cmd_queue_reject,
    cmd_queue_publish,
    cmd_queue_stats,
)
from .triage import (
    cmd_triage_community,
    cmd_deliver_triage_community,
    cmd_deliver_approved_triage_replies,
    cmd_list_triage_items,
    cmd_list_calendar_items,
    cmd_deliver_approval_queue,
    cmd_approval_audit,
    cmd_deliver_approval_audit,
    cmd_deliver_metrics_backlog,
    cmd_deliver_operator_digest,
    cmd_resolve_triage_item,
    cmd_reopen_triage_item,
    cmd_approve_triage_reply,
    cmd_reject_triage_reply,
    cmd_mark_triage_reply_sent,
    cmd_approve_caption,
    cmd_reject_caption,
)
from .analytics import (
    cmd_analytics_review,
    cmd_deliver_analytics_review,
    cmd_generate_dashboard,
    cmd_deliver_dashboard,
    cmd_eval_all,
    cmd_auto_fetch_metrics,
    cmd_fetch_fb_comments,
    cmd_fetch_fb_data,
)
from .ops import cmd_ops_status, cmd_hermes_cron_status
from .preview import cmd_preview_telegram, cmd_send_telegram_preview


def cmd_agent_tick(args: argparse.Namespace) -> int:
    from fanpage_agent.agent.config import AgentConfig
    from fanpage_agent.agent.scheduler import tick

    cfg = AgentConfig(max_actions_per_tick=args.max_actions)
    if args.config:
        cfg = __import__("fanpage_agent.agent.scheduler", fromlist=["load_config"]).load_config(args.config)
    import json as _json
    result = tick(cfg)
    print(_json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_agent_daemon(args: argparse.Namespace) -> int:
    from fanpage_agent.agent.config import AgentConfig
    from fanpage_agent.agent.scheduler import daemon

    cfg = AgentConfig(tick_interval_seconds=args.interval)
    if args.config:
        cfg = __import__("fanpage_agent.agent.scheduler", fromlist=["load_config"]).load_config(args.config)
    daemon(cfg)
    return 0


# Single source of truth for subcommand dispatch. fanpage_cli grafts these
# handlers onto the same parser tree, so both entry points stay in lockstep.
HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "plan-week": cmd_plan_week,
    "research-brief": cmd_research_brief,
    "deliver-research-brief": cmd_deliver_research_brief,
    "search-trends": cmd_search_trends,
    "run-daily": cmd_run_daily,
    "deliver-daily-packet": cmd_deliver_daily_packet,
    "triage-community": cmd_triage_community,
    "deliver-triage-community": cmd_deliver_triage_community,
    "deliver-approved-triage-replies": cmd_deliver_approved_triage_replies,
    "list-triage-items": cmd_list_triage_items,
    "list-calendar-items": cmd_list_calendar_items,
    "deliver-approval-queue": cmd_deliver_approval_queue,
    "approval-audit": cmd_approval_audit,
    "deliver-approval-audit": cmd_deliver_approval_audit,
    "deliver-metrics-backlog": cmd_deliver_metrics_backlog,
    "deliver-operator-digest": cmd_deliver_operator_digest,
    "resolve-triage-item": cmd_resolve_triage_item,
    "reopen-triage-item": cmd_reopen_triage_item,
    "approve-triage-reply": cmd_approve_triage_reply,
    "reject-triage-reply": cmd_reject_triage_reply,
    "mark-triage-reply-sent": cmd_mark_triage_reply_sent,
    "write-caption": cmd_write_caption,
    "approve-caption": cmd_approve_caption,
    "reject-caption": cmd_reject_caption,
    "publish-post": cmd_publish_post,
    "process-pending": cmd_process_pending,
    "scheduled-publish": cmd_scheduled_publish,
    "generate-image": cmd_generate_image,
    "list-calendar": cmd_list_calendar,
    "approve-calendar-item": cmd_approve_calendar_item,
    "reject-calendar-item": cmd_reject_calendar_item,
    "check-calendar-gaps": cmd_check_calendar_gaps,
    "fill-calendar-gaps": cmd_fill_calendar_gaps,
    "record-post-metrics": cmd_record_post_metrics,
    "weekly-report": cmd_weekly_report,
    "deliver-weekly-report": cmd_deliver_weekly_report,
    "analytics-review": cmd_analytics_review,
    "deliver-analytics-review": cmd_deliver_analytics_review,
    "generate-dashboard": cmd_generate_dashboard,
    "deliver-dashboard": cmd_deliver_dashboard,
    "ops-status": cmd_ops_status,
    "research-trends": cmd_research_trends,
    "auto-content-cycle": cmd_auto_content_cycle,
    "generate-hashtags": cmd_generate_hashtags,
    "build-strategy": cmd_build_strategy,
    "auto-fetch-metrics": cmd_auto_fetch_metrics,
    "hermes-cron-status": cmd_hermes_cron_status,
    "eval-all": cmd_eval_all,
    "preview-telegram": cmd_preview_telegram,
    "send-telegram-preview": cmd_send_telegram_preview,
    "fetch-fb-comments": cmd_fetch_fb_comments,
    "fetch-fb-data": cmd_fetch_fb_data,
    "learn": cmd_learn,
    "queue-show": cmd_queue_show,
    "queue-enqueue": cmd_queue_enqueue,
    "queue-approve": cmd_queue_approve,
    "queue-reject": cmd_queue_reject,
    "queue-publish": cmd_queue_publish,
    "queue-stats": cmd_queue_stats,
    "agent-tick": cmd_agent_tick,
    "agent-daemon": cmd_agent_daemon,
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handler = HANDLERS.get(args.command)
    if handler is None:
        parser.error(f"Unknown command: {args.command}")
        return 2
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
