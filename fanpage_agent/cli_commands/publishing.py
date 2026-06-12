"""Publishing CLI commands — refactored from legacy_cli.py.

Each command recreates the original CLI interface using the new tool-based API.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.adapters.page_registry import PageRegistry
from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.analytics.analytics import AnalyticsTool
from fanpage_agent.tools.content.image_gen import build_image_service
from fanpage_agent.tools.publishing.delivery import DeliveryTool
from fanpage_agent.tools.publishing.planner import PlannerTool
from fanpage_agent.tools.content.verifier import VerifierTool
from fanpage_agent.tools.content.writer import WriterTool
from fanpage_agent.tools.content.auto_approval import AutoApprovalConfig, AutoApprovalEngine
from fanpage_agent.tools.content.auto_content import AutoContentOrchestrator
from fanpage_agent.tools.publishing.calendar_gap_service import CalendarGapTool
from fanpage_agent.tools.publishing.daily_ops import DailyOpsTool
from fanpage_agent.tools.publishing.scheduled_publish import ScheduledPublishTool
from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.scraping.web_search import WebSearchClient
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.tools.research.research_packet import (
    build_research_packet,
    packet_to_brief_payload,
    save_research_packet,
)
from fanpage_agent.utils import dump_json
from fanpage_agent.models import ResearchBrief

from .parser import ROOT_DIR, add_store_backend_arg, with_default_store_backend


# ── helpers ─────────────────────────────────────────────────────────────


def _find_calendar_item_for_publish(store, calendar_id: str) -> dict | None:
    """Find a calendar item by ID."""
    items = store.list_calendar_items()
    if isinstance(items, list):
        for item in items:
            if item.get("calendar_id") == calendar_id:
                return item
        return None
    if isinstance(items, dict):
        return items
    return None


def _build_publish_block_payload(calendar_id: str, row: dict | None) -> dict:
    approval_status = str((row or {}).get("approval_status", "missing") or "missing")
    status = str((row or {}).get("status", "missing") or "missing")
    final_caption_ref = str((row or {}).get("final_caption_ref", "") or "")
    reason_codes: list[str] = []
    if row is None:
        reason_codes.append("calendar_item_not_found")
    if approval_status != "approved":
        reason_codes.append("approval_status_not_approved")
    if status in {"published", "posted"}:
        reason_codes.append("already_published")
    if not final_caption_ref:
        reason_codes.append("missing_final_caption_ref")
    return {
        "blocked": True,
        "action": "publish-post",
        "calendar_id": calendar_id,
        "reason_codes": reason_codes,
        "approval_status": approval_status,
        "status": status,
        "next_step": "Run approve-caption first, then retry publish-post. Use --allow-unapproved only for manual recovery.",
    }


# ── research helpers ────────────────────────────────────────────────────


def _build_research_tool(timeout: int = 15) -> ResearchTool:
    web_search = WebSearchClient()
    scraper = TrendScraper(timeout=timeout, web_search=web_search)
    return ResearchTool(trend_scraper=scraper)


# ── commands ────────────────────────────────────────────────────────────


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


def cmd_deliver_research_brief(args: argparse.Namespace) -> int:
    from .research import build_research_brief

    settings = Settings.from_env(root_dir=ROOT_DIR)
    brief = build_research_brief(args)
    payload = brief.model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "research" / "research-brief.json", payload)
    payload["delivery"] = DeliveryTool(settings).deliver_research_brief(
        payload, chat_id=getattr(args, "chat_id", None)
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_auto_content_cycle(args: argparse.Namespace) -> int:
    from fanpage_agent.tools.content.auto_content import AutoContentOrchestrator
    from fanpage_agent.tools.content.writer import WriterTool as WriterService

    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)

    research_tool = _build_research_tool()

    brand_profile = None
    if args.brand_file:
        try:
            brand_profile = load_brand_profile(args.brand_file)
        except Exception as exc:
            print(f"⚠️  Không load được brand profile: {exc}", file=sys.stderr)

    writer_service = (
        WriterService(llm_client=build_llm_client(settings))
        if brand_profile and args.draft
        else None
    )
    orchestrator = AutoContentOrchestrator(
        research_service=None,  # wrapped below via store
        writer_service=writer_service,
    )

    report = orchestrator.run_cycle(
        store=store,
        brand_profile=brand_profile,
        comment_csv=getattr(args, "comment_file", None),
        campaign_file=getattr(args, "campaign_file", None),
        draft_content=bool(args.draft and brand_profile),
        max_gaps=args.max_gaps,
    )

    payload = report.to_dict()

    if args.save:
        out_dir = settings.artifacts_dir / "auto_content"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"auto-content-cycle-{report.run_date}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 Report saved: {out_path}", file=sys.stderr)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(file=sys.stderr)
    print(report.format_telegram(), file=sys.stderr)
    return 0


def cmd_run_daily(args: argparse.Namespace) -> int:
    from fanpage_agent.tools.publishing.daily_ops import DailyOpsTool as DailyOpsService
    from fanpage_agent.tools.publishing.planner import PlannerTool as PlannerService
    from fanpage_agent.tools.research.research_packet import (
        build_research_packet,
        packet_to_brief_payload,
        save_research_packet,
    )
    from fanpage_agent.tools.content.writer import WriterTool as WriterService
    from .research import build_daily_artifacts

    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings)
    store = build_store(settings=settings, args=args)
    page_context = PageRegistry(settings).page_context(None)
    research_packet = build_research_packet(
        history_file=args.history_file,
        metrics_file=args.metrics_file,
        comment_file=args.comment_file,
        campaign_file=args.campaign_file,
        calendar_file=args.calendar_file,
        job_id=f"daily-{args.run_date}",
        fetch_external_trends=False,
        page_id=str(page_context.get("page_id", "")),
        page_context=page_context,
        source_registry_file=args.source_registry_file,
        fetch_source_documents=args.fetch_source_documents,
        source_cache_dir=args.source_cache_dir,
        discover_sources=args.discover_sources,
        max_discovered_sources=args.max_discovered_sources,
        discover_product_topics=args.discover_product_topics,
        max_product_topics=args.max_product_topics,
    )
    research_brief = research_packet.brief
    packet = DailyOpsService(
        planner=PlannerService(llm_client=llm_client),
        writer=WriterService(llm_client=llm_client),
    ).build_packet(
        profile=profile,
        run_date=args.run_date,
        store=store,
        days=args.days,
        write_calendar=args.write_calendar,
        research_brief=research_brief,
    )
    packet["research_packet"] = packet_to_brief_payload(research_packet)
    if args.save:
        packet["artifacts"] = build_daily_artifacts(settings, packet, args.run_date)
        packet["artifacts"]["research_packet"] = str(
            save_research_packet(research_packet, settings.artifacts_dir / "research_packets")
        )
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


def cmd_deliver_daily_packet(args: argparse.Namespace) -> int:
    from fanpage_agent.tools.publishing.daily_ops import DailyOpsTool as DailyOpsService
    from fanpage_agent.tools.publishing.planner import PlannerTool as PlannerService
    from fanpage_agent.tools.research.research_packet import (
        build_research_packet,
        packet_to_brief_payload,
        save_research_packet,
    )
    from fanpage_agent.tools.content.writer import WriterTool as WriterService
    from .research import build_daily_artifacts

    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings)
    store = build_store(settings=settings, args=args)
    page_context = PageRegistry(settings).page_context(None)
    research_packet = build_research_packet(
        history_file=args.history_file,
        metrics_file=args.metrics_file,
        comment_file=args.comment_file,
        campaign_file=args.campaign_file,
        calendar_file=args.calendar_file,
        job_id=f"daily-{args.run_date}",
        fetch_external_trends=False,
        page_id=str(page_context.get("page_id", "")),
        page_context=page_context,
        source_registry_file=args.source_registry_file,
        fetch_source_documents=args.fetch_source_documents,
        source_cache_dir=args.source_cache_dir,
        discover_sources=args.discover_sources,
        max_discovered_sources=args.max_discovered_sources,
        discover_product_topics=args.discover_product_topics,
        max_product_topics=args.max_product_topics,
    )
    research_brief = research_packet.brief
    packet = DailyOpsService(
        planner=PlannerService(llm_client=llm_client),
        writer=WriterService(llm_client=llm_client),
    ).build_packet(
        profile=profile,
        run_date=args.run_date,
        store=store,
        days=args.days,
        write_calendar=args.write_calendar,
        research_brief=research_brief,
    )
    packet["research_packet"] = packet_to_brief_payload(research_packet)
    if args.save:
        packet["artifacts"] = build_daily_artifacts(settings, packet, args.run_date)
        packet["artifacts"]["research_packet"] = str(
            save_research_packet(research_packet, settings.artifacts_dir / "research_packets")
        )
        if args.write_calendar:
            packet["store"] = {
                "calendar": store.attach_draft_caption_ref(
                    calendar_id=packet["calendar_id"],
                    caption_ref=packet["artifacts"]["caption_package"],
                    updated_at=args.run_date,
                )
            }
    packet["delivery"] = DeliveryTool(settings).deliver_daily_packet(
        packet, chat_id=getattr(args, "chat_id", None)
    )
    print(json.dumps(packet, ensure_ascii=False, indent=2))
    return 0


def cmd_publish_post(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    row = _find_calendar_item_for_publish(store, args.calendar_id)
    if not args.allow_unapproved and (
        row is None
        or row.get("approval_status") != "approved"
        or not row.get("final_caption_ref")
        or row.get("status") in {"published", "posted"}
    ):
        print(json.dumps(_build_publish_block_payload(args.calendar_id, row), ensure_ascii=False, indent=2))
        return 2

    published = store.publish_calendar_item(
        calendar_id=args.calendar_id,
        published_at=args.published_at,
        permalink=args.permalink,
        reach=args.reach,
        engagement_rate=args.engagement_rate,
    )
    print(json.dumps(published, ensure_ascii=False, indent=2))
    return 0


def cmd_process_pending(args: argparse.Namespace) -> int:
    from fanpage_agent.tools.content.auto_approval import AutoApprovalConfig, AutoApprovalEngine
    from fanpage_agent.tools.content.verifier import VerifierTool as VerifierService

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
    from fanpage_agent.tools.publishing.scheduled_publish import ScheduledPublishTool as ScheduledPublishService
    from fanpage_agent.tools.content.verifier import VerifierTool as VerifierService

    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    store = LocalSheetStore(
        calendar_csv=args.calendar_file,
        history_csv=args.history_file,
        hashtag_csv=settings.artifacts_dir / "_local_store" / "hashtag_performance.csv",
    )

    fb_client: FacebookClient | None = None
    if settings.fb_page_id and settings.fb_page_token:
        fb_client = FacebookClient(settings)

    from fanpage_agent.tools.content.image_gen import build_image_service as ImageGenTool

    image_service = ImageGenTool(settings)

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
    from fanpage_agent.tools.content.image_gen import build_image_service as ImageGenTool

    settings = Settings.from_env(root_dir=ROOT_DIR)

    prompt = args.prompt
    if not prompt:
        prompt = sys.stdin.read().strip()
    if not prompt:
        print("ERROR: No prompt provided. Pass as argument or pipe via stdin.", file=sys.stderr)
        return 1

    svc = ImageGenTool(settings)
    output = args.output or None
    result_path = svc.generate(prompt, output_dir=output)
    print(json.dumps({"image_path": result_path}, ensure_ascii=False, indent=2))
    return 0


def cmd_list_calendar(args: argparse.Namespace) -> int:
    """List content calendar items with filters."""
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

    print(f"📋 Calendar items ({len(items)}):\n")
    for item in items:
        cid = item.get("calendar_id", "?")
        b = item.get("brand_id", "?")
        d = item.get("date", "?")
        t = str(item.get("topic", "?"))[:50]
        s = item.get("status", "?")
        a = f"{str(item.get('approval_status', '?'))[:8]}"
        p = "📸" if item.get("visual_brief") else ""
        print(f"  [{s}/{a}] {d} | {b} | {cid}\n    {t} {p}")
    return 0


def cmd_approve_calendar_item(args: argparse.Namespace) -> int:
    """Approve a content calendar item."""
    store = LocalSheetStore(
        calendar_csv=args.calendar_file,
        history_csv=args.history_file,
    )
    now = datetime.now(timezone.utc).isoformat()
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
    store = LocalSheetStore(
        calendar_csv=args.calendar_file,
        history_csv=args.history_file,
    )
    now = datetime.now(timezone.utc).isoformat()
    result = store.reject_calendar_item(
        calendar_id=args.calendar_id,
        reason=args.reason,
        rejected_at=now,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_check_calendar_gaps(args: argparse.Namespace) -> int:
    """Find gaps in the content calendar."""
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
        print("✅ No significant gaps found.")
    else:
        for g in gaps:
            print(f"  ⚠️  Gap: {g['start_date']} → {g['end_date']} ({g['gap_days']} days)")
    return 0


def cmd_fill_calendar_gaps(args: argparse.Namespace) -> int:
    """Auto-detect and fill gaps in the content calendar."""
    from fanpage_agent.tools.publishing.calendar_gap_service import CalendarGapTool as CalendarGapService
    from fanpage_agent.tools.publishing.planner import PlannerTool as PlannerService
    from fanpage_agent.tools.content.writer import WriterTool as WriterService

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
        import json as _json

        print(_json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if result.filled_count > 0:
        print(f"✅ Filled {result.filled_count} gap(s):")
        for item in result.filled:
            print(f"  📝 {item['date']} — {item['pillar']}: {item['topic']}")
    else:
        print("ℹ️  No gaps filled.")

    if result.skipped_count > 0:
        print(f"⏭️  Skipped {result.skipped_count}:")
        for item in result.skipped:
            print(f"  {item['date']} — {item['reason']}")

    if result.error_count > 0:
        print(f"❌ {result.error_count} error(s):")
        for item in result.errors:
            print(f"  {item.get('date', item.get('calendar_id', '?'))} — {item['reason']}")

    return 0 if result.error_count == 0 else 1


# ── Content Queue handlers (Phase 4) ────────────────────────────


def cmd_queue_show(args: argparse.Namespace) -> int:
    """Show content queue with optional filters."""
    from fanpage_agent.tools.publishing.content_queue import ContentQueueTool

    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    queue_svc = ContentQueueTool(store=store)

    result = queue_svc.show_queue(
        status=args.status,
        topic=args.topic,
        pillar=args.pillar,
        limit=args.limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Pretty-print stats to stderr
    stats = result["stats"]
    print(f"\n📊 Queue stats: {stats['queued']} queued | {stats['approved']} approved | "
          f"{stats['rejected']} rejected | {stats['published']} published | "
          f"{stats['failed']} failed | {stats['total']} total", file=sys.stderr)

    items = result.get("items", [])
    if not items:
        print("📭 Queue is empty.", file=sys.stderr)
        return 0
    print(f"\n📋 Queue items ({len(items)}):", file=sys.stderr)
    for item in items[:20]:
        cid = item.get("calendar_id", "?")
        s = item.get("queue_status", "?")
        t = str(item.get("topic", "?"))[:40]
        p = item.get("pillar", "?")
        print(f"  [{s}] {t} ({p}) | {cid}", file=sys.stderr)
    return 0


def cmd_queue_enqueue(args: argparse.Namespace) -> int:
    """Enqueue a calendar item into the content queue."""
    from fanpage_agent.tools.publishing.content_queue import ContentQueueTool

    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    queue_svc = ContentQueueTool(store=store)

    result = queue_svc.enqueue_from_calendar(
        calendar_id=args.calendar_id,
        batch_id=args.batch_id or "",
        scheduled_for=args.scheduled_for or "",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("enqueued") else 1


def cmd_queue_approve(args: argparse.Namespace) -> int:
    """Approve a queued item (single or batch)."""
    from fanpage_agent.tools.publishing.content_queue import ContentQueueTool

    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    queue_svc = ContentQueueTool(store=store)

    if args.all or args.pillar or args.topic:
        result = queue_svc.batch_approve(
            pillar=args.pillar, topic=args.topic,
            approved_by=args.approved_by or "admin",
            limit=args.limit,
        )
    elif args.calendar_id:
        result = queue_svc.approve_item(
            calendar_id=args.calendar_id,
            approved_by=args.approved_by or "admin",
        )
    else:
        print("ERROR: Specify --calendar-id or --all / --pillar / --topic", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    approved = result.get("approved_count") or (1 if result.get("approved") else 0)
    print(f"✅ Approved {approved} item(s)", file=sys.stderr)
    return 0


def cmd_queue_reject(args: argparse.Namespace) -> int:
    """Reject a queued item (single or batch)."""
    from fanpage_agent.tools.publishing.content_queue import ContentQueueTool

    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    queue_svc = ContentQueueTool(store=store)

    reason = args.reason or ""
    if args.all or args.pillar or args.topic:
        result = queue_svc.batch_reject(
            pillar=args.pillar, topic=args.topic,
            reason=reason, limit=args.limit,
        )
    elif args.calendar_id:
        result = queue_svc.reject_item(
            calendar_id=args.calendar_id, reason=reason,
        )
    else:
        print("ERROR: Specify --calendar-id or --all / --pillar / --topic", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    rejected = result.get("rejected_count") or (1 if result.get("rejected") else 0)
    print(f"⛔ Rejected {rejected} item(s)", file=sys.stderr)
    return 0


def cmd_queue_publish(args: argparse.Namespace) -> int:
    """Publish approved queue items to Facebook."""
    from fanpage_agent.tools.publishing.content_queue import ContentQueueTool
    from fanpage_agent.adapters.facebook_client import FacebookClient

    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)

    fb_client: FacebookClient | None = None
    if not args.dry_run:
        try:
            fb_client = FacebookClient(settings)
        except Exception as exc:
            print(f"⚠️  No FB client available: {exc}", file=sys.stderr)
            print("Use --dry-run to preview without FB API.", file=sys.stderr)

    queue_svc = ContentQueueTool(store=store, fb_client=fb_client, dry_run=args.dry_run)

    if args.calendar_id:
        result = queue_svc.publish_to_facebook(calendar_id=args.calendar_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("published"):
            print(f"✅ Published {args.calendar_id}", file=sys.stderr)
        else:
            print(f"❌ Failed: {result.get('error', 'unknown')}", file=sys.stderr)
            return 1
    else:
        result = queue_svc.batch_publish_to_facebook(
            pillar=args.pillar, topic=args.topic, limit=args.limit,
        )
        payload = result.to_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"✅ Published: {payload['published_count']} | "
              f"❌ Failed: {payload['failed_count']} | "
              f"⏭️ Skipped: {payload['skipped_count']}", file=sys.stderr)
    return 0


def cmd_queue_stats(args: argparse.Namespace) -> int:
    """Show queue statistics only."""
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    stats = store.get_queue_stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"\n📊 Queue: {stats['queued']} queued | {stats['approved']} approved | "
          f"{stats['rejected']} rejected | {stats['published']} published | "
          f"{stats['failed']} failed | {stats['total']} total", file=sys.stderr)
    return 0


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


def cmd_weekly_report(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    load_brand_profile(args.brand_file)  # validate brand exists
    store = build_store(settings=settings, args=args)
    metrics = store.read_post_metrics()
    report = AnalyticsTool().build_weekly_report(metrics)
    payload = report.model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "reports" / "weekly-report.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_weekly_report(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    load_brand_profile(args.brand_file)
    store = build_store(settings=settings, args=args)
    metrics = store.read_post_metrics()
    payload = AnalyticsTool().build_weekly_report(metrics).model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "reports" / "weekly-report.json", payload)
    payload["delivery"] = DeliveryTool(settings).deliver_weekly_report(
        payload, chat_id=getattr(args, "chat_id", None)
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_build_strategy(args: argparse.Namespace) -> int:
    """Build a content strategy from brand profile + optional research brief.

    Runs StrategistTool to produce pillar mix, trend ideas, competitor gap fills.
    Saves to artifacts if --save is set.
    """
    from fanpage_agent.tools.content.strategist import StrategistTool

    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings) if not args.no_llm else None
    strategist = StrategistTool(llm_client=llm_client)

    # Load research brief if available
    research_brief: ResearchBrief | None = None
    if args.research_file:
        try:
            data = json.loads(Path(args.research_file).read_text(encoding="utf-8"))
            # ResearchPacket wrapper or raw ResearchBrief
            brief_data = data.get("brief", data)
            research_brief = ResearchBrief(**brief_data)
        except Exception as exc:
            print(f"⚠️  Could not load research brief: {exc}", file=sys.stderr)
    elif args.build_research:
        # Build fresh research brief
        from .research import build_research_brief

        store = build_store(settings=settings, args=args)
        # We create dummy args to call build_research_brief
        dummy_args = argparse.Namespace(
            comment_file=None,
            campaign_file=None,
            scan_competitor=True,
            competitor_pages=None,
            store_backend="local",
        )
        research_brief = build_research_brief(dummy_args)
        print("✅ Research brief built from live data.", file=sys.stderr)

    strategy = strategist.build_strategy(profile=profile, research_brief=research_brief)
    payload = strategy.model_dump(mode="json")

    if args.save:
        out_dir = settings.artifacts_dir / "strategies"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"strategy-{strategy.generated_at[:19].replace(':', '-')}.json"
        dump_json(out_path, payload)
        print(f"💾 Saved to {out_path}", file=sys.stderr)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0
