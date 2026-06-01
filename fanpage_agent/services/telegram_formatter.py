from __future__ import annotations


class TelegramFormatterService:
    def format_weekly_plan(self, payload: dict) -> str:
        lines = [
            "## Weekly Plan",
            f"plan: {payload.get('plan_title', '-')}",
            self._format_verification(payload.get('verification')),
            "",
        ]
        for index, day in enumerate(payload.get("days", []), start=1):
            lines.extend(
                [
                    f"{index}. {day.get('date', '-') } — {day.get('topic', '-')}",
                    f"   pillar: {day.get('pillar', '-')} | objective: {day.get('objective', '-')}",
                    f"   hook: {day.get('hook', '-')}",
                    f"   cta: {day.get('cta', '-')}",
                ]
            )
        strategy_notes = payload.get("strategy_notes", [])
        if strategy_notes:
            lines.append("")
            lines.append("strategy notes:")
            lines.extend([f"- {item}" for item in strategy_notes])
        return "\n".join(lines).strip()

    def format_caption_package(self, payload: dict) -> str:
        lines = [
            "## Caption Package",
            f"topic: {payload.get('topic', '-')}",
            self._format_verification(payload.get('verification')),
            "",
        ]
        for variant in payload.get("variants", []):
            lines.extend(
                [
                    f"Variant {variant.get('label', '-')}",
                    f"- hook: {variant.get('hook', '-')}",
                    f"- caption: {variant.get('caption', '-')}",
                    f"- cta: {variant.get('cta', '-')}",
                    f"- visual: {variant.get('visual_brief', '-')}",
                    "",
                ]
            )
        dos = payload.get("dos", [])
        if dos:
            lines.append("dos:")
            lines.extend([f"- {item}" for item in dos])
        donts = payload.get("donts", [])
        if donts:
            lines.append("don'ts:")
            lines.extend([f"- {item}" for item in donts])
        return "\n".join(lines).strip()

    def format_weekly_report(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        top_post = payload.get("top_post") or {}
        lines = [
            "## Weekly Report",
            f"posts: {summary.get('total_posts', 0)}",
            f"reach: {summary.get('total_reach', 0)}",
            f"engagements: {summary.get('total_engagements', 0)}",
            f"leads: {summary.get('total_leads', 0)}",
            f"avg engagement rate: {summary.get('avg_engagement_rate', 0)}",
            "",
        ]
        if top_post:
            lines.extend(
                [
                    "top post:",
                    f"- topic: {top_post.get('topic', '-')}",
                    f"- pillar: {top_post.get('pillar', '-')} | objective: {top_post.get('objective', '-')}",
                    f"- reach: {top_post.get('reach', 0)} | engagements: {top_post.get('engagements', 0)} | leads: {top_post.get('leads', 0)}",
                    "",
                ]
            )
        recommendations = payload.get("recommendations", [])
        if recommendations:
            lines.append("recommendations:")
            lines.extend([f"- {item}" for item in recommendations])
        return "\n".join(lines).strip()

    def format_community_triage(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        by_category = summary.get("by_category", {})
        by_priority = summary.get("by_priority", {})
        by_status = summary.get("by_status", {})
        items = payload.get("items", [])
        ranked_items = sorted(
            items,
            key=lambda item: ({"urgent": 0, "high": 1, "normal": 2, "low": 3}.get(item.get("priority", "normal"), 9), item.get("category", "")),
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
                lines.extend(
                    [
                        f"{index}. [{item.get('priority', '-').upper()}] {item.get('category', '-')} via {item.get('source', '-')}",
                        f"   triage_id: {item.get('triage_id', '-')}",
                        f"   status: {item.get('status', '-')}",
                        f"   message: {item.get('message', '-')}",
                        f"   action: {item.get('recommended_action', '-')}",
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
            f"as of: {summary.get('as_of', '-')}",
            f"SLA days: {summary.get('sla_days', 0)}",
            f"total items: {summary.get('total_items', 0)}",
            f"pending: {summary.get('pending', 0)}",
            f"overdue pending: {summary.get('overdue_pending', 0)}",
            f"approved: {summary.get('approved', 0)}",
            f"rejected: {summary.get('rejected', 0)}",
            "",
        ]
        lines.append("Overdue pending captions:")
        if overdue_items:
            for index, item in enumerate(overdue_items[:5], start=1):
                lines.extend(
                    [
                        f"{index}. {item.get('date', '-')} — {item.get('topic', '-')}",
                        f"   calendar_id: {item.get('calendar_id', '-')}",
                        f"   days pending: {item.get('days_pending', 0)}",
                        f"   draft caption: {item.get('draft_caption_ref', '-') or '-'}",
                        *self._caption_action_lines(item),
                    ]
                )
        else:
            lines.append("- none")
        if recent_rejections:
            lines.append("")
            lines.append("Recent rejections:")
            for index, item in enumerate(recent_rejections[:5], start=1):
                lines.extend(
                    [
                        f"{index}. {item.get('date', '-')} — {item.get('topic', '-')}",
                        f"   calendar_id: {item.get('calendar_id', '-')}",
                        f"   notes: {item.get('notes', '-') or '-'}",
                    ]
                )
        return "\n".join(lines).strip()

    def format_approved_triage_replies(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        items = payload.get("items", [])
        lines = [
            "## Approved Triage Replies",
            f"total items: {summary.get('total_items', 0)}",
            "",
            "Copy/paste các draft_reply đã duyệt lên fanpage/inbox. Sau khi gửi thật, chạy command mark-triage-reply-sent để ghi nhận permalink.",
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
        lines = [
            "## Daily Operator Digest",
            f"Pending captions: {summary.get('pending_captions', 0)}",
            f"Approved replies: {summary.get('approved_replies', 0)}",
            f"Metrics backlog: {summary.get('metrics_backlog', 0)}",
            "",
        ]
        lines.append("Pending captions:")
        if approval_items:
            for index, item in enumerate(approval_items[:3], start=1):
                lines.extend(
                    [
                        f"{index}. {item.get('date', '-')} — {item.get('topic', '-')}",
                        f"   calendar_id: {item.get('calendar_id', '-')}",
                        f"   draft caption: {item.get('draft_caption_ref', '-') or '-'}",
                        *self._caption_action_lines(item),
                    ]
                )
        else:
            lines.append("- none")
        lines.append("")
        lines.append("Approved replies:")
        if approved_reply_items:
            for index, item in enumerate(approved_reply_items[:3], start=1):
                lines.extend(
                    [
                        f"{index}. [{item.get('priority', '-').upper()}] {item.get('category', '-')} via {item.get('source', '-')}",
                        f"   triage_id: {item.get('triage_id', '-')}",
                        f"   message: {item.get('message', '-')}",
                        f"   draft_reply: {item.get('draft_reply', '-') or '-'}",
                    ]
                )
        else:
            lines.append("- none")
        lines.append("")
        lines.append("Metrics backlog:")
        if metrics_items:
            for index, item in enumerate(metrics_items[:3], start=1):
                lines.extend(
                    [
                        f"{index}. {item.get('date', '-')} — {item.get('topic', '-')}",
                        f"   calendar_id: {item.get('calendar_id', '-')}",
                        f"   published_at: {item.get('published_at', '-')}",
                        f"   permalink: {item.get('permalink', '-') or '-'}",
                    ]
                )
        else:
            lines.append("- none")
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

    def format_research_brief(self, payload: dict) -> str:
        lines = ["## Research Brief"]
        if payload.get("recommended_objectives"):
            lines.append(f"objective focus: {payload['recommended_objectives'][0]}")
        if payload.get("recommended_pillars"):
            lines.append(f"pillar focus: {payload['recommended_pillars'][0]}")
        if payload.get("campaign_focus"):
            lines.append(f"campaign focus: {', '.join(payload['campaign_focus'][:3])}")
        if payload.get("top_performing_topics"):
            lines.append(f"top topic: {payload['top_performing_topics'][0]}")
        lines.append("")
        if payload.get("frequent_questions"):
            lines.append("frequent questions:")
            lines.extend([f"- {item}" for item in payload["frequent_questions"][:3]])
        if payload.get("next_angles"):
            lines.append("next angles:")
            lines.extend([f"- {item}" for item in payload["next_angles"][:3]])
        if payload.get("recommendations"):
            lines.append("recommendations:")
            lines.extend([f"- {item}" for item in payload["recommendations"][:3]])
        if payload.get("overused_topics"):
            lines.append("watchouts:")
            lines.extend([f"- overused topic: {item}" for item in payload["overused_topics"][:3]])
        return "\n".join(lines).strip()

    @staticmethod
    def _format_verification(verification: dict | None) -> str:
        if not verification:
            return "verification: N/A"
        return "verification: PASS" if verification.get("passed") else "verification: FAIL"

    @staticmethod
    def _caption_action_lines(item: dict) -> list[str]:
        calendar_id = item.get("calendar_id", "") or "<CALENDAR_ID>"
        draft_caption_ref = item.get("draft_caption_ref", "") or "<CAPTION_FILE>"
        return [
            "   actions:",
            f"   approve: python3 -m fanpage_agent.main approve-caption --calendar-id {calendar_id} --caption-file {draft_caption_ref} --approved-by <NAME> --approved-at <ISO_TIME>",
            f"   reject: python3 -m fanpage_agent.main reject-caption --calendar-id {calendar_id} --reason <REASON> --rejected-at <ISO_TIME>",
        ]
