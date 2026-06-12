from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fanpage_agent.config import Settings

from .parser import (
    ROOT_DIR,
    DEFAULT_HERMES_CRON_JOBS_FILE,
    DEFAULT_HERMES_SCRIPTS_DIR,
    EXPECTED_HERMES_CRON_JOBS,
    OPS_ARTIFACT_FRESHNESS_HOURS,
)


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


def _runtime_check(name: str, ok: bool, reason_codes: list[str], next_step: str, **details: Any) -> dict:
    return {
        "name": name,
        "ok": ok,
        "reason_codes": [] if ok else reason_codes,
        "next_step": "" if ok else next_step,
        **details,
    }


def build_runtime_config_status(settings: Settings) -> dict:
    google_account = Path(settings.google_service_account_file) if settings.google_service_account_file else None
    checks = [
        _runtime_check(
            "telegram_delivery",
            bool(settings.telegram_bot_token and settings.telegram_chat_id),
            ["missing_telegram_bot_token" if not settings.telegram_bot_token else "missing_telegram_chat_id"],
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, then run send-telegram-preview.",
            configured=bool(settings.telegram_bot_token and settings.telegram_chat_id),
            base_url_configured=bool(settings.telegram_base_url),
        ),
        _runtime_check(
            "facebook_publish",
            bool(settings.fb_page_id and settings.fb_page_token),
            ["missing_fb_page_id" if not settings.fb_page_id else "missing_fb_page_token"],
            "Set FB_PAGE_ID and FB_PAGE_TOKEN before enabling publish-post or scheduled-publish.",
            configured=bool(settings.fb_page_id and settings.fb_page_token),
            api_version=settings.fb_api_version,
        ),
        _runtime_check(
            "google_store",
            settings.store_backend != "google"
            or bool(
                settings.google_sheets_id
                and google_account is not None
                and google_account.exists()
            ),
            [
                reason
                for reason, missing in (
                    ("missing_google_sheets_id", not settings.google_sheets_id),
                    ("missing_google_service_account_file", not settings.google_service_account_file),
                    (
                        "google_service_account_file_not_found",
                        bool(google_account is not None and not google_account.exists()),
                    ),
                )
                if missing
            ],
            "Use --store-backend local for pilot, or configure Google Sheets ID and service account file.",
            store_backend=settings.store_backend,
            service_account_file_configured=bool(settings.google_service_account_file),
            service_account_file_exists=bool(google_account is not None and google_account.exists()),
        ),
        _runtime_check(
            "llm_generation",
            settings.llm_provider == "mock-local" or bool(settings.llm_api_key),
            ["missing_llm_api_key"],
            "Set LLM_API_KEY for non-mock providers, or use LLM_PROVIDER=mock-local for dry runs.",
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key_configured=bool(settings.llm_api_key),
        ),
        _runtime_check(
            "artifacts_dir",
            settings.artifacts_dir.exists() and os.access(settings.artifacts_dir, os.W_OK),
            [
                "artifacts_dir_missing"
                if not settings.artifacts_dir.exists()
                else "artifacts_dir_not_writable"
            ],
            "Create ARTIFACTS_DIR and ensure the agent can write artifacts there.",
            path=str(settings.artifacts_dir),
            exists=settings.artifacts_dir.exists(),
            writable=settings.artifacts_dir.exists() and os.access(settings.artifacts_dir, os.W_OK),
        ),
    ]
    ok_count = sum(1 for item in checks if item["ok"])
    failed = [item for item in checks if not item["ok"]]
    return {
        "summary": {
            "checks": len(checks),
            "ok": ok_count,
            "failed": len(failed),
        },
        "checks": checks,
    }


def build_ops_status_payload(
    settings: Settings,
    *,
    now_timestamp: float | None = None,
    freshness_thresholds: dict[str, float] | None = None,
    include_cron: bool = False,
    cron_jobs_file: Path | None = None,
    cron_scripts_dir: Path | None = None,
    cron_workdir: str | None = None,
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
    runtime_config = build_runtime_config_status(settings)
    cron_status = None
    cron_failed = 0
    if include_cron:
        cron_status = build_hermes_cron_status_payload(
            jobs_file=cron_jobs_file or DEFAULT_HERMES_CRON_JOBS_FILE,
            scripts_dir=cron_scripts_dir or DEFAULT_HERMES_SCRIPTS_DIR,
            expected_workdir=cron_workdir or str(ROOT_DIR),
        )
        cron_failed = cron_status["summary"]["failed"]
    payload = {
        "artifacts_dir": str(settings.artifacts_dir),
        "freshness_checked_at": now,
        "summary": {
            "existing": existing,
            "missing": len(artifacts) - existing,
            "fresh": fresh,
            "stale": stale,
            "runtime_failed": runtime_config["summary"]["failed"],
            "cron_failed": cron_failed,
        },
        "artifacts": artifacts,
        "runtime_config": runtime_config,
    }
    if cron_status is not None:
        payload["cron"] = cron_status
    return payload


def cmd_ops_status(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    try:
        now_timestamp = _parse_timestamp(args.now)
        thresholds = _parse_freshness_thresholds(args.max_age_hours)
    except ValueError as exc:
        raise SystemExit(f"ops-status: {exc}") from exc
    payload = build_ops_status_payload(
        settings,
        now_timestamp=now_timestamp,
        freshness_thresholds=thresholds,
        include_cron=args.include_cron,
        cron_jobs_file=Path(args.cron_jobs_file),
        cron_scripts_dir=Path(args.cron_scripts_dir),
        cron_workdir=args.cron_workdir,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.fail_on_stale and payload["summary"]["stale"]:
        return 1
    if args.fail_on_runtime and payload["summary"]["runtime_failed"]:
        return 1
    if args.fail_on_cron and payload["summary"].get("cron_failed", 0):
        return 1
    return 0


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
        # Windows has no exec bit — existence is the strongest check there.
        "executable": wrapper_path.exists()
        and (os.name == "nt" or wrapper_path.stat().st_mode & 0o111 != 0),
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


def cmd_hermes_cron_status(args: argparse.Namespace) -> int:
    payload = build_hermes_cron_status_payload(
        jobs_file=Path(args.jobs_file),
        scripts_dir=Path(args.scripts_dir),
        expected_workdir=args.workdir,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["summary"]["failed"] == 0 else 1
