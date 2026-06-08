from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.adapters.telegram_client import TelegramClient
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.main import (
    DEFAULT_CALENDAR_FILE,
    DEFAULT_CAMPAIGN_FILE,
    DEFAULT_COMMENT_FILE,
    DEFAULT_HERMES_CRON_JOBS_FILE,
    DEFAULT_HERMES_SCRIPTS_DIR,
    DEFAULT_HISTORY_FILE,
    DEFAULT_METRICS_FILE,
    EXPECTED_HERMES_CRON_JOBS,
    OPS_ARTIFACT_FRESHNESS_HOURS,
    ROOT_DIR,
    add_store_backend_arg,
)
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer
from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.tools.analytics.analytics_dashboard import AnalyticsDashboardTool
from fanpage_agent.tools.analytics.evals import EvalTool
from fanpage_agent.tools.content.hashtag import HashtagTool
from fanpage_agent.tools.data.metrics_auto_fetch import MetricsAutoFetchTool
from fanpage_agent.tools.publishing.telegram_formatter import TelegramFormatterTool
from fanpage_agent.utils import dump_json


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    ops_status_parser = subparsers.add_parser("ops-status")
    ops_status_parser.add_argument(
        "--max-age-hours",
        action="append",
        default=[],
        help="Override freshness threshold, e.g. operator_digest=24 or operator_digest=24,weekly_report=192.",
    )
    ops_status_parser.add_argument(
        "--now",
        help="Timestamp used for freshness checks. Accepts ISO-8601 or Unix epoch seconds. Defaults to current time.",
    )
    ops_status_parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Return exit code 1 when any existing artifact is stale.",
    )
    ops_status_parser.set_defaults(_handler=cmd_ops_status)

    hermes_cron_parser = subparsers.add_parser("hermes-cron-status")
    hermes_cron_parser.add_argument("--jobs-file", default=str(DEFAULT_HERMES_CRON_JOBS_FILE))
    hermes_cron_parser.add_argument("--scripts-dir", default=str(DEFAULT_HERMES_SCRIPTS_DIR))
    hermes_cron_parser.add_argument("--workdir", default=str(ROOT_DIR))
    hermes_cron_parser.set_defaults(_handler=cmd_hermes_cron_status)

    telegram_parser = subparsers.add_parser("preview-telegram")
    telegram_parser.add_argument("--artifact-type", required=True, choices=["plan", "caption", "report", "triage", "approved_replies", "approval", "approval_audit", "metrics", "operator", "research"])
    telegram_parser.add_argument("--input-file", required=True)
    telegram_parser.set_defaults(_handler=cmd_preview_telegram)

    telegram_send_parser = subparsers.add_parser("send-telegram-preview")
    telegram_send_parser.add_argument("--artifact-type", required=True, choices=["plan", "caption", "report", "triage", "approved_replies", "approval", "approval_audit", "metrics", "operator", "research"])
    telegram_send_parser.add_argument("--input-file", required=True)
    telegram_send_parser.add_argument("--chat-id")
    telegram_send_parser.set_defaults(_handler=cmd_send_telegram_preview)

    research_trends_parser = subparsers.add_parser("research-trends")
    research_trends_parser.add_argument("--timeout", type=int, default=30, help="Timeout per request (sec)")
    research_trends_parser.add_argument("--tldr", action="store_true", help="Only print summary (no full report)")
    research_trends_parser.add_argument("--save", action="store_true", help="Save report to JSON")
    research_trends_parser.set_defaults(_handler=cmd_research_trends)

    hashtag_parser = subparsers.add_parser("generate-hashtags")
    hashtag_parser.add_argument("--brand-file", required=True)
    hashtag_parser.add_argument("--topic", required=True)
    hashtag_parser.add_argument("--pillar", required=True)
    hashtag_parser.add_argument("--objective", default="engagement")
    hashtag_parser.add_argument("--angle", default="")
    hashtag_parser.add_argument("--brand-id", default="", help="Override brand_id if brand file has multiple")
    hashtag_parser.add_argument("--no-llm", action="store_true", help="Use rule-based fallback only")
    hashtag_parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted text")
    hashtag_parser.set_defaults(_handler=cmd_generate_hashtags)

    metrics_fetch_parser = subparsers.add_parser("auto-fetch-metrics")
    metrics_fetch_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    metrics_fetch_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    metrics_fetch_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    metrics_fetch_parser.add_argument("--days-back", type=int, default=30, help="Process items within this many days")
    metrics_fetch_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    add_store_backend_arg(metrics_fetch_parser)
    metrics_fetch_parser.set_defaults(_handler=cmd_auto_fetch_metrics)

    fb_comment_parser = subparsers.add_parser("fetch-fb-comments")
    fb_comment_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    fb_comment_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    fb_comment_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    fb_comment_parser.add_argument("--post-limit", type=int, default=10, help="Max recent posts to scan")
    fb_comment_parser.add_argument("--comment-limit", type=int, default=50, help="Max comments per post")
    fb_comment_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    fb_comment_parser.set_defaults(_handler=cmd_fetch_fb_comments)

    eval_parser = subparsers.add_parser("eval-all")
    eval_parser.add_argument("--brand-file", required=True)
    eval_parser.add_argument("--start-date", default="2026-06-20")
    eval_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    eval_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    eval_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    eval_parser.add_argument("--comment-file", default=str(DEFAULT_COMMENT_FILE))
    eval_parser.add_argument("--campaign-file", default=str(DEFAULT_CAMPAIGN_FILE))
    eval_parser.add_argument("--save", action="store_true")
    add_store_backend_arg(eval_parser)
    eval_parser.set_defaults(_handler=cmd_eval_all)

    dashboard_parser = subparsers.add_parser("generate-dashboard")
    dashboard_parser.add_argument("--brand-file", default=str(ROOT_DIR / "data" / "brand_profile.json"))
    dashboard_parser.add_argument("--calendar-file", default=str(DEFAULT_CALENDAR_FILE))
    dashboard_parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    dashboard_parser.add_argument("--metrics-file", default=str(DEFAULT_METRICS_FILE))
    dashboard_parser.add_argument("--days", type=int, default=7)
    dashboard_parser.add_argument("--save", action="store_true", help="Save dashboard HTML to artifacts")
    add_store_backend_arg(dashboard_parser)
    dashboard_parser.set_defaults(_handler=cmd_generate_dashboard)


