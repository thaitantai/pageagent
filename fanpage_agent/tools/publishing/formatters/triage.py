from __future__ import annotations


class _TriageMixin:
    """Formatters for community triage, approval workflows, and operator digest."""

    def format_community_triage(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        by_category = summary.get("by_category", {})
        by_priority = summary.get("by_priority", {})
        by_status = summary.get("by_status", {})
        items = payload.get("items", [])
        now = self._parse_now(payload.get("now") or payload.get("generated_at"))
        ranked_items = sorted(
            items,
            key=lambda item: (
                {"urgent": 0, "high": 1, "normal": 2, "low": 3}.get(
                    item.get("priority", "normal"), 9
                ),
                self._created_at_sort_key(item.get("created_at")),
                item.get("category", ""),
            ),
        )
        lines = [
            "## Community Triage",
            f"total items: {summary.get('total_items', 0)}",
            f"escalations: {summary.get('escalation_count', 0)}",
            f"approval required: {summary.get('approval_required_count', 0)}",
            "",
            "categories:",
        ]
        lines.extend([f"- {name}: {count}" for name, count in by_category.items()])
        if by_priority:
            lines.append("priorities:")
            lines.extend([f"- {name}: {count}" for name, count in by_priority.items()])
        if by_status:
            lines.append("statuses:")
            lines.extend([f"- {name}: {count}" for name, count in by_status.items()])
        if ranked_items:
            lines.append("")
            lines.append("top items:")
            for index, item in enumerate(ranked_items[:3], start=1):
                age = self._age_hours(item.get("created_at"), now=now)
                age_hint = f" | age: {age:.1f}h" if age is not None else ""
                lines.extend(
                    [
                        f"{index}. [{item.get('priority', '-').upper()}] {item.get('category', '-')} via {item.get('source', '-')}",
                        f"   triage_id: {item.get('triage_id', '-')}",
                        f"   status: {item.get('status', '-')}",
                        f"   assigned_to: {item.get('assigned_to', '-') or '-'}",
                        f"   created_at: {item.get('created_at', '-')}{age_hint}",
                        f"   message: {item.get('message', '-')}",
                        f"   action: {item.get('recommended_action', '-')}",
                        *self._triage_action_lines(item),
                    ]
                )
        return "\n".join(lines).strip()

    def format_approval_queue(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        items = payload.get("items", [])
        lines = [
            "## Approval Queue",
            f"total items: {summary.get('total_items', 0)}",
            "",
        ]
        by_status = summary.get("by_status", {})
        by_approval_status = summary.get("by_approval_status", {})
        by_pillar = summary.get("by_pillar", {})
        if by_status:
            lines.append("statuses:")
            lines.extend([f"- {name}: {count}" for name, count in by_status.items()])
        if by_approval_status:
            lines.append("approval statuses:")
            lines.extend([f"- {name}: {count}" for name, count in by_approval_status.items()])
        if by_pillar:
            lines.append("pillars:")
            lines.extend([f"- {name}: {count}" for name, count in by_pillar.items()])
        if items:
            lines.append("")
            lines.append("top items:")
            for index, item in enumerate(items[:3], start=1):
                lines.extend(
                    [
                        f"{index}. {item.get('date', '-')} — {item.get('topic', '-')}",
                        f"   calendar_id: {item.get('calendar_id', '-')}",
                        f"   status: {item.get('status', '-')} | approval: {item.get('approval_status', '-')}",
                        f"   pillar: {item.get('pillar', '-')}",
                        f"   draft caption: {item.get('draft_caption_ref', '-') or '-'}",
                        *self._variant_score_lines(item),
                        *self._caption_action_lines(item),
                    ]
                )
        return "\n".join(lines).strip()

    def format_approval_audit(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        overdue_items = payload.get("overdue_items", [])
        recent_rejections = payload.get("recent_rejections", [])
        lines = [
            "## Approval Audit",
            f"as of: {summary.get('as_of', '-')} | SLA: {summary.get('sla_days', 0)}d",
            (
                f"overdue pending: {summary.get('overdue_pending', 0)} | "
                f"pending: {summary.get('pending', 0)} | "
                f"approved: {summary.get('approved', 0)} | "
                f"rejected: {summary.get('rejected', 0)}"
            ),
            "Next:",
        ]
        if overdue_items:
            for index, item in enumerate(overdue_items[:3], start=1):
                lines.append(
                    f"{index}. {item.get('calendar_id', '-')} — {item.get('topic', '-')} "
                    f"({item.get('date', '-')}, days pending: {item.get('days_pending', 0)})"
                )
                lines.extend(self._caption_action_summary_lines(item))
        else:
            lines.append("- no overdue captions")
        if recent_rejections:
            rejected = recent_rejections[0]
            lines.append(
                f"Recent rejection: {rejected.get('calendar_id', '-')} — "
                f"{rejected.get('notes', '-') or '-'}"
            )
        return "\n".join(lines).strip()

    def format_approved_triage_replies(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        items = payload.get("items", [])
        lines = [
            "## Approved Triage Replies",
            f"total items: {summary.get('total_items', 0)}",
            "",
            "Copy/paste c\u00e1c draft_reply \u0111\u00e3 duy\u1ec7t l\u00ean fanpage/inbox. Sau khi g\u1eedi th\u1eadt, ch\u1ea1y command mark-triage-reply-sent \u0111\u1ec3 ghi nh\u1eadn permalink.",
        ]
        by_status = summary.get("by_status", {})
        by_priority = summary.get("by_priority", {})
        if by_status:
            lines.append("statuses:")
            lines.extend([f"- {name}: {count}" for name, count in by_status.items()])
        if by_priority:
            lines.append("priorities:")
            lines.extend([f"- {name}: {count}" for name, count in by_priority.items()])
        if items:
            lines.append("")
            lines.append("approved replies:")
            for index, item in enumerate(items[:5], start=1):
                lines.extend(
                    [
                        f"{index}. [{item.get('priority', '-').upper()}] {item.get('category', '-')} via {item.get('source', '-')}",
                        f"   triage_id: {item.get('triage_id', '-')}",
                        f"   assigned_to: {item.get('assigned_to', '-') or '-'}",
                        f"   message: {item.get('message', '-')}",
                        f"   draft_reply: {item.get('draft_reply', '-') or '-'}",
                        "   after sending:",
                        "   python3 -m fanpage_agent.main mark-triage-reply-sent --triage-id <TRIAGE_ID> --sent-at <ISO_TIME> --reply-permalink <URL>",
                    ]
                )
        return "\n".join(lines).strip()

    def format_operator_digest(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        approval_items = payload.get("approval_queue", {}).get("items", [])
        approved_reply_items = payload.get("approved_replies", {}).get("items", [])
        metrics_items = payload.get("metrics_backlog", {}).get("items", [])
        publish_blockers = payload.get("publish_blockers", {}).get("items", [])
        lines = [
            "## Daily Operator Digest",
            (
                f"Pending captions: {summary.get('pending_captions', 0)} | "
                f"Approved replies: {summary.get('approved_replies', 0)} | "
                f"Metrics backlog: {summary.get('metrics_backlog', 0)} | "
                f"Publish blockers: {summary.get('publish_blockers', 0)}"
            ),
            "Next:",
        ]
        next_index = 1
        if approval_items:
            item = approval_items[0]
            lines.append(
                f"{next_index}. approve {item.get('calendar_id', '-')} — {item.get('topic', '-')}"
            )
            lines.extend(self._caption_action_summary_lines(item))
            next_index += 1
        if approved_reply_items:
            item = approved_reply_items[0]
            lines.append(
                f"{next_index}. reply {item.get('triage_id', '-')} — "
                f"[{item.get('priority', '-').upper()}] {item.get('message', '-')} -> {item.get('draft_reply', '-') or '-'}"
            )
            next_index += 1
        if metrics_items:
            item = metrics_items[0]
            lines.append(
                f"{next_index}. record metrics for {item.get('calendar_id', '-')} — "
                f"{item.get('topic', '-')} published {item.get('published_at', '-')}"
            )
            next_index += 1
        if publish_blockers:
            item = publish_blockers[0]
            reasons = ", ".join(item.get("reason_codes", [])) or "unknown"
            lines.append(
                f"{next_index}. unblock publish {item.get('calendar_id', '-')} — "
                f"{item.get('topic', '-')} ({reasons}); next: {item.get('next_step', '-')}"
            )
            next_index += 1
        if next_index == 1:
            lines.append("- nothing pending")
        return "\n".join(lines).strip()

    def format_metrics_backlog(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        items = payload.get("items", [])
        lines = [
            "## Metrics Backlog",
            f"total items: {summary.get('total_items', 0)}",
            "",
        ]
        by_status = summary.get("by_status", {})
        by_approval_status = summary.get("by_approval_status", {})
        by_pillar = summary.get("by_pillar", {})
        if by_status:
            lines.append("statuses:")
            lines.extend([f"- {name}: {count}" for name, count in by_status.items()])
        if by_approval_status:
            lines.append("approval statuses:")
            lines.extend([f"- {name}: {count}" for name, count in by_approval_status.items()])
        if by_pillar:
            lines.append("pillars:")
            lines.extend([f"- {name}: {count}" for name, count in by_pillar.items()])
        if items:
            lines.append("")
            lines.append("pending metrics:")
            for index, item in enumerate(items[:3], start=1):
                lines.extend(
                    [
                        f"{index}. {item.get('date', '-')} — {item.get('topic', '-')}",
                        f"   calendar_id: {item.get('calendar_id', '-')}",
                        f"   published_at: {item.get('published_at', '-')}",
                        f"   permalink: {item.get('permalink', '-') or '-'}",
                        f"   current reach: {item.get('reach', '0')} | engagement rate: {item.get('engagement_rate', '0')}",
                    ]
                )
        return "\n".join(lines).strip()
