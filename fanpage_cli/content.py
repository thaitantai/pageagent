from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.services.auto_approval import (
    AutoApprovalConfig,
    AutoApprovalEngine,
)
from fanpage_agent.services.calendar_gap_service import CalendarGapService
from fanpage_agent.services.planner import PlannerService
from fanpage_agent.services.scheduled_publish import ScheduledPublishService
from fanpage_agent.services.verifier import VerifierService
from fanpage_agent.services.writer import WriterService
from fanpage_agent.utils import dump_json
from fanpage_agent.main import (
    ROOT_DIR,
    DEFAULT_CALENDAR_FILE,
    DEFAULT_HISTORY_FILE,
    DEFAULT_METRICS_FILE,
)


def add_store_backend_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store-backend", choices=["local", "google"])


def register_subcommand(subparsers) -> None:
    # ── write-caption ──
    p = subparsers.add_parser("write-caption")
    p.add_argument("--brand-file", required=True)
    p.add_argument("--topic", required=True)
    p.add_argument("--pillar", required=True)
    p.add_argument("--objective", required=True)
    p.add_argument("--format", default="post_short")
    p.add_argument("--save", action="store_true")
    p.set_defaults(_handler=cmd_write_caption)

    # ── approve-caption ──
    p = subparsers.add_parser("approve-caption")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--calendar-id", required=True)
    p.add_argument("--approved-by", required=True)
    p.add_argument("--caption-file", required=True)
    p.add_argument("--approved-at", required=True)
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_approve_caption)

    # ── reject-caption ──
    p = subparsers.add_parser("reject-caption")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--calendar-id", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--rejected-at", required=True)
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_reject_caption)

    # ── publish-post ──
    p = subparsers.add_parser("publish-post")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--calendar-id", required=True)
    p.add_argument("--published-at", required=True)
    p.add_argument("--permalink", required=True)
    p.add_argument("--reach", type=int, default=0)
    p.add_argument("--engagement-rate", type=float, default=0.0)
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_publish_post)

    # ── process-pending ──
    p = subparsers.add_parser("process-pending")
    p.add_argument("--brand-file", required=True)
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--no-verify", action="store_true")
    p.add_argument("--skip-ban", action="store_true")
    p.add_argument("--skip-duplicate", action="store_true")
    p.set_defaults(_handler=cmd_process_pending)

    # ── scheduled-publish ──
    p = subparsers.add_parser("scheduled-publish")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--hashtag-file")
    p.add_argument("--reference-date")
    p.add_argument("--brand-file", default=str(ROOT_DIR / "data" / "sample" / "brand_profile.json"))
    p.set_defaults(_handler=cmd_scheduled_publish)

    # ── generate-image ──
    p = subparsers.add_parser("generate-image")
    p.add_argument("prompt", nargs="?", help="Visual brief text (reads from stdin if omitted)")
    p.add_argument("--output", help="Output file path (auto-generates if omitted)")
    p.set_defaults(_handler=cmd_generate_image)

    # ── list-calendar ──
    p = subparsers.add_parser("list-calendar")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--brand-id", help="Filter by brand_id")
    p.add_argument("--status", help="Filter by status (planned/approved/published)")
    p.add_argument("--approval-status", help="Filter by approval_status (pending/approved/rejected)")
    p.add_argument("--date", help="Filter by exact date (YYYY-MM-DD)")
    p.add_argument("--limit", type=int, default=20, help="Max items to show")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(_handler=cmd_list_calendar)

    # ── approve-calendar-item ──
    p = subparsers.add_parser("approve-calendar-item")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--calendar-id", required=True)
    p.add_argument("--final-caption-ref", help="Path to final caption JSON")
    p.add_argument("--approved-by", default="admin", help="Who approved")
    p.set_defaults(_handler=cmd_approve_calendar_item)

    # ── reject-calendar-item ──
    p = subparsers.add_parser("reject-calendar-item")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--calendar-id", required=True)
    p.add_argument("--reason", default="Needs revision", help="Rejection reason")
    p.set_defaults(_handler=cmd_reject_calendar_item)

    # ── check-calendar-gaps ──
    p = subparsers.add_parser("check-calendar-gaps")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--brand-id", help="Filter by brand_id")
    p.add_argument("--start-date", help="Start date (YYYY-MM-DD, default: today)")
    p.add_argument("--end-date", help="End date (YYYY-MM-DD, default: today+14)")
    p.add_argument("--max-gap-days", type=int, default=3, help="Alert on gaps longer than N days")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(_handler=cmd_check_calendar_gaps)

    # ── fill-calendar-gaps ──
    p = subparsers.add_parser("fill-calendar-gaps")
    p.add_argument("--brand-file", required=True)
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--start-date", help="Start date (YYYY-MM-DD, default: today)")
    p.add_argument("--lookahead-days", type=int, default=3, help="How many days forward to scan")
    p.add_argument("--max-items", type=int, default=3, help="Max items to fill per run")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(_handler=cmd_fill_calendar_gaps)

    # ── record-post-metrics ──
    p = subparsers.add_parser("record-post-metrics")
    p.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    p.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    p.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    p.add_argument("--calendar-id", required=True)
    p.add_argument("--reach", type=int, required=True)
    p.add_argument("--engagements", type=int, required=True)
    p.add_argument("--leads", type=int, required=True)
    p.add_argument("--recorded-at", required=True)
    add_store_backend_arg(p)
    p.set_defaults(_handler=cmd_record_post_metrics)


# ── Command handlers (copied verbatim from fanpage_agent/main.py) ──

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


def cmd_publish_post(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    row = build_store(settings=settings, args=args).publish_calendar_item(
        calendar_id=args.calendar_id,
        published_at=args.published_at,
        permalink=args.permalink,
        reach=args.reach,
        engagement_rate=args.engagement_rate,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
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
    print(f"\U0001f4cb Calendar items ({len(items)}):\n")
    for item in items:
        cid = item.get("calendar_id", "?")
        b = item.get("brand_id", "?")
        d = item.get("date", "?")
        t = item.get("topic", "?")[:50]
        s = item.get("status", "?")
        a = f"{item.get('approval_status', '?')[:8]}"
        p = "\U0001f4f8" if item.get("visual_brief") else ""
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
        print("\u2705 No significant gaps found.")
    else:
        for g in gaps:
            print(f"  \u26a0\ufe0f  Gap: {g['start_date']} \u2192 {g['end_date']} ({g['gap_days']} days)")
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
        print(f"\u2705 Filled {result.filled_count} gap(s):")
        for item in result.filled:
            print(f"  \U0001f4dd {item['date']} \u2014 {item['pillar']}: {item['topic']}")
    else:
        print("\u2139\ufe0f  No gaps filled.")

    if result.skipped_count > 0:
        print(f"\u23ed\ufe0f  Skipped {result.skipped_count}:")
        for item in result.skipped:
            print(f"  {item['date']} \u2014 {item['reason']}")

    if result.error_count > 0:
        print(f"\u274c {result.error_count} error(s):")
        for item in result.errors:
            print(f"  {item.get('date', item.get('calendar_id', '?'))} \u2014 {item['reason']}")

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
