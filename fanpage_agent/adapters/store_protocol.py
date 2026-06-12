"""Shared store contract for the three backends (sqlite / local CSV / Google Sheets).

The backends grew identical method sets with no common type — adding a
method meant editing three files and hoping; ``scheduled-publish`` even
crashed on sqlite because it reached for a LocalSheetStore-private method.
These Protocols pin the shared surface so drift fails the contract test in
``tests/test_store_factory.py`` instead of production.

``@runtime_checkable`` allows ``isinstance(store, FanpageStore)`` — purely
additive typing, no inheritance changes to any backend. Method signatures
mirror UnifiedStore (the canonical backend). ``runtime_checkable`` only
verifies method NAMES at isinstance-time; signatures are enforced by the
type checker.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fanpage_agent.models import (
    CommunityTriageItem,
    PostHistoryEntry,
    PostMetric,
    WeeklyPlan,
)


@runtime_checkable
class CalendarStore(Protocol):
    """Content calendar lifecycle: plan → approve/reject → publish → metrics."""

    def append_plan(self, brand_id: str, plan: WeeklyPlan) -> None: ...

    def list_calendar_items(
        self,
        brand_id: str | None = None,
        status: str | None = None,
        approval_status: str | None = None,
        date: str | None = None,
        metrics_pending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, str]]: ...

    def approve_calendar_item(
        self,
        calendar_id: str,
        approved_by: str,
        final_caption_ref: str,
        approved_at: str,
    ) -> dict[str, str]: ...

    def reject_calendar_item(
        self, calendar_id: str, reason: str, rejected_at: str,
    ) -> dict[str, str]: ...

    def publish_calendar_item(
        self,
        calendar_id: str,
        published_at: str,
        permalink: str,
        reach: int = 0,
        engagement_rate: float = 0.0,
    ) -> dict[str, str]: ...

    def attach_draft_caption_ref(
        self, calendar_id: str, caption_ref: str, updated_at: str,
    ) -> dict[str, str]: ...

    def record_post_metrics(
        self,
        calendar_id: str,
        reach: int,
        engagements: int,
        leads: int,
        recorded_at: str,
    ) -> dict[str, dict[str, str]]: ...

    def read_post_history(self, limit: int = 30) -> list[PostHistoryEntry]: ...

    def read_post_metrics(self) -> list[PostMetric]: ...

    def record_hashtag_usage(
        self,
        calendar_id: str,
        brand_id: str,
        hashtags: list[str],
        topic: str = "",
        reach: int = 0,
        engagements: int = 0,
        recorded_at: str | None = None,
    ) -> dict[str, str]: ...


@runtime_checkable
class TriageStore(Protocol):
    """Community triage lifecycle: upsert → approve/reject reply → sent/resolved."""

    def list_triage_items(
        self,
        status: str | None = None,
        priority: str | None = None,
        assigned_to: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]: ...

    def upsert_triage_items(
        self, brand_id: str, items: list[CommunityTriageItem],
    ) -> list[dict[str, str]]: ...

    def approve_triage_reply(
        self, triage_id: str, approved_by: str, approved_at: str,
        assigned_to: str = "",
    ) -> dict[str, str]: ...

    def reject_triage_reply(
        self, triage_id: str, reason: str, rejected_at: str,
        assigned_to: str = "",
    ) -> dict[str, str]: ...

    def resolve_triage_item(
        self, triage_id: str, resolved_at: str, assigned_to: str = "",
    ) -> dict[str, str]: ...

    def reopen_triage_item(
        self, triage_id: str, reopened_at: str, assigned_to: str = "",
    ) -> dict[str, str]: ...

    def mark_triage_reply_sent(
        self, triage_id: str, sent_at: str, reply_permalink: str,
        assigned_to: str = "",
    ) -> dict[str, str]: ...


@runtime_checkable
class FanpageStore(CalendarStore, TriageStore, Protocol):
    """Full backend contract — every store build_store() returns satisfies this."""