# ── ops-status helpers ────────────────────────────────────────────────

def _parse_timestamp(raw: str | None) -> float:
    if not raw:
        return time.time()
    try:
        return float(raw)
    except ValueError:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()


def _parse_freshness_thresholds(overrides: list[str] | None = None) -> dict[str, float]:
    thresholds = dict(OPS_ARTIFACT_FRESHNESS_HOURS)
    for raw in overrides or []:
        for pair in raw.split(","):
            if not pair.strip():
                continue
            if "=" not in pair:
                raise ValueError(f"Invalid --max-age-hours value: {pair!r}. Expected name=hours.")
            name, hours = pair.split("=", 1)
            artifact_name = name.strip()
            if artifact_name not in thresholds:
                raise ValueError(
                    f"Unknown artifact for --max-age-hours: {artifact_name!r}. "
                    f"Expected one of: {', '.join(sorted(thresholds))}."
                )
            thresholds[artifact_name] = float(hours.strip())
    return thresholds


def _artifact_status(name: str, path: Path, *, now_timestamp: float, max_age_hours: float) -> dict:
    status = {
        "name": name,
        "path": str(path),
        "exists": path.exists(),
        "freshness": {
            "max_age_hours": max_age_hours,
        },
    }
    if not path.exists():
        status["freshness"].update({"stale": False, "reason": "missing"})
        return status
    stat = path.stat()
    age_hours = max(0.0, (now_timestamp - stat.st_mtime) / 3600)
    status["size_bytes"] = stat.st_size
    status["modified_at"] = stat.st_mtime
    status["freshness"].update(
        {
            "age_hours": round(age_hours, 3),
            "stale": age_hours > max_age_hours,
        }
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        status["json_valid"] = False
        return status
    status["json_valid"] = True
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        status["summary"] = payload["summary"]
    if isinstance(payload, dict) and isinstance(payload.get("delivery"), dict):
        delivery = payload["delivery"]
        status["delivery"] = {
            "sent_count": delivery.get("sent_count"),
            "skipped": delivery.get("skipped", False),
            "reason": delivery.get("reason", ""),
        }
    return status


def _latest_artifact(
    name: str,
    directory: Path,
    pattern: str,
    *,
    now_timestamp: float,
    max_age_hours: float,
) -> dict:
    matches = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    if not matches:
        return {
            "name": name,
            "path": str(directory / pattern),
            "exists": False,
            "freshness": {
                "max_age_hours": max_age_hours,
                "stale": False,
                "reason": "missing",
            },
        }
    return _artifact_status(name, matches[0], now_timestamp=now_timestamp, max_age_hours=max_age_hours)


def build_ops_status_payload(
    settings: Settings,
    *,
    now_timestamp: float | None = None,
    freshness_thresholds: dict[str, float] | None = None,
) -> dict:
    now = time.time() if now_timestamp is None else now_timestamp
    thresholds = freshness_thresholds or dict(OPS_ARTIFACT_FRESHNESS_HOURS)
    artifacts = [
        _latest_artifact(
            "daily_ops_latest",
            settings.artifacts_dir / "ops",
            "daily-ops-*.json",
            now_timestamp=now,
            max_age_hours=thresholds["daily_ops_latest"],
        ),
        _artifact_status(
            "operator_digest",
            settings.artifacts_dir / "ops" / "operator-digest.json",
            now_timestamp=now,
            max_age_hours=thresholds["operator_digest"],
        ),
        _artifact_status(
            "approval_audit",
            settings.artifacts_dir / "approvals" / "approval-audit.json",
            now_timestamp=now,
            max_age_hours=thresholds["approval_audit"],
        ),
        _artifact_status(
            "weekly_report",
            settings.artifacts_dir / "reports" / "weekly-report.json",
            now_timestamp=now,
            max_age_hours=thresholds["weekly_report"],
        ),
        _artifact_status(
            "research_brief",
            settings.artifacts_dir / "research" / "research-brief.json",
            now_timestamp=now,
            max_age_hours=thresholds["research_brief"],
        ),
        _latest_artifact(
            "eval_latest",
            settings.artifacts_dir / "evals",
            "eval-summary-*.json",
            now_timestamp=now,
            max_age_hours=thresholds["eval_latest"],
        ),
    ]
    existing = sum(1 for item in artifacts if item["exists"])
    stale = sum(1 for item in artifacts if item["exists"] and item.get("freshness", {}).get("stale"))
    fresh = sum(1 for item in artifacts if item["exists"] and not item.get("freshness", {}).get("stale"))
    return {
        "artifacts_dir": str(settings.artifacts_dir),
        "freshness_checked_at": now,
        "summary": {
            "existing": existing,
            "missing": len(artifacts) - existing,
            "fresh": fresh,
            "stale": stale,
        },
        "artifacts": artifacts,
    }


# ── hermes-cron-status helpers ────────────────────────────────────────

def _cron_schedule_display(job: dict) -> str:
    if job.get("schedule_display"):
        return str(job["schedule_display"])
    schedule = job.get("schedule")
    if isinstance(schedule, dict):
        return str(schedule.get("display") or schedule.get("expr") or "")
    return str(schedule or "")


def _load_hermes_jobs(jobs_file: Path) -> list[dict]:
    if not jobs_file.exists():
        return []
    payload = json.loads(jobs_file.read_text(encoding="utf-8"))
    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        return []
    return [job for job in jobs if isinstance(job, dict)]


def _check_wrapper(wrapper_path: Path, project_script: str) -> dict:
    status = {
        "path": str(wrapper_path),
        "exists": wrapper_path.exists(),
        "executable": wrapper_path.exists() and wrapper_path.stat().st_mode & 0o111 != 0,
        "targets_project_script": False,
    }
    if wrapper_path.exists():
        text = wrapper_path.read_text(encoding="utf-8")
        status["targets_project_script"] = project_script in text
    return status


def build_hermes_cron_status_payload(jobs_file: Path, scripts_dir: Path, expected_workdir: str) -> dict:
    jobs = _load_hermes_jobs(jobs_file)
    jobs_by_name = {str(job.get("name", "")): job for job in jobs}
    checks = []
    for name, expected in EXPECTED_HERMES_CRON_JOBS.items():
        job = jobs_by_name.get(name)
        wrapper = _check_wrapper(scripts_dir / expected["script"], expected["project_script"])
        errors: list[str] = []
        if job is None:
            errors.append("missing_job")
            actual = {}
        else:
            actual = {
                "job_id": job.get("id") or job.get("job_id"),
                "schedule": _cron_schedule_display(job),
                "script": job.get("script"),
                "no_agent": job.get("no_agent"),
                "deliver": job.get("deliver"),
                "workdir": job.get("workdir"),
                "enabled": job.get("enabled"),
                "state": job.get("state"),
                "last_status": job.get("last_status"),
                "last_delivery_error": job.get("last_delivery_error"),
            }
            if actual["schedule"] != expected["schedule"]:
                errors.append("wrong_schedule")
            if actual["script"] != expected["script"]:
                errors.append("wrong_script")
            if actual["no_agent"] is not True:
                errors.append("not_no_agent")
            if actual["deliver"] != "local":
                errors.append("wrong_deliver")
            if actual["workdir"] != expected_workdir:
                errors.append("wrong_workdir")
            if actual["enabled"] is not True:
                errors.append("not_enabled")
            if actual["last_delivery_error"]:
                errors.append("last_delivery_error")
        if not wrapper["exists"]:
            errors.append("missing_wrapper")
        if wrapper["exists"] and not wrapper["executable"]:
            errors.append("wrapper_not_executable")
        if wrapper["exists"] and not wrapper["targets_project_script"]:
            errors.append("wrapper_wrong_target")
        checks.append({
            "name": name,
            "expected": expected,
            "actual": actual,
            "wrapper": wrapper,
            "ok": not errors,
            "errors": errors,
        })
    ok_count = sum(1 for item in checks if item["ok"])
    return {
        "jobs_file": str(jobs_file),
        "jobs_file_exists": jobs_file.exists(),
        "scripts_dir": str(scripts_dir),
        "expected_workdir": expected_workdir,
        "summary": {
            "expected": len(EXPECTED_HERMES_CRON_JOBS),
            "configured": sum(1 for item in checks if item["actual"]),
            "ok": ok_count,
            "failed": len(checks) - ok_count,
        },
        "checks": checks,
    }


# ── telegram preview helpers ──────────────────────────────────────────

def render_telegram_preview(artifact_type: str, input_file: str) -> str:
    payload = json.loads(Path(input_file).read_text(encoding="utf-8"))
    formatter = TelegramFormatterTool()
    if artifact_type == "plan":
        return formatter.format_weekly_plan(payload)
    if artifact_type == "caption":
        return formatter.format_caption_package(payload)
    if artifact_type == "report":
        return formatter.format_weekly_report(payload)
    if artifact_type == "triage":
        return formatter.format_community_triage(payload)
    if artifact_type == "approved_replies":
        return formatter.format_approved_triage_replies(payload)
    if artifact_type == "approval":
        return formatter.format_approval_queue(payload)
    if artifact_type == "approval_audit":
        return formatter.format_approval_audit(payload)
    if artifact_type == "metrics":
        return formatter.format_metrics_backlog(payload)
    if artifact_type == "operator":
        return formatter.format_operator_digest(payload)
    if artifact_type == "research":
        return formatter.format_research_brief(payload)
    raise ValueError(f"Unsupported artifact type: {artifact_type}")


# ── command functions ─────────────────────────────────────────────────

def cmd_ops_status(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    try:
        now_timestamp = _parse_timestamp(args.now)
        thresholds = _parse_freshness_thresholds(args.max_age_hours)
    except ValueError as exc:
        raise SystemExit(f"ops-status: {exc}") from exc
    payload = build_ops_status_payload(settings, now_timestamp=now_timestamp, freshness_thresholds=thresholds)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if args.fail_on_stale and payload["summary"]["stale"] else 0


def cmd_hermes_cron_status(args: argparse.Namespace) -> int:
    payload = build_hermes_cron_status_payload(
        jobs_file=Path(args.jobs_file),
        scripts_dir=Path(args.scripts_dir),
        expected_workdir=args.workdir,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["summary"]["failed"] == 0 else 1


def cmd_preview_telegram(args: argparse.Namespace) -> int:
    print(render_telegram_preview(args.artifact_type, args.input_file))
    return 0


def cmd_send_telegram_preview(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    message = render_telegram_preview(args.artifact_type, args.input_file)
    result = TelegramClient(settings).send_message(message, chat_id=args.chat_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
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


def cmd_generate_hashtags(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings) if settings.llm_provider != "mock-local" or not args.no_llm else None
    service = HashtagTool(llm_client=llm_client, settings=settings)

    result = service.generate(
        topic=args.topic,
        pillar=args.pillar,
        objective=args.objective,
        angle=args.angle,
        brand_id=profile.brand_id,
        use_llm=not args.no_llm,
    )

    # Convert to serializable dict
    output = {
        "content_topic": result.content_topic,
        "pillar": result.pillar,
        "objective": result.objective,
        "suggestions": [
            {"tag": s.tag, "tier": s.tier, "relevance_score": s.relevance_score, "reason": s.reason}
            for s in result.suggestions
        ],
        "recommended": result.recommended,
    }

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        formatter = TelegramFormatterTool()
        print(formatter.format_hashtag_set(output))

    return 0


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
    """Fetch real comments from FB API and merge into comment_inbox.csv.

    Get recent published posts → fetch comments → dedup by FB comment id → save.
    """

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
        new_rows.append({
            "id": c.get("id", ""),
            "post_id": c.get("post_id", ""),
            "created_at": c.get("created_time", ""),
            "source": "facebook_comment",
            "message": c.get("message", ""),
        })
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
        dump_json(settings.artifacts_dir / "evals" / f"eval-summary-{args.start_date}.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["summary"]["failed"] == 0 else 1


def cmd_generate_dashboard(args: argparse.Namespace) -> int:

    settings = Settings.from_env(root_dir=ROOT_DIR)
    metrics = build_store(settings=settings, args=args).read_post_metrics()
    svc = AnalyticsDashboardTool(settings.artifacts_dir)
    result = svc.generate(metrics, days=args.days)
    if args.save:
        pass  # already saved in generate()
    print(f"📊 Dashboard saved: {result['path']}")
    print(f"   Period: {args.days}d | Posts: {result['total_posts']} | Reach: {result['total_reach']} | Eng: {result['total_engagements']}")
    return 0
