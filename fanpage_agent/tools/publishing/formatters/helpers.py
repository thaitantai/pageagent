from __future__ import annotations

from datetime import datetime, timezone


class _HelpersMixin:
    """Static/helper methods shared across TelegramFormatterTool domain mixins."""

    @staticmethod
    def _format_verification(verification: dict | None) -> str:
        if not verification:
            return "verification: N/A"
        return "verification: PASS" if verification.get("passed") else "verification: FAIL"

    @staticmethod
    def _caption_action_summary_lines(item: dict) -> list[str]:
        calendar_id = item.get("calendar_id", "") or "<CALENDAR_ID>"
        draft_caption_ref = item.get("draft_caption_ref", "") or "<CAPTION_FILE>"
        return [
            f"approve: python3 -m fanpage_agent.main approve-caption --calendar-id {calendar_id} --caption-file {draft_caption_ref} --approved-by <NAME> --approved-at <ISO_TIME>",
            f"reject: python3 -m fanpage_agent.main reject-caption --calendar-id {calendar_id} --reason <REASON> --rejected-at <ISO_TIME>",
        ]

    @staticmethod
    def _variant_score_lines(item: dict) -> list[str]:
        recommended = item.get("recommended_variant") or {}
        scores = item.get("variant_scores") or []
        if not recommended and not scores:
            return []
        lines = []
        if recommended:
            lines.append(
                f"   recommended variant: {recommended.get('variant_id', '-')} "
                f"(score {recommended.get('score', '-')})"
            )
        if scores:
            compact = ", ".join(
                f"{score.get('variant_id', '-')}: {score.get('score', '-')}"
                for score in scores[:4]
            )
            lines.append(f"   variant scores: {compact}")
        return lines

    @staticmethod
    def _caption_action_lines(item: dict) -> list[str]:
        calendar_id = item.get("calendar_id", "") or "<CALENDAR_ID>"
        draft_caption_ref = item.get("draft_caption_ref", "") or "<CAPTION_FILE>"
        return [
            "   actions:",
            f"   approve: python3 -m fanpage_agent.main approve-caption --calendar-id {calendar_id} --caption-file {draft_caption_ref} --approved-by <NAME> --approved-at <ISO_TIME>",
            f"   reject: python3 -m fanpage_agent.main reject-caption --calendar-id {calendar_id} --reason <REASON> --rejected-at <ISO_TIME>",
        ]

    @staticmethod
    def _parse_now(value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        if isinstance(value, str) and value.strip():
            raw = value.strip()
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return datetime.now(timezone.utc)
        return datetime.now(timezone.utc)

    @staticmethod
    def _created_at_sort_key(created_at: object) -> str:
        # Oldest first; unknown timestamps sink to the end.
        if not isinstance(created_at, str) or not created_at.strip():
            return "9999"
        return created_at

    @staticmethod
    def _age_hours(created_at: object, now: datetime) -> float | None:
        if not isinstance(created_at, str) or not created_at.strip():
            return None
        raw = created_at.strip()
        try:
            created = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                created = datetime.fromisoformat(raw + "T00:00:00+00:00")
            except ValueError:
                return None
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta = now - created
        return delta.total_seconds() / 3600.0

    @staticmethod
    def _triage_action_lines(item: dict) -> list[str]:
        triage_id = item.get("triage_id", "") or "<TRIAGE_ID>"
        status = str(item.get("status", "") or "new")

        if status in {"new", "pending"}:
            return [
                "   actions:",
                f"   approve: python3 -m fanpage_agent.main approve-triage-reply --triage-id {triage_id} --approved-by <NAME> --approved-at <ISO_TIME>",
                f"   reject: python3 -m fanpage_agent.main reject-triage-reply --triage-id {triage_id} --reason <REASON> --rejected-at <ISO_TIME>",
            ]
        if status == "approved":
            return [
                "   after sending:",
                f"   python3 -m fanpage_agent.main mark-triage-reply-sent --triage-id {triage_id} --sent-at <ISO_TIME> --reply-permalink <URL>",
            ]
        if status == "sent":
            return [
                "   after resolved:",
                f"   python3 -m fanpage_agent.main resolve-triage-item --triage-id {triage_id} --resolved-at <ISO_TIME>",
            ]
        return []
