from __future__ import annotations

import argparse
import json

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
    DEFAULT_TRIAGE_FILE,
    ROOT_DIR,
    add_store_backend_arg,
    build_daily_artifacts,
    build_triage_store_payload,
)
from fanpage_agent.tools.content.writer import WriterTool
from fanpage_agent.tools.publishing.community_triage import CommunityTriageTool
from fanpage_agent.tools.publishing.daily_ops import DailyOpsTool
from fanpage_agent.tools.publishing.delivery import DeliveryTool
from fanpage_agent.tools.publishing.planner import PlannerTool
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.utils import dump_json


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
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
    daily_delivery_parser.set_defaults(_handler=cmd_deliver_daily_packet)

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
    triage_delivery_parser.set_defaults(_handler=cmd_deliver_triage_community)

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
    approved_replies_parser.set_defaults(_handler=cmd_deliver_approved_triage_replies)

    dashboard_delivery_parser = subparsers.add_parser("deliver-dashboard")
    dashboard_delivery_parser.add_argument(
        "--brand-file", default=str(ROOT_DIR / "data" / "brand_profile.json")
    )
    dashboard_delivery_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    dashboard_delivery_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    dashboard_delivery_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    dashboard_delivery_parser.add_argument("--days", type=int, default=7)
    dashboard_delivery_parser.add_argument("--chat-id")
    add_store_backend_arg(dashboard_delivery_parser)
    dashboard_delivery_parser.set_defaults(_handler=cmd_deliver_dashboard)


def cmd_deliver_daily_packet(args: argparse.Namespace) -> int:
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
    packet["delivery"] = DeliveryTool(settings).deliver_daily_packet(packet, chat_id=args.chat_id)
    print(json.dumps(packet, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_triage_community(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    if args.from_store:
        payload = build_triage_store_payload(args)
    else:
        profile = load_brand_profile(args.brand_file)
        batch = CommunityTriageTool().triage_from_csv(
            profile=profile, comment_csv=args.comment_file
        )
        payload = batch.model_dump(mode="json")
        if args.write_store:
            payload["store"] = {
                "persisted": build_store(settings=settings, args=args).upsert_triage_items(
                    profile.brand_id, batch.items
                )
            }
    if args.save:
        dump_json(settings.artifacts_dir / "community" / "community-triage.json", payload)
    payload["delivery"] = DeliveryTool(settings).deliver_community_triage(
        payload, chat_id=args.chat_id
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_approved_triage_replies(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    payload = build_triage_store_payload(args)
    if args.save:
        dump_json(settings.artifacts_dir / "community" / "approved-triage-replies.json", payload)
    payload["delivery"] = DeliveryTool(settings).deliver_approved_triage_replies(
        payload, chat_id=args.chat_id
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_dashboard(args: argparse.Namespace) -> int:
    from fanpage_agent.tools.analytics.analytics_dashboard import AnalyticsDashboardTool

    settings = Settings.from_env(root_dir=ROOT_DIR)
    metrics = build_store(settings=settings, args=args).read_post_metrics()
    svc = AnalyticsDashboardTool(settings.artifacts_dir)
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
    payload["delivery"] = DeliveryTool(settings).deliver_analytics_review(
        payload, chat_id=args.chat_id
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0
