from __future__ import annotations

from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.config import Settings
from fanpage_agent.models import CommunityTriageItem, PostHistoryEntry, PostMetric, WeeklyPlan


class GoogleSheetsStore:
    METRICS_HEADERS = ["published_at", "topic", "pillar", "objective", "reach", "engagements", "leads"]

    def __init__(self, settings: Settings, service: Any | None = None) -> None:
        if not settings.google_sheets_id:
            raise RuntimeError("GOOGLE_SHEETS_ID is required for google store backend")
        if not settings.google_service_account_file:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE is required for google store backend")
        self.settings = settings
        self.spreadsheet_id = settings.google_sheets_id
        self.tabs_prefix = settings.google_sheets_tabs_prefix.strip()
        self.service = service or self._build_service(settings.google_service_account_file)

    def append_plan(self, brand_id: str, plan: WeeklyPlan) -> None:
        headers = LocalSheetStore.HEADERS
        rows: list[list[str]] = []
        for index, day in enumerate(plan.days, start=1):
            row = {
                "brand_id": brand_id,
                "calendar_id": f"{plan.plan_title}-{index}",
                "date": day.date,
                "pillar": day.pillar,
                "objective": day.objective,
                "topic": day.topic,
                "angle": day.angle,
                "format": day.format,
                "hook": day.hook,
                "cta": day.cta,
                "visual_brief": day.visual_brief,
                "status": "planned",
                "approval_status": "pending",
                "approved_by": "",
                "final_caption_ref": "",
                "draft_caption_ref": "",
                "campaign_tag": "",
                "notes": "",
                "last_updated": day.date,
                "published_at": "",
                "permalink": "",
                "reach": "0",
                "engagement_rate": "0.0",
            }
            rows.append([row.get(header, "") for header in headers])
        self._ensure_headers(self._tab_name("content_calendar"), headers)
        self._append_rows(self._tab_name("content_calendar"), rows)

    def approve_calendar_item(
        self,
        calendar_id: str,
        approved_by: str,
        final_caption_ref: str,
        approved_at: str,
    ) -> dict[str, str]:
        rows, row_number = self._find_calendar_row(calendar_id)
        row = rows[row_number - 2]
        row["approval_status"] = "approved"
        row["approved_by"] = approved_by
        row["final_caption_ref"] = final_caption_ref
        row["status"] = "approved"
        row["last_updated"] = approved_at
        self._update_calendar_row(row_number, row)
        return row

    def reject_calendar_item(self, calendar_id: str, reason: str, rejected_at: str) -> dict[str, str]:
        rows, row_number = self._find_calendar_row(calendar_id)
        row = rows[row_number - 2]
        row["approval_status"] = "rejected"
        row["status"] = "needs_revision"
        row["notes"] = reason
        row["last_updated"] = rejected_at
        self._update_calendar_row(row_number, row)
        return row

    def publish_calendar_item(
        self,
        calendar_id: str,
        published_at: str,
        permalink: str,
        reach: int = 0,
        engagement_rate: float = 0.0,
    ) -> dict[str, str]:
        rows, row_number = self._find_calendar_row(calendar_id)
        row = rows[row_number - 2]
        row["status"] = "published"
        row["published_at"] = published_at
        row["permalink"] = permalink
        row["reach"] = str(reach)
        row["engagement_rate"] = str(engagement_rate)
        row["last_updated"] = published_at
        self._update_calendar_row(row_number, row)
        self._append_history_entry(row)
        return row

    def attach_draft_caption_ref(self, calendar_id: str, caption_ref: str, updated_at: str) -> dict[str, str]:
        rows, row_number = self._find_calendar_row(calendar_id)
        row = rows[row_number - 2]
        row["draft_caption_ref"] = caption_ref
        row["last_updated"] = updated_at
        self._update_calendar_row(row_number, row)
        return row

    def record_post_metrics(
        self,
        calendar_id: str,
        reach: int,
        engagements: int,
        leads: int,
        recorded_at: str,
    ) -> dict[str, dict[str, str]]:
        rows, row_number = self._find_calendar_row(calendar_id)
        row = rows[row_number - 2]
        engagement_rate = round((engagements / reach), 2) if reach > 0 else 0.0
        row["reach"] = str(reach)
        row["engagement_rate"] = str(engagement_rate)
        row["last_updated"] = recorded_at
        self._update_calendar_row(row_number, row)

        metric_row = {
            "published_at": row.get("published_at", ""),
            "topic": row.get("topic", ""),
            "pillar": row.get("pillar", ""),
            "objective": row.get("objective", ""),
            "reach": str(reach),
            "engagements": str(engagements),
            "leads": str(leads),
        }
        metric_rows = self._read_tab_as_dicts(self._tab_name("post_metrics"), self.METRICS_HEADERS)
        updated = False
        for existing in metric_rows:
            if existing.get("published_at") == metric_row["published_at"] and existing.get("topic") == metric_row["topic"]:
                existing.update(metric_row)
                updated = True
                break
        if not updated:
            metric_rows.append(metric_row)
        self._replace_tab_rows(self._tab_name("post_metrics"), self.METRICS_HEADERS, metric_rows)
        return {
            "calendar": row,
            "metric": metric_row,
        }

    def list_calendar_items(
        self,
        status: str | None = None,
        approval_status: str | None = None,
        date: str | None = None,
        metrics_pending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        rows = self._read_tab_as_dicts(self._tab_name("content_calendar"), LocalSheetStore.HEADERS)
        filtered = [
            row
            for row in rows
            if (not status or row.get("status") == status)
            and (not approval_status or row.get("approval_status") == approval_status)
            and (not date or row.get("date") == date)
            and (not metrics_pending or self._is_metrics_pending_row(row))
        ]
        if limit is not None:
            return filtered[:limit]
        return filtered

    def read_post_history(self, limit: int = 30) -> list[PostHistoryEntry]:
        rows = self._read_tab_as_dicts(self._tab_name("post_history"), LocalSheetStore.HISTORY_HEADERS)
        selected = rows[-limit:]
        return [
            PostHistoryEntry(
                published_at=row.get("published_at", ""),
                topic=row.get("topic", ""),
                hook=row.get("hook", ""),
                pillar=row.get("pillar", ""),
                objective=row.get("objective", ""),
                permalink=row.get("permalink", ""),
                reach=int(row.get("reach", 0) or 0),
                engagement_rate=float(row.get("engagement_rate", 0.0) or 0.0),
            )
            for row in selected
        ]

    def read_post_metrics(self) -> list[PostMetric]:
        rows = self._read_tab_as_dicts(self._tab_name("post_metrics"), self.METRICS_HEADERS)
        return [
            PostMetric(
                published_at=row.get("published_at", ""),
                topic=row.get("topic", ""),
                pillar=row.get("pillar", ""),
                objective=row.get("objective", ""),
                reach=int(row.get("reach", 0) or 0),
                engagements=int(row.get("engagements", 0) or 0),
                leads=int(row.get("leads", 0) or 0),
            )
            for row in rows
        ]

    def upsert_triage_items(self, brand_id: str, items: list[CommunityTriageItem]) -> list[dict[str, str]]:
        tab_name = self._tab_name("comment_triage")
        headers = LocalSheetStore.TRIAGE_HEADERS
        self._ensure_headers(tab_name, headers)
        existing_rows = self._read_tab_as_dicts(tab_name, headers)
        by_id = {row.get("triage_id"): row for row in existing_rows}
        persisted: list[dict[str, str]] = []
        for item in items:
            existing = by_id.get(item.triage_id, {})
            row = {
                "triage_id": item.triage_id,
                "brand_id": brand_id,
                "created_at": item.created_at,
                "source": item.source,
                "message": item.message,
                "category": item.category,
                "priority": item.priority,
                "recommended_action": item.recommended_action,
                "draft_reply": item.draft_reply,
                "escalation_required": str(item.escalation_required).lower(),
                "requires_human_approval": str(item.requires_human_approval).lower(),
                "matched_rules": "|".join(item.matched_rules),
                "status": existing.get("status", "new") or "new",
                "assigned_to": existing.get("assigned_to", ""),
                "approved_by": existing.get("approved_by", ""),
                "rejected_reason": existing.get("rejected_reason", ""),
                "reply_sent_at": existing.get("reply_sent_at", ""),
                "reply_permalink": existing.get("reply_permalink", ""),
                "resolved_at": existing.get("resolved_at", ""),
                "last_updated": existing.get("last_updated", item.created_at) or item.created_at,
            }
            by_id[item.triage_id] = row
            persisted.append(row)
        all_rows = [by_id[key] for key in by_id]
        self._replace_tab_rows(tab_name, headers, all_rows)
        return persisted

    def approve_triage_reply(
        self,
        triage_id: str,
        approved_by: str,
        approved_at: str,
        assigned_to: str = "",
    ) -> dict[str, str]:
        rows, row_number = self._find_triage_row(triage_id)
        row = rows[row_number - 2]
        row["status"] = "approved"
        row["approved_by"] = approved_by
        row["assigned_to"] = assigned_to or row.get("assigned_to", "")
        row["last_updated"] = approved_at
        self._update_triage_row(row_number, row)
        return row

    def reject_triage_reply(
        self,
        triage_id: str,
        reason: str,
        rejected_at: str,
        assigned_to: str = "",
    ) -> dict[str, str]:
        rows, row_number = self._find_triage_row(triage_id)
        row = rows[row_number - 2]
        row["status"] = "needs_revision"
        row["rejected_reason"] = reason
        row["assigned_to"] = assigned_to or row.get("assigned_to", "")
        row["last_updated"] = rejected_at
        self._update_triage_row(row_number, row)
        return row

    def resolve_triage_item(self, triage_id: str, resolved_at: str, assigned_to: str = "") -> dict[str, str]:
        rows, row_number = self._find_triage_row(triage_id)
        row = rows[row_number - 2]
        row["status"] = "resolved"
        row["resolved_at"] = resolved_at
        row["assigned_to"] = assigned_to or row.get("assigned_to", "")
        row["last_updated"] = resolved_at
        self._update_triage_row(row_number, row)
        return row

    def mark_triage_reply_sent(
        self,
        triage_id: str,
        sent_at: str,
        reply_permalink: str,
        assigned_to: str = "",
    ) -> dict[str, str]:
        rows, row_number = self._find_triage_row(triage_id)
        row = rows[row_number - 2]
        row["status"] = "replied"
        row["reply_sent_at"] = sent_at
        row["reply_permalink"] = reply_permalink
        row["assigned_to"] = assigned_to or row.get("assigned_to", "")
        row["last_updated"] = sent_at
        self._update_triage_row(row_number, row)
        return row

    def reopen_triage_item(self, triage_id: str, reopened_at: str, assigned_to: str = "") -> dict[str, str]:
        rows, row_number = self._find_triage_row(triage_id)
        row = rows[row_number - 2]
        row["status"] = "reopened"
        row["resolved_at"] = ""
        row["assigned_to"] = assigned_to or row.get("assigned_to", "")
        row["last_updated"] = reopened_at
        self._update_triage_row(row_number, row)
        return row

    def list_triage_items(
        self,
        status: str | None = None,
        priority: str | None = None,
        assigned_to: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        rows = self._read_tab_as_dicts(self._tab_name("comment_triage"), LocalSheetStore.TRIAGE_HEADERS)
        filtered = [
            row
            for row in rows
            if (not status or row.get("status") == status)
            and (not priority or row.get("priority") == priority)
            and (not assigned_to or row.get("assigned_to") == assigned_to)
        ]
        if limit is not None:
            return filtered[:limit]
        return filtered

    @staticmethod
    def _build_service(service_account_file: str):
        creds_path = Path(service_account_file)
        if not creds_path.exists():
            raise RuntimeError(f"Google service account file not found: {creds_path}")
        credentials = Credentials.from_service_account_file(
            str(creds_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def _tab_name(self, base_name: str) -> str:
        return f"{self.tabs_prefix}_{base_name}" if self.tabs_prefix else base_name

    def _ensure_headers(self, tab_name: str, headers: list[str]) -> None:
        existing = self._get_values(tab_name)
        if existing:
            return
        self._append_rows(tab_name, [headers])

    def _find_calendar_row(self, calendar_id: str) -> tuple[list[dict[str, str]], int]:
        rows = self._read_tab_as_dicts(self._tab_name("content_calendar"), LocalSheetStore.HEADERS)
        for index, row in enumerate(rows, start=2):
            if row.get("calendar_id") == calendar_id:
                return rows, index
        raise KeyError(f"calendar_id not found: {calendar_id}")

    def _find_triage_row(self, triage_id: str) -> tuple[list[dict[str, str]], int]:
        rows = self._read_tab_as_dicts(self._tab_name("comment_triage"), LocalSheetStore.TRIAGE_HEADERS)
        for index, row in enumerate(rows, start=2):
            if row.get("triage_id") == triage_id:
                return rows, index
        raise KeyError(f"triage_id not found: {triage_id}")

    @staticmethod
    def _is_metrics_pending_row(row: dict[str, str]) -> bool:
        if row.get("status") != "published":
            return False
        reach = int(row.get("reach", 0) or 0)
        permalink = str(row.get("permalink", "") or "")
        published_at = str(row.get("published_at", "") or "")
        return reach <= 0 and bool(permalink or published_at)

    def _update_calendar_row(self, row_number: int, row: dict[str, str]) -> None:
        values = [[row.get(header, "") for header in LocalSheetStore.HEADERS]]
        range_name = f"{self._tab_name('content_calendar')}!A{row_number}:W{row_number}"
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    def _update_triage_row(self, row_number: int, row: dict[str, str]) -> None:
        values = [[row.get(header, "") for header in LocalSheetStore.TRIAGE_HEADERS]]
        range_name = f"{self._tab_name('comment_triage')}!A{row_number}:T{row_number}"
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    def _replace_tab_rows(self, tab_name: str, headers: list[str], rows: list[dict[str, str]]) -> None:
        values = [headers] + [[row.get(header, "") for header in headers] for row in rows]
        end_column = chr(ord("A") + max(len(headers) - 1, 0))
        range_name = f"{tab_name}!A1:{end_column}{len(values)}"
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    def _append_history_entry(self, row: dict[str, str]) -> None:
        headers = LocalSheetStore.HISTORY_HEADERS
        self._ensure_headers(self._tab_name("post_history"), headers)
        history_row = [
            row.get("published_at", ""),
            row.get("topic", ""),
            row.get("hook", ""),
            row.get("pillar", ""),
            row.get("objective", ""),
            row.get("permalink", ""),
            row.get("reach", "0"),
            row.get("engagement_rate", "0.0"),
        ]
        self._append_rows(self._tab_name("post_history"), [history_row])

    def _read_tab_as_dicts(self, tab_name: str, headers: list[str]) -> list[dict[str, str]]:
        values = self._get_values(tab_name)
        if not values:
            return []
        header_row = values[0]
        data_rows = values[1:] if header_row == headers else values
        normalized: list[dict[str, str]] = []
        for raw_row in data_rows:
            normalized.append({header: raw_row[index] if index < len(raw_row) else "" for index, header in enumerate(headers)})
        return normalized

    def _get_values(self, tab_name: str) -> list[list[str]]:
        response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{tab_name}!A:Z",
        ).execute()
        return response.get("values", [])

    def _append_rows(self, tab_name: str, rows: list[list[str]]) -> None:
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"{tab_name}!A:Z",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()
