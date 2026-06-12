from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.config import Settings
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer
from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.scraping.web_search import WebSearchClient
from fanpage_agent.tools.research.competitor_page_discovery import (
    CompetitorPageDiscoveryTool,
)
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.utils import dump_json

from .parser import ROOT_DIR, add_store_backend_arg, with_default_store_backend


def _build_research_service(
    timeout: int = 15,
) -> ResearchTool:
    """Build ResearchTool với TrendScraper + WebSearchClient tích hợp.

    Parameters
    ----------
    timeout : int
        HTTP timeout for web scraping.
    """
    web_search = WebSearchClient()
    scraper = TrendScraper(timeout=timeout, web_search=web_search)
    # CompetitorPageDiscoveryTool tự tạo MultiSourceSearchClient khi cần
    competitor_discovery = CompetitorPageDiscoveryTool()
    return ResearchTool(
        trend_scraper=scraper,
        competitor_discovery=competitor_discovery,
        # CompetitorLearningEngine lazy init bên trong ResearchTool.__init__
    )


def build_research_brief(args: argparse.Namespace):
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=with_default_store_backend(args))

    # ── Competitor page scan ──
    scan_competitor = getattr(args, "scan_competitor", False) or False
    competitor_names: list[str] | None = None

    if scan_competitor:
        # Read competitor_page_names from page config (multi-page setup)
        try:
            page_config = settings.get_page_config(settings.fb_page_id)
            competitor_names = list(page_config.competitor_page_names or [])
        except Exception:
            competitor_names = []

        # Fallback: load from brand profile JSON (skincare_genz.json)
        if not competitor_names:
            try:
                from fanpage_agent.loaders.brand_loader import load_brand_profile
                brand_path = ROOT_DIR / "brand_profiles" / "skincare_genz.json"
                if brand_path.exists():
                    profile = load_brand_profile(brand_path)
                    competitor_names = list(getattr(profile, "competitor_page_names", []) or [])
            except Exception:
                pass

        # CLI override: --competitor-pages name1 name2 (vẫn dùng tên, ko phải FB ID)
        cli_pages = getattr(args, "competitor_pages", None)
        if cli_pages:
            competitor_names = [
                p.strip() for p in cli_pages if p.strip()
            ]

    rt = _build_research_service()
    return rt.build_brief(
        store=store,
        comment_csv=args.comment_file,
        campaign_notes_file=args.campaign_file,
        scan_competitor_pages=scan_competitor,
        competitor_names=competitor_names,
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


def cmd_learn(args: argparse.Namespace) -> int:
    """Run or inspect the Research Agent's self-learning cycle."""
    from fanpage_agent.adapters.sqlite_store import UnifiedStore
    from fanpage_agent.tools.research.learning_optimizer import (
        ConfidenceCalibrator,
        DecayModel,
        GoalWeightOptimizer,
        PerformancePredictor,
        WeightOptimizer,
    )

    store = UnifiedStore()

    if args.lifecycle:
        from fanpage_agent.tools.research.learning_optimizer import LifecycleManager
        report = LifecycleManager(store).get_lifecycle_report()
        print("=== 🔄 Topic Lifecycle Report ===\n")
        print(f"Total topics tracked: {report['total_topics']}\n")
        for stage in ("explore", "active", "mature", "retire"):
            entry = report["by_stage"][stage]
            icon = {"explore": "🌱", "active": "✅", "mature": "💰", "retire": "⏹"}[stage]
            print(f"  {icon} {stage.title()}: {entry['count']} topics")
            for t in entry["topics"]:
                posts = t["total_posts"]
                days_post = t["days_since_publish"]
                days_stage = t["days_in_stage"]
                last = t["last_published"] or "never"
                print(f"      {t['topic'][:40]:40s} | {posts} posts | last {last} ({days_post}d ago)")
        return 0

    if args.set_lifecycle:
        topic, stage = args.set_lifecycle
        from fanpage_agent.adapters.sqlite_store import UnifiedStore
        try:
            result = store.set_topic_stage(topic, stage)
            print(f"✅ Topic '{result['topic']}' set to stage '{result['stage']}'")
            return 0
        except ValueError as e:
            print(f"❌ {e}")
            return 1

    if args.auto_lifecycle:
        from fanpage_agent.tools.research.learning_optimizer import LifecycleManager
        result = LifecycleManager(store).run()
        if result["transitions"]:
            print("=== 🔄 Auto Lifecycle Transitions ===\n")
            for t in result["transitions"]:
                arrow = "→"
                print(f"  {t['topic'][:40]:40s} {t['from']} {arrow} {t['to']}")
                print(f"      {t['reason']} ({t['total_posts']} posts)")
        else:
            print("⏭ No transitions needed.")
        return 0

    if args.auto_discover:
        from fanpage_agent.tools.research.competitor_learning_engine import CompetitorLearningEngine
        from fanpage_agent.tools.research.competitor_page_discovery import CompetitorPageDiscoveryTool

        discovery_tool = CompetitorPageDiscoveryTool()
        engine = CompetitorLearningEngine(
            discovery_tool=discovery_tool,
            store=store,
        )
        result = engine.scan_auto_discover()
        if result["status"] == "no_candidates":
            print("⏭ No candidates ready for promotion yet.")
        elif result["status"] == "promotion_failed":
            print("⚠ Candidate promotion failed.")
        else:
            promoted = result.get("promoted", [])
            print(f"✅ Promoted {len(promoted)} new competitors: {', '.join(promoted)}")
            scan = result.get("scan", {})
            if scan:
                for name in promoted:
                    profile = None
                    for p in scan.get("profiles", []):
                        if p.get("name", "").lower() == name.lower():
                            profile = p
                            break
                    if profile:
                        print(f"   {name}: {len(profile.get('products_detected', []))} products, "
                              f"angle={profile.get('unique_angle', '?')}")
        return 0

    if args.status:
        weights = store.get_weights()
        print("=== ⚖ Global Weights ===")
        for name, value in weights.items():
            print(f"  {name:30s} {value}")

        # Show per-goal weight summaries
        goal_types = store.get_goal_types()
        print(f"\n=== 🎯 Per-Goal Weights ({len(goal_types)} goals) ===")
        for gt in goal_types:
            gw = store.get_weights_for_goal(gt)
            print(f"  [{gt}]")
            for name in ("brand_relevance", "novelty", "content_potential",
                         "source_confidence", "fanpage_fit", "customer_value"):
                print(f"    {name:30s} {gw.get(name, 0):.4f}")
            print(f"    {'evidence_confidence_floor':30s} {gw.get('evidence_confidence_floor', 0.45)}")

        # Show predictor quality
        predictor = PerformancePredictor(store)
        pq = predictor.get_quality()
        if pq["status"] == "trained":
            drift_warn = " ⚠️ DRIFT DETECTED" if pq["drift"] else ""
            print(f"\n=== 🔮 Performance Predictor{drift_warn} ===")
            print(f"  MAE: {pq['mae']} engagements")
            print(f"  MAPE: {pq['mape']:.1%}")
            print(f"  R²: {pq['r2']}")
            print(f"  Samples: {pq['sample_count']}")
            print(f"  Trained at: {pq['trained_at'][:19]}")
            if pq.get("drift_message"):
                print(f"  ⚠ {pq['drift_message']}")
        else:
            print(f"\n=== 🔮 Performance Predictor ===")
            print(f"  {pq.get('message', 'Not trained yet.')}")

        runs = store.get_learning_runs(limit=5)
        if runs:
            print(f"\n=== 🧠 Recent Learning Runs ({len(runs)}) ===")
            for r in runs:
                print(f"  [{r['run_type']}] {r['executed_at'][:19]}")
        return 0

    if args.goal_types:
        goal_types = store.get_goal_types()
        print(f"=== 🎯 Registered Goal Types ({len(goal_types)}) ===")
        for gt in goal_types:
            gw = store.get_weights_for_goal(gt)
            print(f"  [{gt}] novelty={gw.get('novelty', 0):.2f} brand={gw.get('brand_relevance', 0):.2f} "
                  f"content={gw.get('content_potential', 0):.2f} conv={gw.get('customer_value', 0):.2f}")
        return 0

    if args.list_goals:
        goals = store.get_all_topic_goals()
        if not goals:
            print("No topic → goal assignments yet.")
            return 0
        print(f"=== 🎯 Topic → Goal Assignments ({len(goals)}) ===")
        for g in goals:
            print(f"  {g['topic'][:40]:40s} → {g['goal_type']:15s} (updated {g['updated_at'][:19]})")
        return 0

    if args.set_goal:
        topic, goal_type = args.set_goal
        if goal_type not in store.GOAL_TYPES:
            print(f"❌ Invalid goal type '{goal_type}'. Valid: {', '.join(store.GOAL_TYPES)}")
            return 1
        store.set_topic_goal(topic, goal_type)
        print(f"✅ Topic '{topic}' assigned to goal '{goal_type}'")
        return 0

    if args.history:
        limit = min(50, max(1, args.history))
        runs = store.get_learning_runs(limit=limit)
        if not runs:
            print("No learning runs recorded yet.")
            return 0
        print(f"=== 🧠 Last {len(runs)} Learning Runs ===")
        for r in runs:
            smry = r["summary"]
            changes = smry.get("changes", []) if isinstance(smry, dict) else []
            decayed = smry.get("decayed_count", 0) if isinstance(smry, dict) else 0
            print(f"\n  [{r['id']}] {r['run_type']}")
            print(f"       At: {r['executed_at'][:19]}")
            if changes:
                print(f"       Changes: {len(changes)} weights adjusted")
                for c in changes[:5]:
                    d = c.get("delta", 0)
                    arrow = "▲" if d > 0 else "▼"
                    print(f"         {c['weight_name']}: {c['from']} → {c['to']} ({arrow}{abs(d):.4f})")
            if decayed:
                print(f"       Decayed: {decayed} topics")
        return 0

    results: dict[str, Any] = {}

    if args.optimize or args.all or args.goal:
        if args.goal:
            # Per-goal optimization
            optimizer = GoalWeightOptimizer(store)
            results["optimize"] = optimizer.run(args.goal)
        else:
            # Global optimization
            optimizer = WeightOptimizer(store)
            results["optimize"] = optimizer.run()

    # If --goal was used alone (without --optimize), make sure we print results
    if args.goal and not args.optimize and not args.all and not args.calibrate and not args.decay and not args.predict:
        pass  # results will be printed below

    if args.calibrate or args.all:
        calibrator = ConfidenceCalibrator(store)
        results["calibrate"] = calibrator.run()

    if args.decay or args.all:
        decay = DecayModel(store)
        results["decay"] = decay.run()

    # Lifecycle transition is always run as part of --all
    if args.all:
        from fanpage_agent.tools.research.learning_optimizer import LifecycleManager as _LifecycleManager
        results["lifecycle"] = _LifecycleManager(store).run()

    if args.predict:
        predictor = PerformancePredictor(store)
        results["predict"] = predictor.train()

    print("=== 🧠 Self-Learning Cycle ===\n")

    if "optimize" in results:
        opt = results["optimize"]
        goal_label = f" [{opt.get('goal_type', 'global')}]" if opt.get("goal_type") else ""
        status_icon = "✅" if opt["status"] == "ok" else ("⏭" if opt["status"] == "no_change" else "⚠")
        print(f"{status_icon} WeightOptimizer{goal_label}: {opt['status']}")
        if opt.get("changes"):
            for c in opt["changes"]:
                d = c.get("delta", 0)
                arrow = "▲" if d > 0 else "▼"
                print(f"   {c['weight_name']:30s} {c['from']} → {c['to']} ({arrow}{abs(d):.4f}) corr={c['correlation']:.3f}")
        if "analysis_summary" in opt:
            s = opt["analysis_summary"]
            print(f"   ({s['total_weights_analyzed']} analyzed, {s['weights_adjusted']} adjusted)")

    if "calibrate" in results:
        cal = results["calibrate"]
        status_icon = "✅" if cal["status"] == "ok" else ("⏭" if cal["status"] == "no_change" else "⚠")
        print(f"{status_icon} ConfidenceCalibrator: {cal['status']}")
        if cal.get("adjustments"):
            for a in cal["adjustments"]:
                print(f"   {a['target']}: {a['from']} → {a['to']} ({a['reason']})")

    if "decay" in results:
        dc = results["decay"]
        status_icon = "✅" if dc["status"] == "ok" else ("⏭" if dc["status"] == "no_decay_needed" else "⚠")
        print(f"{status_icon} DecayModel: {dc['status']} — {dc.get('decayed_topics', 0)}/{dc.get('total_topics', 0)} topics decayed")
        if dc.get("details"):
            for d_ in dc["details"][:10]:
                print(f"   {d_['topic'][:35]:35s} {d_['days_since_update']:3d}d ago → factor {d_['decay_factor']}")

    if "predict" in results:
        pr = results["predict"]
        if pr["status"] == "ok":
            drift_warn = " ⚠️ DRIFT DETECTED" if pr.get("drift") else ""
            print(f"✅ PerformancePredictor: trained ✓{drift_warn}")
            print(f"   Model: log(eng+1) = {pr['params']['slope']} × score + {pr['params']['intercept']}")
            print(f"   MAE: {pr['metrics']['mae']} eng  |  MAPE: {pr['metrics']['mape']:.1%}  |  R²: {pr['metrics']['r2']}")
            print(f"   Samples: {pr['sample_count']}")
            if pr.get("drift_message"):
                print(f"   ⚠ {pr['drift_message']}")
        else:
            print(f"⏭ PerformancePredictor: {pr.get('reason', 'skipped')}")

    if "lifecycle" in results:
        lc = results["lifecycle"]
        icon = "🔄" if lc["transition_count"] > 0 else "⏭"
        print(f"{icon} LifecycleManager: {lc['status']} — {lc['transition_count']} transitions")
        if lc.get("transitions"):
            for t in lc["transitions"]:
                print(f"   {t['topic'][:35]:35s} {t['from']} → {t['to']} ({t['reason']})")

    return 0
