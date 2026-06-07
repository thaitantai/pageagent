"""Analytics Dashboard Service — generates an HTML dashboard with Chart.js.

Reads post_metrics from the store, computes WoW trends and pillar breakdowns,
and produces a self-contained HTML file (artifacts/reports/dashboard.html).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fanpage_agent.models import PostMetric

DASHBOARD_TEMPLATE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fanpage Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }}
  .header {{ margin-bottom: 28px; }}
  .header h1 {{ font-size: 24px; color: #f1f5f9; }}
  .header .subtitle {{ font-size: 13px; color: #94a3b8; margin-top: 4px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 28px; }}
  .card {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }}
  .card .label {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }}
  .card .value {{ font-size: 28px; font-weight: 700; color: #f1f5f9; margin-top: 6px; }}
  .card .trend {{ font-size: 13px; margin-top: 4px; }}
  .trend-up {{ color: #22c55e; }}
  .trend-down {{ color: #ef4444; }}
  .trend-flat {{ color: #94a3b8; }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px; }}
  .chart-box {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }}
  .chart-box h3 {{ font-size: 14px; color: #94a3b8; margin-bottom: 12px; }}
  .chart-box.full {{ grid-column: 1 / -1; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; color: #94a3b8; padding: 8px 12px; border-bottom: 1px solid #334155; font-weight: 500; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #1e293b; }}
  tr:hover td {{ background: #334155; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
  .badge-pillar {{ background: #1e40af; color: #93c5fd; }}
  .badge-obj {{ background: #166534; color: #86efac; }}
  .rec-list {{ list-style: none; }}
  .rec-list li {{ padding: 8px 0; border-bottom: 1px solid #334155; }}
  .rec-list li:last-child {{ border: none; }}
  .rec-list li::before {{ content: "▸ "; color: #3b82f6; }}
  @media (max-width: 768px) {{ .chart-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>📊 Fanpage Dashboard</h1>
  <div class="subtitle">Generated: {generated_at} | Period: {period_label}</div>
</div>

<!-- Summary Cards -->
<div class="cards">
  <div class="card">
    <div class="label">Total Posts</div>
    <div class="value">{total_posts}</div>
    <div class="trend {wow_posts_class}">{wow_posts_label}</div>
  </div>
  <div class="card">
    <div class="label">Total Reach</div>
    <div class="value">{total_reach_formatted}</div>
    <div class="trend {wow_reach_class}">{wow_reach_label}</div>
  </div>
  <div class="card">
    <div class="label">Total Engagements</div>
    <div class="value">{total_engagements_formatted}</div>
    <div class="trend {wow_eng_class}">{wow_eng_label}</div>
  </div>
  <div class="card">
    <div class="label">Avg Engagement Rate</div>
    <div class="value">{avg_engagement_rate_pct}</div>
    <div class="trend {wow_er_class}">{wow_er_label}</div>
  </div>
</div>

<!-- Charts Row -->
<div class="chart-grid">
  <div class="chart-box">
    <h3>Reach Trend (7 ngày qua)</h3>
    <canvas id="reachChart"></canvas>
  </div>
  <div class="chart-box">
    <h3>Engagement Breakdown</h3>
    <canvas id="engagementPieChart"></canvas>
  </div>
  <div class="chart-box full">
    <h3>Pillar Performance</h3>
    <canvas id="pillarChart"></canvas>
  </div>
</div>

<!-- Top Posts -->
<div class="chart-box" style="margin-bottom: 28px;">
  <h3>🏆 Top Posts</h3>
  <table>
    <thead><tr><th>Topic</th><th>Pillar</th><th>Objective</th><th>Reach</th><th>Eng.</th><th>Rate</th></tr></thead>
    <tbody>
{top_posts_rows}
    </tbody>
  </table>
</div>

<!-- Recommendations -->
<div class="chart-box" style="margin-bottom: 28px;">
  <h3>💡 Recommendations</h3>
  <ul class="rec-list">
{recommendations_items}
  </ul>
</div>

<script>
const CHART_COLORS = ['#3b82f6','#22c55e','#f59e0b','#ef4444','#8b5cf6','#ec4899','#06b6d4','#84cc16'];

// Reach Trend Chart
new Chart(document.getElementById('reachChart'), {{
  type: 'line',
  data: {{
    labels: {reach_dates},
    datasets: [{{
      label: 'Reach',
      data: {reach_values},
      borderColor: '#3b82f6',
      backgroundColor: 'rgba(59,130,246,0.1)',
      fill: true,
      tension: 0.3,
      pointRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
      y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }}, beginAtZero: true }}
    }}
  }}
}});

// Engagement Pie Chart
new Chart(document.getElementById('engagementPieChart'), {{
  type: 'doughnut',
  data: {{
    labels: ['Likes', 'Comments', 'Shares'],
    datasets: [{{
      data: {pie_values},
      backgroundColor: ['#3b82f6', '#22c55e', '#f59e0b'],
      borderWidth: 0,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ color: '#94a3b8' }} }}
    }}
  }}
}});

// Pillar Performance Chart
new Chart(document.getElementById('pillarChart'), {{
  type: 'bar',
  data: {{
    labels: {pillar_labels},
    datasets: [
      {{
        label: 'Reach',
        data: {pillar_reach},
        backgroundColor: '#3b82f6',
        borderRadius: 4,
      }},
      {{
        label: 'Engagements',
        data: {pillar_eng},
        backgroundColor: '#22c55e',
        borderRadius: 4,
      }}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
      y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }}, beginAtZero: true }}
    }}
  }}
}});
</script>
</body>
</html>"""


