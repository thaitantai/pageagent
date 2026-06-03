from __future__ import annotations

from fanpage_agent.adapters.google_sheets_store import GoogleSheetsStore
from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.config import Settings


def build_store(settings: Settings, args):
    backend = getattr(args, "store_backend", None) or settings.store_backend
    if backend == "local":
        calendar_file = getattr(args, "calendar_file", None) or (settings.artifacts_dir / "_local_store" / "content_calendar.csv")
        history_file = getattr(args, "history_file", None)
        metrics_file = getattr(args, "metrics_file", None)
        triage_file = getattr(args, "triage_file", None)
        hashtag_file = getattr(args, "hashtag_file", None) or (settings.artifacts_dir / "_local_store" / "hashtag_performance.csv")
        return LocalSheetStore(
            calendar_file,
            history_csv=history_file,
            metrics_csv=metrics_file,
            triage_csv=triage_file,
            hashtag_csv=hashtag_file,
        )
    if backend == "google":
        return GoogleSheetsStore(settings=settings)
    raise ValueError(f"Unsupported store backend: {backend}")
