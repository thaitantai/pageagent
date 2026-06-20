from __future__ import annotations


class _ReportMixin:
    """Formatters for weekly reports, analytics reviews, and metrics auto-fetch."""

    def format_weekly_report(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        top_post = payload.get("top_post") or {}
        wow = payload.get("wow", {})

        def _trend_icon(val: float) -> str:
            if val > 5:
                return "\u25b2"  # ▲
            if val < -5:
                return "\u25bc"  # ▼
            return "\u2192"  # →

        lines = [
            "## Weekly Report",
            f"\U0001f4dd posts: {summary.get('total_posts', 0)}",
            f"\U0001f441 reach: {summary.get('total_reach', 0)}",
            f"\U0001f4ac engagements: {summary.get('total_engagements', 0)}",
            f"\U0001f3af leads: {summary.get('total_leads', 0)}",
            f"\U0001f4c8 avg engagement rate: {summary.get('avg_engagement_rate', 0)}",
            "",
        ]

        # WoW trend
        if wow:
            lines.append("tu\u1ea7n n\u00e0y vs tu\u1ea7n tr\u01b0\u1edbc:")
            wow_keys = [
                ("posts", "\U0001f4dd posts"),
                ("reach", "\U0001f441 reach"),
                ("engagements", "\U0001f4ac engagements"),
                ("engagement_rate", "\U0001f4c8 engagement rate"),
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
            lines.append("\U0001f3c6 top posts:")
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
            lines.append("\U0001f4c2 pillar performance:")
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
                lines.append(
                    f"  \u2022 {name}: {cnt} b\u00e0i | reach {reach} | rate {er_val * 100:.1f}%"
                )
            lines.append("")

        recommendations = payload.get("recommendations", [])
        if recommendations:
            lines.append("\U0001f4a1 recommendations:")
            lines.extend([f"  \u2022 {item}" for item in recommendations])
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
                lines.append(
                    f"  reach: {top_post.get('reach', 0)} | engagements: {top_post.get('engagements', 0)}"
                )
            lines.append("")

        if matched_posts:
            lines.append("--- matched posts ---")
            for p in matched_posts[:5]:
                recorded_badge = " [recorded]" if p.get("recorded") else " [preview]"
                lines.append(f"- {p.get('topic', '-')} ({p.get('pillar', '-')}){recorded_badge}")
                lines.append(
                    f"  reach: {p.get('reach', 0)} | engagements: {p.get('engagements', 0)}"
                )
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
                lines.append(
                    f"  reach: {p.get('reach', 0)} | engagements: {p.get('engagements', 0)}"
                )
                if p.get("permalink"):
                    lines.append(f"  {p['permalink']}")
            if len(unmatched_posts) > 5:
                lines.append(f"  ... and {len(unmatched_posts) - 5} more")

        return "\n".join(lines)
