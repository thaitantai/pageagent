from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fanpage_agent.models import AnalyticsReport, AnalyticsSummary, PostMetric


def _parse_date(raw: str) -> datetime:
    try:
        normalized = raw.replace("Z", "+00:00").strip()
        # Date-only string: treat as end of day
        if len(raw.strip()) == 10 and raw.strip().count("-") == 2:
            normalized += "T23:59:59+00:00"
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


class AnalyticsService:
    def build_weekly_report(
        self,
        metrics: list[PostMetric],
        now: datetime | None = None,
        days: int = 7,
    ) -> AnalyticsReport:
        if now is not None:
            ref = now
        elif metrics:
            ref = max(_parse_date(item.published_at) for item in metrics)
        else:
            ref = datetime.now(timezone.utc)
        period_start = ref - timedelta(days=days)

        # Split into current and previous period
        current_metrics = [
            m for m in metrics if _parse_date(m.published_at) >= period_start
        ]
        prev_start = period_start - timedelta(days=days)
        prev_metrics = [
            m for m in metrics
            if prev_start <= _parse_date(m.published_at) < period_start
        ]

        # Current period aggregates
        total_posts = len(current_metrics)
        total_reach = sum(item.reach for item in current_metrics)
        total_engagements = sum(item.engagements for item in current_metrics)
        total_leads = sum(item.leads for item in current_metrics)
        avg_engagement_rate = (total_engagements / total_reach) if total_reach else 0.0

        # Top posts
        sorted_posts = sorted(
            current_metrics,
            key=lambda item: (item.engagement_rate, item.reach),
            reverse=True,
        )
        top_post = sorted_posts[0] if sorted_posts else None
        top_posts = sorted_posts[:3]

        # WoW comparison
        def _agg(m_list: list[PostMetric]) -> dict[str, float]:
            n = len(m_list)
            r = sum(m.reach for m in m_list)
            e = sum(m.engagements for m in m_list)
            er = e / r if r > 0 else 0.0
            return {"posts": n, "reach": r, "engagements": e, "engagement_rate": er}

        c = _agg(current_metrics)
        p = _agg(prev_metrics)
        wow: dict[str, float] = {}
        for key in ("posts", "reach", "engagements", "engagement_rate"):
            pv = p.get(key, 0)
            cv = c.get(key, 0)
            wow[key] = round(((cv - pv) / pv) * 100, 1) if pv > 0 else 0.0

        # Pillar breakdown
        pillar_breakdown: dict[str, dict[str, int]] = {}
        for item in current_metrics:
            pillar = item.pillar or "other"
            if pillar not in pillar_breakdown:
                pillar_breakdown[pillar] = {"count": 0, "reach": 0, "engagements": 0}
            pillar_breakdown[pillar]["count"] += 1
            pillar_breakdown[pillar]["reach"] += item.reach
            pillar_breakdown[pillar]["engagements"] += item.engagements

        # Recommendations
        recommendations: list[str] = []
        if not current_metrics:
            recommendations.append("Chưa có dữ liệu metrics trong kỳ này.")
        else:
            # WoW-based recs
            if wow.get("reach", 0) > 10:
                recommendations.append(f"Reach tăng {wow['reach']:+.0f}% — giữ chất lượng nội dung hiện tại.")
            elif wow.get("reach", 0) < -10:
                recommendations.append(f"Reach giảm {wow['reach']:+.0f}% — refresh hook và visual.")

            if wow.get("engagement_rate", 0) < -10:
                recommendations.append("Engagement rate giảm — kiểm tra lại CTA và tương tác đầu bài.")
            elif wow.get("engagement_rate", 0) > 10:
                recommendations.append("Engagement rate tăng — nội dung đang chạm đúng insight audience.")

            # Pillar-based recs
            if pillar_breakdown:
                best_pillar = max(
                    pillar_breakdown.items(),
                    key=lambda kv: kv[1]["engagements"] / max(kv[1]["reach"], 1),
                )[0]
                recommendations.append(f"Nhân rộng pillar '{best_pillar}' — đang có engagement rate tốt nhất.")

            if avg_engagement_rate < 0.03:
                recommendations.append("Engagement rate trung bình dưới 3% — cần hook mạnh hơn và visual thu hút.")
            elif avg_engagement_rate > 0.08:
                recommendations.append("Engagement rate trên 8% — nội dung đang rất tốt, giữ vững phong độ!")

        return AnalyticsReport(
            summary=AnalyticsSummary(
                total_posts=total_posts,
                total_reach=total_reach,
                total_engagements=total_engagements,
                total_leads=total_leads,
                avg_engagement_rate=round(avg_engagement_rate, 4),
            ),
            top_post=top_post,
            top_posts=top_posts,
            wow=wow,
            pillar_breakdown=pillar_breakdown,
            recommendations=recommendations,
        )
