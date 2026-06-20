from __future__ import annotations

from .analytics import (
    cmd_analytics_review,
    cmd_auto_fetch_metrics,
    cmd_deliver_analytics_review,
    cmd_deliver_dashboard,
    cmd_eval_all,
    cmd_fetch_fb_comments,
    cmd_fetch_fb_data,
    cmd_generate_dashboard,
)
from .content import cmd_generate_hashtags, cmd_write_caption
from .ops import cmd_hermes_cron_status, cmd_ops_status
from .parser import build_parser
from .preview import cmd_preview_telegram, cmd_send_telegram_preview
from .publishing import (
    cmd_approve_calendar_item,
    cmd_auto_content_cycle,
    cmd_build_strategy,
    cmd_check_calendar_gaps,
    cmd_deliver_daily_packet,
    cmd_deliver_research_brief,
    cmd_deliver_weekly_report,
    cmd_fill_calendar_gaps,
    cmd_generate_image,
    cmd_list_calendar,
    cmd_plan_week,
    cmd_process_pending,
    cmd_publish_post,
    cmd_queue_approve,
    cmd_queue_enqueue,
    cmd_queue_publish,
    cmd_queue_reject,
    # Phase 4: Content Queue
    cmd_queue_show,
    cmd_queue_stats,
    cmd_record_post_metrics,
    cmd_reject_calendar_item,
    cmd_run_daily,
    cmd_scheduled_publish,
    cmd_weekly_report,
)
from .research import cmd_learn, cmd_research_brief, cmd_research_trends, cmd_search_trends
from .triage import (
    cmd_approval_audit,
    cmd_approve_caption,
    cmd_approve_triage_reply,
    cmd_deliver_approval_audit,
    cmd_deliver_approval_queue,
    cmd_deliver_approved_triage_replies,
    cmd_deliver_metrics_backlog,
    cmd_deliver_operator_digest,
    cmd_deliver_triage_community,
    cmd_list_calendar_items,
    cmd_list_triage_items,
    cmd_mark_triage_reply_sent,
    cmd_reject_caption,
    cmd_reject_triage_reply,
    cmd_reopen_triage_item,
    cmd_resolve_triage_item,
    cmd_triage_community,
)


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
    if args.command == "build-strategy":
        return cmd_build_strategy(args)
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
    if args.command == "fetch-fb-data":
        return cmd_fetch_fb_data(args)
    if args.command == "learn":
        return cmd_learn(args)

    # ── Content Queue commands (Phase 4) ──────────────────
    if args.command == "queue-show":
        return cmd_queue_show(args)
    if args.command == "queue-enqueue":
        return cmd_queue_enqueue(args)
    if args.command == "queue-approve":
        return cmd_queue_approve(args)
    if args.command == "queue-reject":
        return cmd_queue_reject(args)
    if args.command == "queue-publish":
        return cmd_queue_publish(args)
    if args.command == "queue-stats":
        return cmd_queue_stats(args)

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
