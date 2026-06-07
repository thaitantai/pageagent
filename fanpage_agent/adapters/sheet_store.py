from __future__ import annotations

import csv
from pathlib import Path

from fanpage_agent.models import CommunityTriageItem, PostHistoryEntry, PostMetric, WeeklyPlan


class LocalSheetStore:
    HEADERS = [
        "brand_id",
        "calendar_id",
        "date",
        "pillar",
        "objective",
        "topic",
        "angle",
        "format",
        "hook",
        "cta",
        "visual_brief",
        "status",
        "approval_status",
        "approved_by",
        "final_caption_ref",
        "draft_caption_ref",
        "campaign_tag",
        "notes",
        "last_updated",
        "published_at",
        "permalink",
        "reach",
        "engagement_rate",
    ]
    TRIAGE_HEADERS = [
        "triage_id",
        "brand_id",
        "created_at",
        "source",
        "message",
        "category",
        "priority",
        "recommended_action",
        "draft_reply",
        "escalation_required",
        "requires_human_approval",
        "matched_rules",
        "status",
        "assigned_to",
        "approved_by",
        "rejected_reason",
        "reply_sent_at",
        "reply_permalink",
        "resolved_at",
        "last_updated",
    ]
    HISTORY_HEADERS = [
        "published_at",
        "topic",
        "hook",
        "pillar",
        "objective",
        "permalink",
        "reach",
        "engagement_rate",
    ]
    HASHTAG_HEADERS = [
        "calendar_id",
        "brand_id",
        "topic",
        "hashtags",
        "reach",
        "engagements",
        "recorded_at",
    ]

    def __init__(
        self,
        calendar_csv: str | Path,
        history_csv: str | Path | None = None,
        metrics_csv: str | Path | None = None,
        triage_csv: str | Path | None = None,
        hashtag_csv: str | Path | None = None,
    ) -> None:
        self.calendar_csv = Path(calendar_csv)
        self.history_csv = Path(history_csv) if history_csv else None
        self.metrics_csv = Path(metrics_csv) if metrics_csv else None
        self.triage_csv = Path(triage_csv) if triage_csv else None
        self.hashtag_csv = Path(hashtag_csv) if hashtag_csv else None

    def append_plan(self, brand_id: str, plan: WeeklyPlan) -> None:
        rows: list[dict[str, str]] = []
        for index, day in enumerate(plan.days, start=1):
            rows.append(
                {
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
            )
        existing = self._read_calendar_rows()
        self._write_calendar_rows(existing + rows)

    def approve_calendar_item(
        self,
        calendar_id: str,
        approved_by: str,
        final_caption_ref: str,
        approved_at: str,
    ) -> dict[str, str]:
        rows = self._read_calendar_rows()
        row = self._find_calendar_row(rows, calendar_id)
        row["approval_status"] = "approved"
        row["approved_by"] = approved_by
        row["final_caption_ref"] = final_caption_ref
        row["status"] = "approved"
        row["last_updated"] = approved_at
        self._write_calendar_rows(rows)
        return row

    def _approve_calendar_item(
        self,
        calendar_id: str,
        approved_by: str,
        final_caption_ref: str,
        approved_at: str,
        approval_status: str = "approved",
    ) -> dict[str, str]:
        rows = self._read_calendar_rows()
        row = self._find_calendar_row(rows, calendar_id)
        row["approval_status"] = approval_status
        row["approved_by"] = approved_by
        row["final_caption_ref"] = final_caption_ref
        row["status"] = approval_status
        row["last_updated"] = approved_at
        self._write_calendar_rows(rows)
        return row

    def reject_calendar_item(self, calendar_id: str, reason: str, rejected_at: str) -> dict[str, str]:
        rows = self._read_calendar_rows()
        row = self._find_calendar_row(rows, calendar_id)
        row["approval_status"] = "rejected"
        row["status"] = "needs_revision"
        row["notes"] = reason
        row["last_updated"] = rejected_at
        self._write_calendar_rows(rows)
        return row

    def publish_calendar_item(
        self,
        calendar_id: str,
        published_at: str,
        permalink: str,
        reach: int = 0,
        engagement_rate: float = 0.0,
    ) -> dict[str, str]:
        rows = self._read_calendar_rows()
        row = self._find_calendar_row(rows, calendar_id)
        row["status"] = "published"
        row["published_at"] = published_at
        row["permalink"] = permalink
        row["reach"] = str(reach)
        row["engagement_rate"] = str(engagement_rate)
        row["last_updated"] = published_at
        self._write_calendar_rows(rows)
        self._append_history_entry(row)
        return row

    def attach_draft_caption_ref(self, calendar_id: str, caption_ref: str, updated_at: str) -> dict[str, str]:
        rows = self._read_calendar_rows()
        row = self._find_calendar_row(rows, calendar_id)
        row["draft_caption_ref"] = caption_ref
        row["last_updated"] = updated_at
        self._write_calendar_rows(rows)
        return row

    def record_post_metrics(
        self,
        calendar_id: str,
        reach: int,
        engagements: int,
        leads: int,
        recorded_at: str,
    ) -> dict[str, dict[str, str]]:
        rows = self._read_calendar_rows()
        row = self._find_calendar_row(rows, calendar_id)
        engagement_rate = round((engagements / reach), 2) if reach > 0 else 0.0
        row["reach"] = str(reach)
        row["engagement_rate"] = str(engagement_rate)
        row["last_updated"] = recorded_at
        self._write_calendar_rows(rows)

        metric_row = {
            "published_at": row.get("published_at", ""),
            "topic": row.get("topic", ""),
            "pillar": row.get("pillar", ""),
            "objective": row.get("objective", ""),
            "reach": str(reach),
            "engagements": str(engagements),
            "leads": str(leads),
        }
        metric_rows = self._read_metric_rows()
        updated = False
        for existing in metric_rows:
            if existing.get("published_at") == metric_row["published_at"] and existing.get("topic") == metric_row["topic"]:
                existing.update(metric_row)
                updated = True
                break
        if not updated:
            metric_rows.append(metric_row)
        self._write_metric_rows(metric_rows)
        return {
            "calendar": row,
            "metric": metric_row,
        }

    def list_calendar_items(
        self,
        brand_id: str | None = None,
        status: str | None = None,
        approval_status: str | None = None,
        date: str | None = None,
        metrics_pending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        rows = self._read_calendar_rows()
        filtered = [
            row
            for row in rows
            if (not brand_id or row.get("brand_id") == brand_id)
            and (not status or row.get("status") == status)
            and (not approval_status or row.get("approval_status") == approval_status)
            and (not date or row.get("date") == date)
            and (not metrics_pending or self._is_metrics_pending_row(row))
        ]
        if limit is not None:
            return filtered[:limit]
        return filtered

    def check_calendar_gaps(
        self,
        brand_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        max_gap_days: int = 3,
    ) -> list[dict[str, object]]:
        """Find gaps in the content calendar longer than max_gap_days.

        Returns list of gap dicts with keys: start_date, end_date, gap_days.
        """
        from datetime import date as _date
        from datetime import timedelta

        rows = self._read_calendar_rows()
        if brand_id:
            rows = [r for r in rows if r.get("brand_id") == brand_id]

        today = _date.today()
        start = _date.fromisoformat(start_date) if start_date else today
        end = _date.fromisoformat(end_date) if end_date else today + timedelta(days=14)

        # Collect scheduled dates (planned + approved items only)
        scheduled: set[_date] = set()
        for row in rows:
            if row.get("status") in ("planned", "approved", "published"):
                raw = row.get("date", "")
                if raw:
                    try:
                        scheduled.add(_date.fromisoformat(raw))
                    except ValueError:
                        pass

        gaps: list[dict[str, object]] = []
        gap_start: _date | None = None
        cursor = start
        while cursor <= end:
            if cursor not in scheduled:
                if gap_start is None:
                    gap_start = cursor
            else:
                if gap_start is not None:
                    gap_days = (cursor - gap_start).days
                    if gap_days > max_gap_days:
                        gaps.append({
                            "start_date": gap_start.isoformat(),
                            "end_date": (cursor - timedelta(days=1)).isoformat(),
                            "gap_days": gap_days,
                        })
                    gap_start = None
            cursor += timedelta(days=1)

        # Handle trailing gap
        if gap_start is not None:
            gap_days = (end - gap_start).days + 1
            if gap_days > max_gap_days:
                gaps.append({
                    "start_date": gap_start.isoformat(),
                    "end_date": end.isoformat(),
                    "gap_days": gap_days,
                })

        return gaps

    def read_post_history(self, limit: int = 30) -> list[PostHistoryEntry]:
        if not self.history_csv or not self.history_csv.exists():
            return []
        with self.history_csv.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
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
        if not self.metrics_csv or not self.metrics_csv.exists():
            return []
        with self.metrics_csv.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
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
        rows = self._read_triage_rows()
        by_id = {row.get("triage_id"): row for row in rows}
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
        self._write_triage_rows(list(by_id.values()))
        return persisted

    def approve_triage_reply(
        self,
        triage_id: str,
        approved_by: str,
        approved_at: str,
        assigned_to: str = "",
    ) -> dict[str, str]:
        rows = self._read_triage_rows()
        row = self._find_triage_row(rows, triage_id)
        row["status"] = "approved"
        row["approved_by"] = approved_by
        row["assigned_to"] = assigned_to or row.get("assigned_to", "")
        row["last_updated"] = approved_at
        self._write_triage_rows(rows)
        return row

    def reject_triage_reply(
        self,
        triage_id: str,
        reason: str,
        rejected_at: str,
        assigned_to: str = "",
    ) -> dict[str, str]:
        rows = self._read_triage_rows()
        row = self._find_triage_row(rows, triage_id)
        row["status"] = "needs_revision"
        row["rejected_reason"] = reason
        row["assigned_to"] = assigned_to or row.get("assigned_to", "")
        row["last_updated"] = rejected_at
        self._write_triage_rows(rows)
        return row

    def resolve_triage_item(self, triage_id: str, resolved_at: str, assigned_to: str = "") -> dict[str, str]:
        rows = self._read_triage_rows()
        row = self._find_triage_row(rows, triage_id)
        row["status"] = "resolved"
        row["resolved_at"] = resolved_at
        row["assigned_to"] = assigned_to or row.get("assigned_to", "")
        row["last_updated"] = resolved_at
        self._write_triage_rows(rows)
        return row

    def mark_triage_reply_sent(
        self,
        triage_id: str,
        sent_at: str,
        reply_permalink: str,
        assigned_to: str = "",
    ) -> dict[str, str]:
        rows = self._read_triage_rows()
        row = self._find_triage_row(rows, triage_id)
        row["status"] = "replied"
        row["reply_sent_at"] = sent_at
        row["reply_permalink"] = reply_permalink
        row["assigned_to"] = assigned_to or row.get("assigned_to", "")
        row["last_updated"] = sent_at
        self._write_triage_rows(rows)
        return row

    def reopen_triage_item(self, triage_id: str, reopened_at: str, assigned_to: str = "") -> dict[str, str]:
        rows = self._read_triage_rows()
        row = self._find_triage_row(rows, triage_id)
        row["status"] = "reopened"
        row["resolved_at"] = ""
        row["assigned_to"] = assigned_to or row.get("assigned_to", "")
        row["last_updated"] = reopened_at
        self._write_triage_rows(rows)
        return row

    def list_triage_items(
        self,
        status: str | None = None,
        priority: str | None = None,
        assigned_to: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        rows = self._read_triage_rows()
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

    def record_hashtag_usage(
        self,
        calendar_id: str,
        brand_id: str,
        hashtags: list[str],
        topic: str = "",
        reach: int = 0,
        engagements: int = 0,
        recorded_at: str | None = None,
    ) -> dict[str, str]:
        from datetime import datetime, timezone

        now = recorded_at or datetime.now(timezone.utc).isoformat()
        row = {
            "calendar_id": calendar_id,
            "brand_id": brand_id,
            "topic": topic,
            "hashtags": " ".join(hashtags),
            "reach": str(reach),
            "engagements": str(engagements),
            "recorded_at": now,
        }
        rows = self._read_hashtag_rows()
        rows.append(row)
        self._write_hashtag_rows(rows)
        return row

    def read_hashtag_performance(
        self,
        brand_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        """Aggregate hashtag performance: for each unique hashtag, sum reach/engagements.

        Returns top tags by total reach, descending.
        """
        rows = self._read_hashtag_rows()
        if brand_id:
            rows = [r for r in rows if r.get("brand_id") == brand_id]

        agg: dict[str, dict[str, int]] = {}
        for row in rows:
            tags = row.get("hashtags", "").strip().split()
            r_reach = int(row.get("reach", 0) or 0)
            r_eng = int(row.get("engagements", 0) or 0)
            for tag in tags:
                tag = tag.strip().lower()
                if not tag:
                    continue
                if tag not in agg:
                    agg[tag] = {"reach": 0, "engagements": 0, "post_count": 0}
                agg[tag]["reach"] += r_reach
                agg[tag]["engagements"] += r_eng
                agg[tag]["post_count"] += 1

        sorted_tags = sorted(agg.items(), key=lambda x: x[1]["reach"], reverse=True)
        return [
            {
                "hashtag": tag,
                "total_reach": stats["reach"],
                "total_engagements": stats["engagements"],
                "post_count": stats["post_count"],
            }
            for tag, stats in sorted_tags[:limit]
        ]

    def _read_hashtag_rows(self) -> list[dict[str, str]]:
        if not self.hashtag_csv or not self.hashtag_csv.exists():
            return []
        with self.hashtag_csv.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return [{header: row.get(header, "") for header in self.HASHTAG_HEADERS} for row in rows]

    def _write_hashtag_rows(self, rows: list[dict[str, str]]) -> None:
        if not self.hashtag_csv:
            raise RuntimeError("hashtag_csv is required for hashtag tracking operations")
        self.hashtag_csv.parent.mkdir(parents=True, exist_ok=True)
        with self.hashtag_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.HASHTAG_HEADERS)
            writer.writeheader()
            for row in rows:
                writer.writerow({header: row.get(header, "") for header in self.HASHTAG_HEADERS})

    def _read_calendar_rows(self) -> list[dict[str, str]]:
        if not self.calendar_csv.exists():
            return []
        with self.calendar_csv.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        normalized: list[dict[str, str]] = []
        for row in rows:
            normalized.append({header: row.get(header, "") for header in self.HEADERS})
        return normalized

    def _write_calendar_rows(self, rows: list[dict[str, str]]) -> None:
        self.calendar_csv.parent.mkdir(parents=True, exist_ok=True)
        with self.calendar_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.HEADERS)
            writer.writeheader()
            for row in rows:
                writer.writerow({header: row.get(header, "") for header in self.HEADERS})

    def _read_triage_rows(self) -> list[dict[str, str]]:
        if not self.triage_csv or not self.triage_csv.exists():
            return []
        with self.triage_csv.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return [{header: row.get(header, "") for header in self.TRIAGE_HEADERS} for row in rows]

    def _write_triage_rows(self, rows: list[dict[str, str]]) -> None:
        if not self.triage_csv:
            raise RuntimeError("triage_csv is required for triage state operations")
        self.triage_csv.parent.mkdir(parents=True, exist_ok=True)
        with self.triage_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.TRIAGE_HEADERS)
            writer.writeheader()
            for row in rows:
                writer.writerow({header: row.get(header, "") for header in self.TRIAGE_HEADERS})

    def _read_metric_rows(self) -> list[dict[str, str]]:
        headers = ["published_at", "topic", "pillar", "objective", "reach", "engagements", "leads"]
        if not self.metrics_csv or not self.metrics_csv.exists():
            return []
        with self.metrics_csv.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return [{header: row.get(header, "") for header in headers} for row in rows]

    def _write_metric_rows(self, rows: list[dict[str, str]]) -> None:
        headers = ["published_at", "topic", "pillar", "objective", "reach", "engagements", "leads"]
        if not self.metrics_csv:
            raise RuntimeError("metrics_csv is required for metrics operations")
        self.metrics_csv.parent.mkdir(parents=True, exist_ok=True)
        with self.metrics_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow({header: row.get(header, "") for header in headers})

    @staticmethod
    def _find_triage_row(rows: list[dict[str, str]], triage_id: str) -> dict[str, str]:
        for row in rows:
            if row.get("triage_id") == triage_id:
                return row
        raise ValueError(f"Triage item not found: {triage_id}")

    @staticmethod
    def _is_metrics_pending_row(row: dict[str, str]) -> bool:
        if row.get("status") != "published":
            return False
        reach = int(row.get("reach", 0) or 0)
        permalink = str(row.get("permalink", "") or "")
        published_at = str(row.get("published_at", "") or "")
        return reach <= 0 and bool(permalink or published_at)

    @staticmethod
    def _find_calendar_row(rows: list[dict[str, str]], calendar_id: str) -> dict[str, str]:
        for row in rows:
            if row.get("calendar_id") == calendar_id:
                return row
        raise KeyError(f"calendar_id not found: {calendar_id}")

    def _append_history_entry(self, row: dict[str, str]) -> None:
        if not self.history_csv:
            return
        self.history_csv.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.history_csv.exists()
        with self.history_csv.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.HISTORY_HEADERS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(
                {
                    "published_at": row.get("published_at", ""),
                    "topic": row.get("topic", ""),
                    "hook": row.get("hook", ""),
                    "pillar": row.get("pillar", ""),
                    "objective": row.get("objective", ""),
                    "permalink": row.get("permalink", ""),
                    "reach": row.get("reach", "0"),
                    "engagement_rate": row.get("engagement_rate", "0.0"),
                }
            )
