from __future__ import annotations

import argparse
import json

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.main import (
    DEFAULT_CALENDAR_FILE,
    DEFAULT_CAMPAIGN_FILE,
    DEFAULT_COMMENT_FILE,
    DEFAULT_HISTORY_FILE,
    DEFAULT_METRICS_FILE,
    ROOT_DIR,
    build_daily_artifacts,
    build_research_brief,
)
from fanpage_agent.tools.analytics.analytics import AnalyticsTool
from fanpage_agent.tools.content.verifier import VerifierTool
from fanpage_agent.tools.content.writer import WriterTool
from fanpage_agent.tools.publishing.daily_ops import DailyOpsTool
from fanpage_agent.tools.publishing.delivery import DeliveryTool
from fanpage_agent.tools.publishing.planner import PlannerTool
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.utils import dump_json


def add_store_backend_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store-backend", choices=["local", "google"])


def register_subcommand(subparsers) -> None:
    # ── plan-week ──
    p = subparsers.add_parser("plan-week")
    p.add_argument("--brand-file", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--save", action="store_true")
    p.add_argument("--write-calendar", action="store_true")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_plan_week)

    # ── research-brief ──
    p = subparsers.add_parser("research-brief")
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    p.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE))
    p.add_argument("--save", action="store_true")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument(
        "--scan-competitor",
        action="store_true",
        help="Enable competitor page analysis (reads competitor_page_names from brand profile)",
    )
    p.add_argument(
        "--competitor-pages",
        nargs="*",
        help="Override competitor page names (space-separated, overrides config)",
    )
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_research_brief)

    # ── deliver-research-brief ──
    p = subparsers.add_parser("deliver-research-brief")
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    p.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE))
    p.add_argument("--save", action="store_true")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--chat-id")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_deliver_research_brief)

    # ── run-daily ──
    p = subparsers.add_parser("run-daily")
    p.add_argument("--brand-file", required=True)
    p.add_argument("--run-date", required=True)
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    p.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE))
    p.add_argument("--write-calendar", action="store_true")
    p.add_argument("--save", action="store_true")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_run_daily)

    # ── weekly-report ──
    p = subparsers.add_parser("weekly-report")
    p.add_argument("--brand-file", required=True)
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--save", action="store_true")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_weekly_report)

    # ── deliver-weekly-report ──
    p = subparsers.add_parser("deliver-weekly-report")
    p.add_argument("--brand-file", required=True)
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--save", action="store_true")
    p.add_argument("--chat-id")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_deliver_weekly_report)

    # ── analytics-review ──
    p = subparsers.add_parser("analytics-review")
    p.add_argument("--brand-file", required=True)
    p.add_argument("--days", type=int, default=7)
    p.add_argument(
        "--record",
        action="store_true",
        help="Write metrics to store (without --record, preview only)",
    )
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--save", action="store_true")
    p.add_argument("--now")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_analytics_review)

    # ── deliver-analytics-review ──
    p = subparsers.add_parser("deliver-analytics-review")
    p.add_argument("--brand-file", required=True)
    p.add_argument("--days", type=int, default=7)
    p.add_argument(
        "--record",
        action="store_true",
        help="Write metrics to store (without --record, preview only)",
    )
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--save", action="store_true")
    p.add_argument("--chat-id")
    p.add_argument("--now")
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_deliver_analytics_review)

    # ── init-sheets ──
    p = subparsers.add_parser(
        "init-sheets", help="Create all standard tabs + headers in the Google Sheet"
    )
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_init_sheets)


# ── Command handlers (copied verbatim from fanpage_agent/main.py) ──


def cmd_plan_week(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    planner = PlannerTool(llm_client=build_llm_client(settings))
    verifier = VerifierTool()
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
    payload["delivery"] = DeliveryTool(settings).deliver_research_brief(
        payload, chat_id=args.chat_id
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_run_daily(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings)
    store = build_store(settings=settings, args=args)
    research_brief = ResearchTool().build_brief(
        store=store,
        comment_csv=args.comment_file,
        campaign_notes_file=args.campaign_file,
    )
    packet = DailyOpsTool(
        planner=PlannerTool(llm_client=llm_client),
        writer=WriterTool(llm_client=llm_client),
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


def cmd_init_sheets(args: argparse.Namespace) -> int:
    """Create all standard tabs + headers in the configured Google Sheet."""
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    if not hasattr(store, "initialize_standard_tabs"):
        print("init-sheets only works with --store-backend google")
        return 1
    status = store.initialize_standard_tabs()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print(f"\n✅ {len(status)} tabs ready.")
    return 0


def cmd_weekly_report(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    _ = load_brand_profile(args.brand_file)
    metrics = build_store(settings=settings, args=args).read_post_metrics()
    report = AnalyticsTool().build_weekly_report(metrics)
    payload = report.model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "reports" / "weekly-report.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_weekly_report(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    _ = load_brand_profile(args.brand_file)
    metrics = build_store(settings=settings, args=args).read_post_metrics()
    payload = AnalyticsTool().build_weekly_report(metrics).model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "reports" / "weekly-report.json", payload)
    payload["delivery"] = DeliveryTool(settings).deliver_weekly_report(
        payload, chat_id=args.chat_id
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_analytics_review(args: argparse.Namespace) -> int:
    from fanpage_agent.tools.analytics.analytics_reviewer import AnalyticsReviewer

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
    from fanpage_agent.tools.analytics.analytics_reviewer import AnalyticsReviewer

    settings = Settings.from_env(root_dir=ROOT_DIR)
    _ = load_brand_profile(args.brand_file)
    store = build_store(settings=settings, args=args)
    fb_client = FacebookClient(settings)
    reviewer = AnalyticsReviewer(settings, fb_client=fb_client)
    payload = reviewer.run_review(store=store, days=args.days, record=args.record)
    if args.save:
        dump_json(settings.artifacts_dir / "reports" / "analytics-review.json", payload)
    payload["delivery"] = DeliveryTool(settings).deliver_analytics_review(
        payload, chat_id=args.chat_id
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0