class AnalyticsDashboardService:
    """Generate an HTML analytics dashboard from store metrics."""

    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = artifacts_dir

    def generate(
        self,
        metrics: list[PostMetric],
        now: datetime | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """Generate the dashboard HTML and save it.

        Args:
            metrics: PostMetric list from store.
            now: Reference timestamp (default: UTC now).
            days: Lookback period for "this week".

        Returns:
            Summary dict with file path, period, and counts.
        """
        ref = now or datetime.now(timezone.utc)
        period_start = ref - timedelta(days=days)

        # Separate current and previous period metrics
        current_metrics = [
            m for m in metrics
            if self._parse_date(m.published_at) >= period_start
        ]
        prev_start = period_start - timedelta(days=days)
        prev_metrics = [
            m for m in metrics
            if prev_start <= self._parse_date(m.published_at) < period_start
        ]

        # Compute WoW
        wow = self._compute_wow(current_metrics, prev_metrics)

        # Current period aggregations
        total_posts = len(current_metrics)
        total_reach = sum(m.reach for m in current_metrics)
        total_engagements = sum(m.engagements for m in current_metrics)
        avg_er = (
            round(total_engagements / total_reach, 4)
            if total_reach > 0
            else 0.0
        )

        # Reach trend (daily aggregation)
        daily_reach = self._daily_reach(current_metrics, days)
        reach_dates = [d["date"] for d in daily_reach]
        reach_values = [d["reach"] for d in daily_reach]

        # Pillar breakdown
        pillar_data = self._pillar_breakdown(current_metrics)

        # Top posts (sorted by reach desc)
        top_posts = sorted(
            current_metrics, key=lambda m: (m.reach, m.engagements), reverse=True
        )[:10]

        # Recommendations (from AnalyticsService-style logic)
        recommendations = self._generate_recommendations(
            current_metrics, wow, pillar_data
        )

        # Format numbers
        def fmt(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.1f}K"
            return str(n)

        # WoW labels
        def wow_label(key: str, up: bool = True) -> tuple[str, str]:
            val = wow.get(key, 0)
            if val > 0.05:
                cls = "trend-up"
                lbl = f"▲ {val:+.0f}% vs tuần trước"
            elif val < -0.05:
                cls = "trend-down"
                lbl = f"▼ {val:+.0f}% vs tuần trước"
            else:
                cls = "trend-flat"
                lbl = "→ không đổi vs tuần trước"
            return cls, lbl

        # Build top posts HTML rows
        top_posts_rows = ""
        for tp in top_posts:
            er = (
                f"{tp.engagement_rate * 100:.1f}%"
                if tp.reach > 0
                else "N/A"
            )
            top_posts_rows += (
                f'<tr><td>{self._escape(tp.topic)}</td>'
                f'<td><span class="badge badge-pillar">{self._escape(tp.pillar)}</span></td>'
                f'<td><span class="badge badge-obj">{self._escape(tp.objective)}</span></td>'
                f"<td>{fmt(tp.reach)}</td>"
                f"<td>{fmt(tp.engagements)}</td>"
                f"<td>{er}</td></tr>\n"
            )

        # Recommendations list
        recommendations_items = "".join(
            f"<li>{self._escape(r)}</li>\n" for r in recommendations
        )

        w_posts_cls, w_posts_lbl = wow_label("posts")
        w_reach_cls, w_reach_lbl = wow_label("reach")
        w_eng_cls, w_eng_lbl = wow_label("engagements")
        w_er_cls, w_er_lbl = wow_label("engagement_rate")

        html = DASHBOARD_TEMPLATE.format(
            generated_at=ref.strftime("%Y-%m-%d %H:%M UTC"),
            period_label=f"{days} ngày ({(ref - timedelta(days=days)).strftime('%d/%m')} – {ref.strftime('%d/%m')})",
            total_posts=total_posts,
            total_reach_formatted=fmt(total_reach),
            total_engagements_formatted=fmt(total_engagements),
            avg_engagement_rate_pct=f"{avg_er * 100:.1f}%",
            wow_posts_class=w_posts_cls,
            wow_posts_label=w_posts_lbl,
            wow_reach_class=w_reach_cls,
            wow_reach_label=w_reach_lbl,
            wow_eng_class=w_eng_cls,
            wow_eng_label=w_eng_lbl,
            wow_er_class=w_er_cls,
            wow_er_label=w_er_lbl,
            reach_dates=json_dumps(reach_dates),
            reach_values=json_dumps(reach_values),
            pie_values=json_dumps(
                [sum(m.engagements for m in current_metrics) or 1, 0, 0]
            ),
            pillar_labels=json_dumps(list(pillar_data.keys())),
            pillar_reach=json_dumps([d["reach"] for d in pillar_data.values()]),
            pillar_eng=json_dumps([d["engagements"] for d in pillar_data.values()]),
            top_posts_rows=top_posts_rows,
            recommendations_items=recommendations_items,
        )

        out_path = self.artifacts_dir / "reports" / "dashboard.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")

        return {
            "path": str(out_path),
            "generated_at": ref.isoformat(),
            "period_days": days,
            "total_posts": total_posts,
            "total_reach": total_reach,
            "total_engagements": total_engagements,
            "avg_engagement_rate": avg_er,
            "wow": wow,
        }

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    @staticmethod
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

    @staticmethod
    def _compute_wow(
        current: list[PostMetric], prev: list[PostMetric]
    ) -> dict[str, float]:
        def _agg(metrics: list[PostMetric]) -> dict[str, float]:
            n = len(metrics)
            r = sum(m.reach for m in metrics)
            e = sum(m.engagements for m in metrics)
            er = e / r if r > 0 else 0.0
            return {"posts": n, "reach": r, "engagements": e, "engagement_rate": er}

        c = _agg(current)
        p = _agg(prev)

        result: dict[str, float] = {}
        for key in ("posts", "reach", "engagements", "engagement_rate"):
            pv = p.get(key, 0)
            cv = c.get(key, 0)
            if pv > 0:
                result[key] = round(((cv - pv) / pv) * 100, 1)
            else:
                result[key] = 0.0
        return result

    @staticmethod
    def _daily_reach(
        metrics: list[PostMetric], days: int
    ) -> list[dict[str, object]]:

        ref = datetime.now(timezone.utc)
        daily: dict[str, int] = {}
        for m in metrics:
            d = m.published_at[:10]
            daily[d] = daily.get(d, 0) + m.reach

        result: list[dict[str, object]] = []
        for i in range(days - 1, -1, -1):
            day = (ref - timedelta(days=i)).strftime("%Y-%m-%d")
            result.append({"date": day, "reach": daily.get(day, 0)})
        return result

    @staticmethod
    def _pillar_breakdown(
        metrics: list[PostMetric],
    ) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for m in metrics:
            p = m.pillar or "other"
            if p not in result:
                result[p] = {"reach": 0, "engagements": 0, "count": 0}
            result[p]["reach"] += m.reach
            result[p]["engagements"] += m.engagements
            result[p]["count"] += 1
        return result

    @staticmethod
    def _generate_recommendations(
        metrics: list[PostMetric],
        wow: dict[str, float],
        pillar_data: dict[str, dict[str, int]],
    ) -> list[str]:
        recs: list[str] = []

        if not metrics:
            recs.append("Chưa có dữ liệu metrics trong kỳ này.")
            return recs

        # WoW insight
        if wow.get("reach", 0) > 10:
            recs.append(f"Reach tăng {wow['reach']:+.0f}% so với tuần trước — giữ chất lượng nội dung hiện tại.")
        elif wow.get("reach", 0) < -10:
            recs.append(f"Reach giảm {wow['reach']:+.0f}% so với tuần trước — cần refresh hook và visual.")

        if wow.get("engagement_rate", 0) < -10:
            recs.append("Engagement rate giảm — kiểm tra lại CTA và tương tác đầu bài.")
        elif wow.get("engagement_rate", 0) > 10:
            recs.append("Engagement rate tăng tốt — các bài đang chạm đúng insight audience.")

        # Pillar insight
        if pillar_data:
            best_pillar = max(
                pillar_data.items(),
                key=lambda kv: kv[1]["engagements"] / max(kv[1]["reach"], 1),
                default=None,
            )
            if best_pillar:
                recs.append(
                    f"Pillar '{best_pillar[0]}' có engagement rate cao nhất — nhân rộng angle này."
                )

            most_posts = max(
                pillar_data.items(),
                key=lambda kv: kv[1]["count"],
                default=None,
            )
            if most_posts and best_pillar and most_posts[0] != best_pillar[0]:
                recs.append(
                    f"Pillar '{most_posts[0]}' có nhiều bài nhất ({most_posts[1]['count']}) — "
                    "kiểm tra xem reach/engagement có tương xứng không."
                )

        # General
        avg_er = (
            sum(m.engagements for m in metrics) / max(sum(m.reach for m in metrics), 1)
        )
        if avg_er < 0.03:
            recs.append("Engagement rate trung bình dưới 3% — cần hook mạnh hơn và visual thu hút hơn.")
        elif avg_er > 0.08:
            recs.append("Engagement rate trên 8% — nội dung đang rất tốt, giữ vững phong độ!")

        return recs

    @staticmethod
    def _escape(text: str) -> str:
        """Escape HTML special chars."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )


def json_dumps(obj: object) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)
