"""Runtime subcommands — the multi-agent daemon/tick lane and ops utilities.

These were the 12 positional "actions" parsed inline by
``fanpage_agent.main.cli()``. They are now ordinary subcommands on the
unified parser tree so ``python -m fanpage_agent.main tick`` and
``fanpage-agent tick`` behave identically.

For backward compatibility every runtime subcommand accepts the same flag
set the old single parser did (each action used to tolerate all flags).
Handlers import fanpage_agent.main lazily to avoid import cycles.
"""

from __future__ import annotations

import argparse
import json

RUNTIME_ACTIONS = [
    "tick", "status", "daemon", "backup", "restore", "list-backups",
    "check-db", "harness-status", "roadmap-status", "research-standalone",
    "page-status", "competitor-learn",
]


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    handlers = {
        "tick": cmd_tick,
        "status": cmd_status,
        "daemon": cmd_daemon,
        "backup": cmd_backup,
        "restore": cmd_restore,
        "list-backups": cmd_list_backups,
        "check-db": cmd_check_db,
        "harness-status": cmd_harness_status,
        "roadmap-status": cmd_roadmap_status,
        "research-standalone": cmd_research_standalone,
        "page-status": cmd_page_status,
        "competitor-learn": cmd_competitor_learn,
    }
    for action in RUNTIME_ACTIONS:
        p = subparsers.add_parser(action)
        _add_runtime_args(p)
        p.set_defaults(_handler=handlers[action])


def _add_runtime_args(parser: argparse.ArgumentParser) -> None:
    from fanpage_agent.main import (
        DEFAULT_CALENDAR_FILE,
        DEFAULT_CAMPAIGN_FILE,
        DEFAULT_COMMENT_FILE,
        DEFAULT_HISTORY_FILE,
        DEFAULT_METRICS_FILE,
    )

    parser.add_argument("--data-dir", default="data/agent",
                        help="agent data directory")
    parser.add_argument("--brand-id", default="skincare_genz",
                        help="Brand identifier")
    parser.add_argument("--interval", type=int, default=7200,
                        help="Daemon interval (seconds, default 7200=2h)")
    parser.add_argument("--backup-idx", type=int, default=1,
                        help="Backup index for restore (1=most recent)")
    parser.add_argument("--keep", type=int, default=7,
                        help="Number of backup copies to keep (default: 7)")
    parser.add_argument("--limit", type=int, default=20,
                        help="Number of recent rows for status views")
    parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE),
                        help="post history CSV for research-standalone")
    parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE),
                        help="post metrics CSV for research-standalone")
    parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE),
                        help="comment inbox CSV for research-standalone")
    parser.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE),
                        help="campaign notes JSON for research-standalone")
    parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE),
                        help="calendar CSV for research-standalone")
    parser.add_argument("--output-dir", default="data/research_packets",
                        help="directory to write ResearchPacket JSON")
    parser.add_argument("--job-id",
                        help="optional stable job id for standalone research")
    parser.add_argument("--page-id",
                        help="page id whose profile should guide research/strategy")
    parser.add_argument("--source-registry-file",
                        help="JSON registry of trusted research sources")
    parser.add_argument("--fetch-source-documents", action="store_true",
                        help="fetch registry URLs with Scrapling and store extracted text")
    parser.add_argument("--source-cache-dir", default="data/research_source_cache",
                        help="cache directory for fetched source documents")
    parser.add_argument("--discover-sources", action="store_true",
                        help="discover new web source candidates from page topics")
    parser.add_argument("--max-discovered-sources", type=int, default=5,
                        help="maximum dynamic source candidates to include")
    parser.add_argument("--discover-product-topics", action="store_true",
                        help="derive topic candidates from page product/customer context")
    parser.add_argument("--max-product-topics", type=int, default=8,
                        help="maximum product-aware topic candidates to include")
    parser.add_argument("--no-external-trends", action="store_true",
                        help="skip external trend fetch for deterministic/offline runs")
    parser.add_argument("--competitor-names", nargs="*",
                        help="competitor names to scan (default: from DB tracked list)")
    parser.add_argument("--auto-discover", action="store_true",
                        help="run auto-discovery: scan candidates + promote")
    parser.add_argument("--show-summary", action="store_true",
                        help="show learning summary (no scan)")
    parser.add_argument("--promote-min-score", type=float, default=3.0,
                        help="minimum candidate score to auto-promote (default: 3.0)")
    parser.add_argument("--no-save", action="store_true",
                        help="dry run: don't save to DB")


# ── Handlers (delegate to fanpage_agent.main; lazy imports break cycles) ──


def cmd_tick(args: argparse.Namespace) -> int:
    from fanpage_agent.main import run_tick

    result = run_tick(data_dir=args.data_dir, brand_id=args.brand_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from fanpage_agent.main import run_status

    result = run_status(data_dir=args.data_dir, brand_id=args.brand_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    from fanpage_agent.main import run_daemon

    run_daemon(
        data_dir=args.data_dir,
        brand_id=args.brand_id,
        interval=args.interval,
        keep=args.keep,
    )
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    from fanpage_agent.main import _run_backup

    _run_backup(data_dir=args.data_dir, keep=args.keep)
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    from fanpage_agent.main import _run_restore

    _run_restore(data_dir=args.data_dir, backup_idx=args.backup_idx)
    return 0


def cmd_list_backups(args: argparse.Namespace) -> int:
    from fanpage_agent.main import _run_list_backups

    _run_list_backups(data_dir=args.data_dir)
    return 0


def cmd_check_db(args: argparse.Namespace) -> int:
    from fanpage_agent.main import _run_check_db

    _run_check_db(data_dir=args.data_dir)
    return 0


def cmd_harness_status(args: argparse.Namespace) -> int:
    from fanpage_agent.main import _run_harness_status

    _run_harness_status(data_dir=args.data_dir, limit=args.limit)
    return 0


def cmd_roadmap_status(args: argparse.Namespace) -> int:
    from fanpage_agent.main import _run_roadmap_status

    _run_roadmap_status()
    return 0


def cmd_research_standalone(args: argparse.Namespace) -> int:
    from fanpage_agent.main import _run_research_standalone

    _run_research_standalone(
        history_file=args.history_file,
        metrics_file=args.metrics_file,
        comment_file=args.comment_file,
        campaign_file=args.campaign_file,
        calendar_file=args.calendar_file,
        output_dir=args.output_dir,
        job_id=args.job_id,
        page_id=args.page_id,
        source_registry_file=args.source_registry_file,
        fetch_source_documents=args.fetch_source_documents,
        source_cache_dir=args.source_cache_dir,
        discover_sources=args.discover_sources,
        max_discovered_sources=args.max_discovered_sources,
        discover_product_topics=args.discover_product_topics,
        max_product_topics=args.max_product_topics,
        fetch_external_trends=not args.no_external_trends,
    )
    return 0


def cmd_page_status(args: argparse.Namespace) -> int:
    from fanpage_agent.main import _run_page_status

    _run_page_status(
        output_dir=args.output_dir,
        page_id=args.page_id,
        limit=args.limit,
    )
    return 0


def cmd_competitor_learn(args: argparse.Namespace) -> int:
    from fanpage_agent.main import _run_competitor_learn

    _run_competitor_learn(
        competitor_names=args.competitor_names,
        auto_discover=args.auto_discover,
        show_summary=args.show_summary,
        promote_min_score=args.promote_min_score,
        no_save=args.no_save,
        data_dir=args.data_dir,
    )
    return 0
