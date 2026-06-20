from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.adapters.llm import build_llm_client
from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.analytics.analytics_dashboard import AnalyticsDashboardTool
from fanpage_agent.tools.analytics.analytics_reviewer import AnalyticsReviewer
from fanpage_agent.tools.analytics.evals import EvalTool
from fanpage_agent.tools.data.data_fetch import DataFetchTool
from fanpage_agent.tools.data.metrics_auto_fetch import MetricsAutoFetchTool
from fanpage_agent.tools.publishing.delivery import DeliveryTool
from fanpage_agent.tools.publishing.telegram_formatter import TelegramFormatterTool
from fanpage_agent.utils import dump_json

from .parser import ROOT_DIR


def cmd_analytics_review(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    store = build_store(settings=settings, args=args)
    tool = AnalyticsReviewer(store=store, profile=profile, settings=settings)
    review = tool.review(
        days=args.days, now=getattr(args, "now", None), record=getattr(args, "record", False)
    )
    payload = review.model_dump(mode="json")
    if args.save:
        dump_json(
            settings.artifacts_dir / "analytics" / f"analytics-review-{review.period_start}.json",
            payload,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_analytics_review(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    profile = load_brand_profile(args.brand_file)
    tool = AnalyticsReviewer(store=store, profile=profile, settings=settings)
    review = tool.review(
        days=args.days, now=getattr(args, "now", None), record=getattr(args, "record", False)
    )
    payload = review.model_dump(mode="json")
    payload["delivery"] = DeliveryTool(settings).deliver_analytics_review(
        payload, chat_id=args.chat_id
    )
    if args.save:
        dump_json(
            settings.artifacts_dir / "analytics" / f"analytics-review-{review.period_start}.json",
            payload,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_generate_dashboard(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    metrics = build_store(settings=settings, args=args).read_post_metrics()
    svc = AnalyticsDashboardTool(settings.artifacts_dir)
    result = svc.generate(metrics, days=args.days)

    payload = {
        "type": "dashboard",
        "path": result["path"],
        "generated_at": result["generated_at"],
        "total_posts": result["total_posts"],
        "total_reach": result["total_reach"],
        "total_engagements": result["total_engagements"],
    }
    if args.save:
        dump_json(settings.artifacts_dir / "analytics" / "dashboard.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver_dashboard(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    metrics = build_store(settings=settings, args=args).read_post_metrics()
    svc = AnalyticsDashboardTool(settings.artifacts_dir)
    result = svc.generate(metrics, days=args.days)

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


def cmd_eval_all(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    store = build_store(settings=settings, args=args)
    payload = EvalTool(llm_client=build_llm_client(settings)).run_all(
        profile=profile,
        store=store,
        comment_csv=args.comment_file,
        campaign_notes_file=args.campaign_file,
        start_date=args.start_date,
    )
    if args.save:
        dump_json(
            settings.artifacts_dir / "evals" / f"eval-summary-{args.start_date}.json", payload
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["summary"]["failed"] == 0 else 1


def cmd_auto_fetch_metrics(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    service = MetricsAutoFetchTool(settings=settings)
    result = service.auto_fetch(store=store, days_back=args.days_back)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        formatter = TelegramFormatterTool()
        print(formatter.format_metrics_auto_fetch(result))

    return 0


def cmd_fetch_fb_comments(args: argparse.Namespace) -> int:
    """Fetch real comments from FB API and merge into comment_inbox.csv."""

    settings = Settings.from_env(root_dir=ROOT_DIR)
    comment_path = Path(args.comment_file)

    # 1. Fetch recent posts from FB
    fb = FacebookClient(settings)
    print(f"📡 Fetching up to {args.post_limit} recent posts from FB...")
    try:
        posts = fb.get_page_posts(limit=args.post_limit)
    except Exception as e:
        print(f"❌ Failed to fetch posts: {e}")
        return 1

    if not posts:
        print("⚠️  No recent posts found.")
        return 0

    # 2. Fetch comments for each post
    all_comments: list[dict] = []
    for post in posts:
        post_id = post.get("id", "")
        if not post_id:
            continue
        print(f"  📝 Post {post_id}: fetching comments...")
        try:
            comments = fb.get_comments(post_id, limit=args.comment_limit)
        except Exception as e:
            print(f"  ⚠️  Error fetching comments for {post_id}: {e}")
            continue
        for c in comments:
            c["post_id"] = post_id
            all_comments.append(c)

    print(f"✅ Fetched {len(all_comments)} comments across {len(posts)} posts.")

    if not all_comments:
        return 0

    # 3. Read existing comments
    existing_ids: set[str] = set()
    existing_rows: list[dict] = []
    if comment_path.exists():
        with comment_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or ["id", "post_id", "created_at", "source", "message"]
            for row in reader:
                existing_rows.append(row)
                if row.get("id"):
                    existing_ids.add(row["id"])

    # 4. Merge new comments (dedup by FB comment id)
    new_rows: list[dict] = []
    for c in all_comments:
        cid = c.get("id", "")
        if cid and cid in existing_ids:
            continue
        new_rows.append(
            {
                "id": c.get("id", ""),
                "post_id": c.get("post_id", ""),
                "created_at": c.get("created_time", ""),
                "source": "facebook_comment",
                "message": c.get("message", ""),
            }
        )
        if cid:
            existing_ids.add(cid)

    if not new_rows:
        print("ℹ️  No new comments to add.")
        return 0

    # 5. Write back
    all_rows = existing_rows + new_rows
    fieldnames = ["id", "post_id", "created_at", "source", "message"]
    with comment_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"✅ Added {len(new_rows)} new comments. Total: {len(all_rows)}.")
    if args.json:
        print(json.dumps({"added": len(new_rows), "total": len(all_rows)}, ensure_ascii=False))

    return 0


def cmd_fetch_fb_data(args: argparse.Namespace) -> int:
    """Fetch posts + insights + comments from FB → populate store."""
    from fanpage_agent.config import Settings as _Settings

    settings = _Settings.from_env(root_dir=ROOT_DIR)
    store = build_store(settings=settings, args=args)
    comment_csv = args.comment_file if not args.skip_comments else None
    service = DataFetchTool(
        settings=settings,
        store=store,
        comment_csv=comment_csv,
    )
    result = service.fetch_all(
        post_limit=args.post_limit,
        comment_posts=args.comment_posts if not args.skip_comments else 0,
        comment_limit=args.comment_limit,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        emoji = "✅" if result["status"] == "ok" else "❌"
        print(f"{emoji} DataFetch complete:")
        print(f"  📜 Posts fetched:     {result.get('posts_fetched', 0)}")
        print(f"  📋 History written:   {result.get('history_written', 0)} rows")
        print(f"  📊 Metrics written:   {result.get('metrics_written', 0)} rows")
        print(f"  💬 Comments fetched:  {result.get('comments_fetched', 0)}")
        if result.get("error"):
            print(f"  ⚠️  Error: {result['error']}")

    return 0 if result["status"] == "ok" else 1
