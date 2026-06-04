"""V2 Store adapter — wraps V1 store (Google Sheets / Local) for V2 agents.

Provides calendar read/write, post history, and triage operations
reusing the V1 store backend.
"""
from __future__ import annotations

from typing import Any

from fanpage_agent.adapters.store_factory import build_store as _build_store
from fanpage_agent_v2.adapters.settings import get_settings


class StoreAdapter:
    """Thin wrapper around V1 store for V2 agents."""

    def __init__(self, backend: str | None = None) -> None:
        settings = get_settings()
        args = _Args()
        if backend:
            args.store_backend = backend
        self._store = _build_store(settings, args=args)

    # ── Calendar ─────────────────────────────────────────────────

    def list_calendar(
        self,
        status: str | None = None,
        limit: int | None = 20,
    ) -> list[dict[str, str]]:
        """List calendar items, optionally filtered by status."""
        # GoogleSheetsStore has list_calendar_items
        method = getattr(self._store, "list_calendar_items", None) or getattr(
            self._store, "list_calendar", None
        )
        if method:
            return method(status=status, limit=limit)
        return []

    def append_plan(self, brand_id: str, plan: Any) -> None:
        """Append a full weekly plan to the calendar."""
        method = getattr(self._store, "append_plan", None)
        if method:
            method(brand_id, plan)

    def publish_calendar_item(
        self, calendar_id: str, published_at: str, permalink: str
    ) -> dict[str, str]:
        """Mark a calendar item as published."""
        method = getattr(self._store, "publish_calendar_item", None)
        if method:
            return method(calendar_id, published_at, permalink)
        return {}

    # ── Post history ─────────────────────────────────────────────

    def read_history(self, limit: int = 20) -> list[Any]:
        """Read post history."""
        method = getattr(self._store, "read_post_history", None) or getattr(
            self._store, "read_history", None
        )
        if method:
            return method(limit=limit)
        return []

    # ── Metrics ──────────────────────────────────────────────────

    def read_metrics(self) -> list[Any]:
        """Read post metrics."""
        method = getattr(self._store, "read_post_metrics", None) or getattr(
            self._store, "read_metrics", None
        )
        if method:
            return method()
        return []

    def record_metrics(
        self,
        calendar_id: str,
        reach: int,
        engagements: int,
        leads: int,
        recorded_at: str,
    ) -> dict[str, Any]:
        """Record metrics for a published post."""
        method = getattr(self._store, "record_post_metrics", None)
        if method:
            return method(calendar_id, reach, engagements, leads, recorded_at)
        return {}

    # ── Triage ───────────────────────────────────────────────────

    def list_triage(
        self,
        status: str | None = None,
        limit: int | None = 20,
    ) -> list[dict[str, str]]:
        """List triage items."""
        method = getattr(self._store, "list_triage_items", None) or getattr(
            self._store, "list_triage", None
        )
        if method:
            return method(status=status, limit=limit)
        return []

    def upsert_triage(self, brand_id: str, items: list[Any]) -> list[dict[str, str]]:
        """Upsert triage items."""
        method = getattr(self._store, "upsert_triage_items", None)
        if method:
            return method(brand_id, items)
        return []


class _Args:
    """Minimal args-like object for store_factory.build_store()."""

    def __init__(self) -> None:
        self.store_backend: str | None = None
        self.calendar_file: str | None = None
        self.history_file: str | None = None
        self.metrics_file: str | None = None
        self.triage_file: str | None = None
        self.hashtag_file: str | None = None
