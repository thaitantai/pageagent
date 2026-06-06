from __future__ import annotations

from datetime import datetime, timezone


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
        wow = payload.get("wow", {})

        def _trend_icon(val: float) -> str:
            if val > 5:
                return "▲"
            if val < -5:
                return "▼"
            return "→"

        lines = [
            "## Weekly Report",
            f"📝 posts: {summary.get('total_posts', 0)}",
            f"👁 reach: {summary.get('total_reach', 0)}",
            f"💬 engagements: {summary.get('total_engagements', 0)}",
            f"🎯 leads: {summary.get('total_leads', 0)}",
            f"📈 avg engagement rate: {summary.get('avg_engagement_rate', 0)}",
            "",
        ]

        # WoW trend
        if wow:
            lines.append("tuần này vs tuần trước:")
            wow_keys = [
                ("posts", "📝 posts"),
                ("reach", "👁 reach"),
                ("engagements", "💬 engagements"),
                ("engagement_rate", "📈 engagement rate"),
            ]
            for key, label in wow_keys:
                val = wow.get(key, 0)
                icon = _trend_icon(val)
                lines.append(f"  {icon} {label}: {val:+.0f}%")
            lines.append("")

        # Top posts (up to 3)
        top_posts_raw = payload.get("top_posts") or []
        if top_post and not top_posts_raw:
            # fallback to single top_post
            top_posts_raw = [top_post]
        if top_posts_raw:
            lines.append("🏆 top posts:")
            for i, tp in enumerate(top_posts_raw[:3], 1):
                topic = tp.get("topic", "-")
                pillar = tp.get("pillar", "-")
                obj = tp.get("objective", "-")
                reach = tp.get("reach", 0)
                eng = tp.get("engagements", 0)
                er_raw = tp.get("engagement_rate", 0)
                er = f"{er_raw * 100:.1f}%" if isinstance(er_raw, float) and reach > 0 else "N/A"
                lines.append(f"  {i}. {topic}")
                lines.append(f"     {pillar} | {obj} | reach {reach} | eng {eng} | rate {er}")
            lines.append("")

        # Pillar breakdown
        pillar_breakdown = payload.get("pillar_breakdown", {})
        if pillar_breakdown:
            lines.append("📂 pillar performance:")
            sorted_pillars = sorted(
                pillar_breakdown.items(),
                key=lambda kv: kv[1].get("reach", 0),
                reverse=True,
            )
            for name, data in sorted_pillars:
                cnt = data.get("count", 0)
                reach = data.get("reach", 0)
                eng = data.get("engagements", 0)
                er_val = eng / max(reach, 1)
                lines.append(f"  • {name}: {cnt} bài | reach {reach} | rate {er_val*100:.1f}%")
            lines.append("")

        recommendations = payload.get("recommendations", [])
        if recommendations:
            lines.append("💡 recommendations:")
            lines.extend([f"  • {item}" for item in recommendations])
        return "\n".join(lines).strip()

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
                {"urgent": 0, "high": 1, "normal": 2, "low": 3}.get(item.get("priority", "normal"), 9),
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
                        f"{index}. [{item.get('priority', '-').upper()}] {item.get('category', '-')} via {item.get('source', '-')}" ,
                        f"   triage_id: {item.get('triage_id', '-')}" ,
                        f"   status: {item.get('status', '-')}" ,
                        f"   assigned_to: {item.get('assigned_to', '-') or '-'}" ,
                        f"   created_at: {item.get('created_at', '-')}{age_hint}" ,
                        f"   message: {item.get('message', '-')}" ,
                        f"   action: {item.get('recommended_action', '-')}" ,
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
            (
                f"Pending captions: {summary.get('pending_captions', 0)} | "
                f"Approved replies: {summary.get('approved_replies', 0)} | "
                f"Metrics backlog: {summary.get('metrics_backlog', 0)}"
            ),
            "Next:",
        ]
        next_index = 1
        if approval_items:
            item = approval_items[0]
            lines.append(f"{next_index}. approve {item.get('calendar_id', '-')} — {item.get('topic', '-')}")
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

    def format_hashtag_set(self, payload: dict) -> str:
        content_topic = payload.get("content_topic", "")
        pillar = payload.get("pillar", "")
        objective = payload.get("objective", "")
        suggestions = payload.get("suggestions", [])
        recommended = payload.get("recommended", [])

        lines = [
            "## Hashtag Package",
            f"topic: {content_topic}",
            f"pillar: {pillar} | objective: {objective}",
            "",
        ]

        # Group by tier
        tiers = {"high_volume": "High Volume", "medium_volume": "Medium Volume",
                 "low_volume": "Low Volume", "branded": "Branded"}
        for tier_key, tier_label in tiers.items():
            tier_tags = [s for s in suggestions if s.get("tier") == tier_key]
            if not tier_tags:
                continue
            lines.append(f"**{tier_label}:**")
            for s in tier_tags:
                tag = s.get("tag", "")
                score = s.get("relevance_score", 0)
                reason = s.get("reason", "")
                badge = " ✅" if tag in recommended else ""
                lines.append(f"  #{tag} ({score:.0%}){badge} — {reason}")
            lines.append("")

        if recommended:
            lines.append("**Recommended:** " + " ".join(f"#{t}" for t in recommended))

        return "\n".join(lines).strip()

    def format_metrics_auto_fetch(self, payload: dict) -> str:
        scanned = payload.get("scanned", 0)
        missing = payload.get("missing_metrics", 0)
        fetched = payload.get("fetched", 0)
        recorded = payload.get("recorded", 0)
        errors = payload.get("errors", 0)
        items = payload.get("items", [])

        lines = [
            "## Metrics Auto-Fetch",
            f"scanned: {scanned} published items",
            f"missing metrics: {missing}",
            f"fetched: {fetched} | recorded: {recorded} | errors: {errors}",
            "",
        ]

        recorded_items = [i for i in items if i.get("status") == "recorded"]
        error_items = [i for i in items if i.get("status") == "error"]
        skipped_items = [i for i in items if i.get("status") == "skipped"]

        if recorded_items:
            lines.append("**Recorded:**")
            for item in recorded_items[:5]:
                lines.append(f"- {item.get('topic', '-')} ({item.get('calendar_id', '')})")
                lines.append(f"  {item.get('detail', '')}")
                if item.get("permalink"):
                    lines.append(f"  {item['permalink']}")
            if len(recorded_items) > 5:
                lines.append(f"  ... +{len(recorded_items) - 5} more")

        if error_items:
            lines.append("")
            lines.append("**Errors:**")
            for item in error_items[:3]:
                lines.append(f"- {item.get('topic', '-')} — {item.get('detail', '')}")

        if skipped_items:
            lines.append("")
            lines.append(f"**Skipped:** {len(skipped_items)} items (no permalink)")

        return "\n".join(lines)

    def format_analytics_review(self, payload: dict) -> str:
        review_period = payload.get("review_period", {})
        report = payload.get("report", {})
        summary = report.get("summary", {})
        matched_posts = payload.get("matched_posts", [])
        unmatched_posts = payload.get("unmatched_posts", [])

        lines = [
            "## Analytics Review",
            "",
            f"period: {review_period.get('days', 7)} days",
            f"fetched: {payload.get('fetched', 0)} FB posts",
            f"matched to calendar: {payload.get('matched', 0)}",
            f"unmatched: {payload.get('unmatched', 0)}",
            f"recorded to store: {payload.get('recorded', 0)}",
            "",
        ]

        if payload.get("recorded", 0) > 0:
            lines.append("--- metrics summary ---")
            lines.append(f"total posts: {summary.get('total_posts', 0)}")
            lines.append(f"total reach: {summary.get('total_reach', 0)}")
            lines.append(f"total engagements: {summary.get('total_engagements', 0)}")
            lines.append(f"avg engagement rate: {summary.get('avg_engagement_rate', 0)}")
            top_post = report.get("top_post")
            if top_post:
                lines.append("")
                lines.append(f"top post: {top_post.get('topic', '-')}")
                lines.append(f"  reach: {top_post.get('reach', 0)} | engagements: {top_post.get('engagements', 0)}")
            lines.append("")

        if matched_posts:
            lines.append("--- matched posts ---")
            for p in matched_posts[:5]:
                recorded_badge = " [recorded]" if p.get("recorded") else " [preview]"
                lines.append(f"- {p.get('topic', '-')} ({p.get('pillar', '-')}){recorded_badge}")
                lines.append(f"  reach: {p.get('reach', 0)} | engagements: {p.get('engagements', 0)}")
                if p.get("permalink"):
                    lines.append(f"  {p['permalink']}")
            if len(matched_posts) > 5:
                lines.append(f"  ... and {len(matched_posts) - 5} more")

        if unmatched_posts:
            lines.append("")
            lines.append("--- unmatched posts ---")
            for p in unmatched_posts[:5]:
                preview = (p.get("message_preview") or "")[:80]
                lines.append(f"- [{p.get('fb_post_id', '')}] {p.get('created_time', '')[:10]}")
                lines.append(f"  {preview}...")
                lines.append(f"  reach: {p.get('reach', 0)} | engagements: {p.get('engagements', 0)}")
                if p.get("permalink"):
                    lines.append(f"  {p['permalink']}")
            if len(unmatched_posts) > 5:
                lines.append(f"  ... and {len(unmatched_posts) - 5} more")

        return "\n".join(lines)
