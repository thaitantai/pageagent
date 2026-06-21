"""Thin compatibility entrypoint for the runtime pipeline and CLI."""

from __future__ import annotations

from fanpage_agent.cli_commands import (
    build_approval_audit_payload,
    build_calendar_store_payload,
    build_daily_artifacts,
    build_operator_digest_payload,
    build_research_brief,
    build_triage_store_payload,
)
from fanpage_agent.cli_common import (
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
    ROOT_DIR,
    add_store_backend_arg,
)
from fanpage_agent.memory_cli import (
    _run_backup,
    _run_check_db,
    _run_list_backups,
    _run_restore,
)
from fanpage_agent.research_cli import (
    _run_competitor_learn,
    _run_page_status,
    _run_research_standalone,
)
from fanpage_agent.runtime_cli.dispatcher import cli
from fanpage_agent.runtime_pipeline import _load_pages, create_pipeline, run_status, run_tick
from fanpage_agent.status_cli import _run_harness_status, _run_roadmap_status

__all__ = [
    "DEFAULT_CALENDAR_FILE",
    "DEFAULT_CAMPAIGN_FILE",
    "DEFAULT_COMMENT_FILE",
    "DEFAULT_HERMES_CRON_JOBS_FILE",
    "DEFAULT_HERMES_SCRIPTS_DIR",
    "DEFAULT_HISTORY_FILE",
    "DEFAULT_METRICS_FILE",
    "DEFAULT_TRIAGE_FILE",
    "EXPECTED_HERMES_CRON_JOBS",
    "OPS_ARTIFACT_FRESHNESS_HOURS",
    "ROOT_DIR",
    "add_store_backend_arg",
    "build_approval_audit_payload",
    "build_calendar_store_payload",
    "build_daily_artifacts",
    "build_operator_digest_payload",
    "build_research_brief",
    "build_triage_store_payload",
    "_load_pages",
    "create_pipeline",
    "run_tick",
    "run_status",
    "_run_backup",
    "_run_restore",
    "_run_list_backups",
    "_run_check_db",
    "_run_harness_status",
    "_run_roadmap_status",
    "_run_research_standalone",
    "_run_page_status",
    "_run_competitor_learn",
    "cli",
]


if __name__ == "__main__":
    cli()
