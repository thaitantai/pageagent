"""Shared helpers for tool implementations."""

from __future__ import annotations

from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.models import BrandProfile

ROOT_DIR = Path(__file__).resolve().parent.parent  # project root
DEFAULT_CALENDAR = ROOT_DIR / "data" / "real" / "content_calendar.csv"
DEFAULT_HISTORY = ROOT_DIR / "data" / "real" / "post_history.csv"
DEFAULT_COMMENT = ROOT_DIR / "data" / "real" / "comment_inbox.csv"
DEFAULT_METRICS = ROOT_DIR / "data" / "real" / "post_metrics.csv"
DEFAULT_BRAND = ROOT_DIR / "data" / "real" / "brand_profile.json"


def settings() -> Settings:
    return Settings.from_env(root_dir=ROOT_DIR)


def local_store() -> LocalSheetStore:
    return LocalSheetStore(
        calendar_csv=DEFAULT_CALENDAR,
        history_csv=DEFAULT_HISTORY,
        metrics_csv=DEFAULT_METRICS,
        triage_csv=DEFAULT_COMMENT,
    )


def profile(s: Settings | None = None) -> BrandProfile:
    s or settings()
    path = DEFAULT_BRAND if DEFAULT_BRAND.exists() else ROOT_DIR / "data" / "sample" / "brand_profile.json"
    if not path.exists():
        raise FileNotFoundError(f"Brand profile not found at {path}")
    return load_brand_profile(path)


def list_calendar_items_summary(store: LocalSheetStore) -> dict:
    items = store.list_calendar_items()
    return {
        "total": len(items),
        "pending_approval": len([i for i in items if i.get("approval_status", "").lower() == "pending"]),
        "approved_ready": len([i for i in items if i.get("approval_status", "").lower() == "approved"]),
        "published": len([i for i in items if i.get("status", "").lower() == "published"]),
    }


def list_triage_items_summary(store: LocalSheetStore) -> dict:
    items = store.list_triage_items()
    return {
        "total": len(items),
        "pending": len([t for t in items if t.get("status", "").lower() == "pending_triage"]),
        "approved": len([t for t in items if t.get("status", "").lower() in ("approved", "reply_approved")]),
        "rejected": len([t for t in items if t.get("status", "").lower() == "rejected"]),
    }
