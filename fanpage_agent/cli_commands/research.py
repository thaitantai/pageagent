from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.config import Settings
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer
from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.scraping.web_search import WebSearchClient
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.utils import dump_json

from .parser import ROOT_DIR, add_store_backend_arg, with_default_store_backend


def _build_research_service(timeout: int = 15) -> ResearchTool:
    """Build ResearchTool với TrendScraper + WebSearchClient tích hợp."""
    web_search = WebSearchClient()
    scraper = TrendScraper(timeout=timeout, web_search=web_search)
    return ResearchTool(trend_scraper=scraper)


def build_research_brief(args: argparse.Namespace):
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=with_default_store_backend(args))
    return _build_research_service().build_brief(
        store=store,
        comment_csv=args.comment_file,
        campaign_notes_file=args.campaign_file,
    )


def summarize_triage_items(items: list[dict]) -> dict:
    summary: dict[str, object] = {
        "total_items": len(items),
        "by_category": {},
        "by_priority": {},
        "by_status": {},
        "escalation_count": 0,
        "approval_required_count": 0,
    }
    by_category: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_status: dict[str, int] = {}
    escalation_count = 0
    approval_required_count = 0
    for item in items:
        category = str(item.get("category", "") or "unknown")
        priority = str(item.get("priority", "") or "unknown")
        status = str(item.get("status", "") or "unknown")
        by_category[category] = by_category.get(category, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        if str(item.get("escalation_required", "")).lower() == "true":
            escalation_count += 1
        if str(item.get("requires_human_approval", "")).lower() == "true":
            approval_required_count += 1
    summary["by_category"] = by_category
    summary["by_priority"] = by_priority
    summary["by_status"] = by_status
    summary["escalation_count"] = escalation_count
    summary["approval_required_count"] = approval_required_count
    return summary


def summarize_calendar_items(items: list[dict]) -> dict:
    summary: dict[str, object] = {
        "total_items": len(items),
        "by_status": {},
        "by_approval_status": {},
        "by_pillar": {},
    }
    by_status: dict[str, int] = {}
    by_approval_status: dict[str, int] = {}
    by_pillar: dict[str, int] = {}
    for item in items:
        status = str(item.get("status", "") or "unknown")
        approval_status = str(item.get("approval_status", "") or "unknown")
        pillar = str(item.get("pillar", "") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_approval_status[approval_status] = by_approval_status.get(approval_status, 0) + 1
        by_pillar[pillar] = by_pillar.get(pillar, 0) + 1
    summary["by_status"] = by_status
    summary["by_approval_status"] = by_approval_status
    summary["by_pillar"] = by_pillar
    return summary


def build_daily_artifacts(settings: Settings, packet: dict, run_date: str) -> dict[str, str]:
    packet_path = settings.artifacts_dir / "ops" / f"daily-ops-{run_date}.json"
    calendar_id = str(packet.get("calendar_id", "daily-packet")).replace("/", "-")
    caption_path = settings.artifacts_dir / "captions" / f"daily-caption-{calendar_id}.json"
    dump_json(packet_path, packet)
    dump_json(caption_path, packet.get("caption_package", {}))
    return {
        "packet": str(packet_path),
        "caption_package": str(caption_path),
    }


def build_triage_store_payload(args: argparse.Namespace) -> dict:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    items = build_store(settings=settings, args=with_default_store_backend(args)).list_triage_items(
        status=getattr(args, "status", None),
        priority=getattr(args, "priority", None),
        assigned_to=getattr(args, "assigned_to", None),
        limit=getattr(args, "limit", None),
    )
    return {
        "items": items,
        "summary": summarize_triage_items(items),
    }


def cmd_research_brief(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    brief = build_research_brief(args)
    payload = brief.model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "research" / "research-brief.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_search_trends(args: argparse.Namespace) -> int:
    """CLI command: search web → scrape URLs → print TrendItems as JSON."""
    web_search = WebSearchClient()
    scraper = TrendScraper(timeout=args.timeout, web_search=web_search)
    results = scraper.search_trends(
        queries=args.queries,
        max_results_per_query=args.max_per_query,
        max_articles=args.max_articles,
    )
    payload = [r.model_dump(mode="json") for r in results]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n📦 Tổng cộng: {len(results)} TrendItem", file=sys.stderr)
    return 0


def cmd_research_trends(args: argparse.Namespace) -> int:
    """Scrape web trends and analyze for skincare/healthcare topics."""
    scraper = TrendScraper(timeout=args.timeout)
    trends = scraper.fetch_all()

    if not trends:
        print("⚠ Khong lay duoc trend tu nguon nao.")
        return 1

    analyzer = TrendAnalyzer(trends)
    report = analyzer.generate_report()

    if args.tldr:
        print(f"📊 {report['total_trends']} trends tu {len(report['sources'])} nguon\n")
        print("Top keywords:")
        for kw in report["top_keywords"][:10]:
            print(f"  {kw['word']} ({kw['count']})")
        print()
        for label, items in list(report["clusters"].items())[:5]:
            print(f"[{label}] ({len(items)} items)")
        print()
        print("Top relevant cho skincare/healthcare:")
        for item in report["top_relevant"][:5]:
            print(f"  {item['score']:.0%} - {item['title'][:60]}")
    else:
        # Full report
        print("=== 🌐 Research Trends ===")
        print(f"Tong: {report['total_trends']} trends tu {len(report['sources'])} nguon\n")

        print("--- Top Keywords ---")
        for kw in report["top_keywords"][:20]:
            print(f"  {kw['word']:20s} ✕ {kw['count']}")

        print("\n--- Top Phrases ---")
        for ph in report["top_phrases"][:15]:
            print(f"  {ph['phrase']:30s} ✕ {ph['count']}")

        print("\n--- Clusters ---")
        for label, items in list(report["clusters"].items())[:10]:
            print(f"  [{label}] ({len(items)} items)")
            for t in items[:3]:
                print(f"    - {t[:60]}")
            if len(items) > 3:
                print(f"    ... +{len(items)-3} more")

        print("\n--- Top Relevant (skincare/healthcare) ---")
        for item in report["top_relevant"][:10]:
            print(f"  {item['score']:.0%} | {item['title'][:55]}")
            print(f"     [{item['source']}]")

    if args.save:
        path = ROOT_DIR / "data" / f"research-trends-{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        dump_json(path, report)
        print(f"\n💾 Saved to {path}")

    return 0
