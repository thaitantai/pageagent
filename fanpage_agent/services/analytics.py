from __future__ import annotations

from fanpage_agent.models import AnalyticsReport, AnalyticsSummary, PostMetric


class AnalyticsService:
    def build_weekly_report(self, metrics: list[PostMetric]) -> AnalyticsReport:
        total_posts = len(metrics)
        total_reach = sum(item.reach for item in metrics)
        total_engagements = sum(item.engagements for item in metrics)
        total_leads = sum(item.leads for item in metrics)
        avg_engagement_rate = (total_engagements / total_reach) if total_reach else 0.0
        top_post = max(metrics, key=lambda item: (item.engagement_rate, item.reach), default=None)

        recommendations: list[str] = []
        if not metrics:
            recommendations.append("Chưa có dữ liệu KPI, cần cập nhật metrics trước khi review tuần.")
        else:
            pillar_scores: dict[str, float] = {}
            objective_scores: dict[str, int] = {}
            for item in metrics:
                pillar_scores[item.pillar] = pillar_scores.get(item.pillar, 0.0) + item.engagement_rate
                objective_scores[item.objective] = objective_scores.get(item.objective, 0) + item.leads
            best_pillar = max(pillar_scores.items(), key=lambda kv: kv[1])[0]
            best_objective = max(objective_scores.items(), key=lambda kv: kv[1])[0]
            recommendations.append(f"Nhân rộng pillar '{best_pillar}' vì đang có engagement rate tốt nhất.")
            recommendations.append(f"Giữ thêm bài theo objective '{best_objective}' vì đang tạo nhiều lead nhất.")
            if avg_engagement_rate < 0.05:
                recommendations.append("Engagement rate trung bình còn thấp, cần test hook ngắn hơn và visual mạnh hơn.")
            else:
                recommendations.append("Giữ cấu trúc hook hiện tại, ưu tiên lặp lại pattern bài top-performing.")

        return AnalyticsReport(
            summary=AnalyticsSummary(
                total_posts=total_posts,
                total_reach=total_reach,
                total_engagements=total_engagements,
                total_leads=total_leads,
                avg_engagement_rate=round(avg_engagement_rate, 4),
            ),
            top_post=top_post,
            recommendations=recommendations,
        )
