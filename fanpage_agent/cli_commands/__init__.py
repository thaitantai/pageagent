"""cli_commands package — split from legacy_cli.py for maintainability.

Re-exports all functions and constants so that ``from fanpage_agent.legacy_cli import X``
continues to work when legacy_cli.py redirects here.
"""

# ── Strict critical exports (used by other modules) ──────────────────────
from .parser import (
    ROOT_DIR,
    DEFAULT_CALENDAR_FILE,
    DEFAULT_CAMPAIGN_FILE,
    DEFAULT_COMMENT_FILE,
    DEFAULT_HERMES_CRON_JOBS_FILE,
    DEFAULT_HERMES_SCRIPTS_DIR,
    DEFAULT_HISTORY_FILE,
    DEFAULT_METRICS_FILE,
    DEFAULT_TRIAGE_FILE,
    EXPECTED_HERMES_CRON_JOBS,
    OPS_ARTIFACT_FRESHNESS_HOURS,
    add_store_backend_arg,
    with_default_store_backend,
    build_parser,
)

from .research import (
    _build_research_service,
    build_research_brief,
    build_daily_artifacts,
    build_triage_store_payload,
    summarize_calendar_items,
    summarize_triage_items,
    cmd_research_brief,
    cmd_search_trends,
    cmd_research_trends,
)

from .content import (
    _content_package_from_caption_item,
    enrich_items_with_variant_scores,
    cmd_write_caption,
    cmd_generate_hashtags,
)

from .triage import (
    build_calendar_store_payload,
    build_approval_audit_payload,
    build_operator_digest_payload,
    _publish_blockers_for_operator,
    _find_calendar_item_for_publish,
    _build_publish_block_payload,
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

from .publishing import (
    cmd_plan_week,
    cmd_deliver_research_brief,
    cmd_auto_content_cycle,
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

from .ops import (
    _parse_timestamp,
    _parse_freshness_thresholds,
    _artifact_status,
    _latest_artifact,
    _runtime_check,
    build_runtime_config_status,
    build_ops_status_payload,
    cmd_ops_status,
    _cron_schedule_display,
    _load_hermes_jobs,
    _check_wrapper,
    build_hermes_cron_status_payload,
    cmd_hermes_cron_status,
)

from .preview import (
    render_telegram_preview,
    cmd_preview_telegram,
    cmd_send_telegram_preview,
)

from .main import main
