"""Dispatcher for runtime-only CLI actions."""

from __future__ import annotations

import argparse
import json
import sys

from fanpage_agent.cli_commands.main import main as public_cli_main
from fanpage_agent.cli_common import (
    DEFAULT_CALENDAR_FILE,
    DEFAULT_CAMPAIGN_FILE,
    DEFAULT_COMMENT_FILE,
    DEFAULT_HISTORY_FILE,
    DEFAULT_METRICS_FILE,
)
from fanpage_agent.daemon_loop import run_daemon_loop
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
from fanpage_agent.runtime_pipeline import run_status, run_tick
from fanpage_agent.status_cli import _run_harness_status, _run_roadmap_status

RUNTIME_ACTIONS = {
    "tick",
    "status",
    "daemon",
    "backup",
    "restore",
    "list-backups",
    "check-db",
    "harness-status",
    "roadmap-status",
    "research-standalone",
    "page-status",
    "competitor-learn",
}


def _build_runtime_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fanpage Agent")
    parser.add_argument("action", choices=sorted(RUNTIME_ACTIONS), help="Action to perform")
    parser.add_argument("--data-dir", default="data/agent", help="Agent data directory")
    parser.add_argument("--brand-id", default="skincare_genz", help="Brand identifier")
    parser.add_argument(
        "--interval",
        type=int,
        default=7200,
        help="Daemon interval in seconds (default: 7200 = 2h)",
    )
    parser.add_argument(
        "--backup-idx",
        type=int,
        default=1,
        help="Backup index to restore (1 = most recent)",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="Number of backup copies to keep (default: 7)",
    )
    parser.add_argument("--limit", type=int, default=20, help="Number of recent rows for status views")
    parser.add_argument(
        "--history-file",
        default=str(DEFAULT_HISTORY_FILE),
        help="Post history CSV for research-standalone",
    )
    parser.add_argument(
        "--metrics-file",
        default=str(DEFAULT_METRICS_FILE),
        help="Post metrics CSV for research-standalone",
    )
    parser.add_argument(
        "--comment-file",
        default=str(DEFAULT_COMMENT_FILE),
        help="Comment inbox CSV for research-standalone",
    )
    parser.add_argument(
        "--campaign-file",
        default=str(DEFAULT_CAMPAIGN_FILE),
        help="Campaign notes JSON for research-standalone",
    )
    parser.add_argument(
        "--calendar-file",
        default=str(DEFAULT_CALENDAR_FILE),
        help="Content calendar CSV for research-standalone",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/research_packets",
        help="Output directory for research packet files",
    )
    parser.add_argument("--job-id", help="Optional job id for research packet")
    parser.add_argument("--page-id", help="Page id filter or packet page context")
    parser.add_argument(
        "--source-registry-file",
        default=None,
        help="Optional source registry JSON for research packet",
    )
    parser.add_argument(
        "--fetch-source-documents",
        action="store_true",
        help="Fetch and cache source documents for research packet",
    )
    parser.add_argument(
        "--source-cache-dir",
        default="data/research_source_cache",
        help="Cache directory for fetched source documents",
    )
    parser.add_argument(
        "--discover-sources",
        action="store_true",
        help="Discover new web source candidates for page topics",
    )
    parser.add_argument(
        "--max-discovered-sources",
        type=int,
        default=5,
        help="Maximum dynamic source candidates to include",
    )
    parser.add_argument(
        "--discover-product-topics",
        action="store_true",
        help="Derive topic candidates from page product/customer context",
    )
    parser.add_argument(
        "--max-product-topics",
        type=int,
        default=8,
        help="Maximum product-aware topic candidates to include",
    )
    parser.add_argument(
        "--no-external-trends",
        action="store_true",
        help="Skip external trend fetch for deterministic/offline runs",
    )
    parser.add_argument(
        "--competitor-names",
        nargs="*",
        help="Competitor names to scan (default: tracked list from DB)",
    )
    parser.add_argument(
        "--auto-discover",
        action="store_true",
        help="Run auto-discovery and promote candidates",
    )
    parser.add_argument("--show-summary", action="store_true", help="Show learning summary only")
    parser.add_argument(
        "--promote-min-score",
        type=float,
        default=3.0,
        help="Minimum candidate score to auto-promote (default: 3.0)",
    )
    parser.add_argument(
        "--roadmap-target",
        choices=["product", "research"],
        default="product",
        help="Roadmap target for roadmap-status",
    )
    parser.add_argument("--no-save", action="store_true", help="Dry run: do not save to DB")
    return parser


def _dispatch_runtime_action(args: argparse.Namespace) -> None:
    if args.action == "tick":
        print(json.dumps(run_tick(data_dir=args.data_dir, brand_id=args.brand_id), ensure_ascii=False, indent=2))
        return

    if args.action == "status":
        print(
            json.dumps(
                run_status(data_dir=args.data_dir, brand_id=args.brand_id),
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.action == "backup":
        _run_backup(data_dir=args.data_dir, keep=args.keep)
        return

    if args.action == "restore":
        _run_restore(data_dir=args.data_dir, backup_idx=args.backup_idx)
        return

    if args.action == "list-backups":
        _run_list_backups(data_dir=args.data_dir)
        return

    if args.action == "check-db":
        _run_check_db(data_dir=args.data_dir)
        return

    if args.action == "harness-status":
        _run_harness_status(data_dir=args.data_dir, limit=args.limit)
        return

    if args.action == "roadmap-status":
        _run_roadmap_status(roadmap_target=args.roadmap_target)
        return

    if args.action == "research-standalone":
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
        return

    if args.action == "page-status":
        _run_page_status(output_dir=args.output_dir, page_id=args.page_id, limit=args.limit)
        return

    if args.action == "competitor-learn":
        _run_competitor_learn(
            competitor_names=args.competitor_names,
            auto_discover=args.auto_discover,
            show_summary=args.show_summary,
            promote_min_score=args.promote_min_score,
            no_save=args.no_save,
            data_dir=args.data_dir,
        )
        return

    if args.action == "daemon":
        run_daemon_loop(
            data_dir=args.data_dir,
            brand_id=args.brand_id,
            interval=args.interval,
            keep=args.keep,
        )
        return

    raise ValueError(f"Unsupported runtime action: {args.action}")


def cli() -> None:
    """CLI entry point."""
    if len(sys.argv) > 1 and sys.argv[1] not in RUNTIME_ACTIONS:
        raise SystemExit(public_cli_main())

    parser = _build_runtime_parser()
    args = parser.parse_args()
    _dispatch_runtime_action(args)
