"""AnalystAgent — performance analytics, pattern learning, and reporting."""

from __future__ import annotations

from typing import Any

from fanpage_agent_v2.core.agent import BaseAgent
from fanpage_agent_v2.core.types import ActionPriority, AgentRole, AgentResult, AgentTask


class AnalystAgent(BaseAgent):
    """Analyst — analyses content performance and drives learning.

    Capabilities:
    - weekly_report: Generate weekly performance summary
    - pattern_analysis: Identify patterns in top/bottom performers
    - pillar_health: Score each pillar's performance
    - ab_test_results: Compare A/B variant performance
    - content_recommendations: Suggest content improvements
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        performance_memory=None,
    ) -> None:
        super().__init__(config)
        self._memory = performance_memory

    @property
    def role(self) -> AgentRole:
        return AgentRole.ANALYST

    @property
    def capabilities(self) -> list[str]:
        return [
            "weekly_report",
            "pattern_analysis",
            "pillar_health",
            "ab_test_results",
            "content_recommendations",
        ]

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params

        if action == "weekly_report":
            return self._weekly_report(page_id=params.get("page_id"))
        elif action == "pattern_analysis":
            return self._pattern_analysis(
                pattern_types=params.get("pattern_types", []),
            )
        elif action == "pillar_health":
            return self._pillar_health(page_id=params.get("page_id"))
        elif action == "ab_test_results":
            return self._ab_test_results()
        elif action == "content_recommendations":
            return self._content_recommendations(params.get("pillar", None))
        return AgentResult(task_id=task.id, success=False, error=f"Unknown action: {action}")

    def self_driving_tick(self) -> list[tuple[str, dict, ActionPriority]]:
        """Propose analytics tasks based on recency."""
        proposals: list[tuple[str, dict, ActionPriority]] = []
        if self._should_act("weekly_report", 86400):
            proposals.append(("weekly_report", {}, ActionPriority.LOW))
        if self._should_act("pattern_analysis", 43200):
            proposals.append(("pattern_analysis", {"pattern_types": []}, ActionPriority.LOW))
        return proposals

    def _weekly_report(self, page_id: str | None = None) -> AgentResult:
        """Generate weekly performance report."""
        if not self._memory:
            return AgentResult(
                task_id="weekly-report",
                success=True,
                data={"summary": "Chưa có dữ liệu performance.", "pillars": []},
            )

        pillars = self._memory.pillar_performance(page_id=page_id)
        recent = self._memory.get_recent_posts(limit=5, page_id=page_id)
        top = self._memory.get_top_patterns(limit=5)
        recs = self._memory.get_recommendations(limit=3)
        total = sum(p.get("post_count", 0) for p in pillars)
        avg_eng = round(sum(p.get("avg_engagement", 0) for p in pillars) / max(len(pillars), 1), 1)
        avg_reach = round(sum(p.get("avg_reach", 0) for p in pillars) / max(len(pillars), 1), 0)

        return AgentResult(
            task_id="weekly-report",
            success=True,
            data={
                "total_posts": total,
                "avg_reach": int(avg_reach),
                "avg_engagement": avg_eng,
                "pillars": pillars,
                "recent_posts": recent,
                "top_patterns": [
                    {"type": p.pattern_type, "value": p.value, "avg_engagement": p.avg_engagement}
                    for p in top
                ],
                "recommendations": recs,
                "summary": self._generate_summary(total, avg_eng, pillars, recs),
            },
        )

    def _pattern_analysis(self, pattern_types: list[str]) -> AgentResult:
        """Analyse patterns by type."""
        if not self._memory:
            return AgentResult(task_id="pattern-analysis", success=True, data={"patterns": []})

        types = pattern_types or ["pillar", "format", "hook_style", "posting_hour", "tone"]
        results = {}
        for pt in types:
            patterns = self._memory.get_top_patterns(pattern_type=pt, limit=5)
            if patterns:
                results[pt] = [
                    {"value": p.value, "avg_engagement": p.avg_engagement,
                     "sample_size": p.sample_size, "confidence": p.confidence}
                    for p in patterns
                ]

        return AgentResult(
            task_id="pattern-analysis",
            success=True,
            data={"patterns": results},
        )

    def _pillar_health(self, page_id: str | None = None) -> AgentResult:
        """Score each pillar's health based on performance."""
        if not self._memory:
            return AgentResult(task_id="pillar-health", success=True, data={"pillars": [], "overall": "no_data"})

        pillars = self._memory.pillar_performance(page_id=page_id)
        for p in pillars:
            er = p.get("avg_engagement_rate", 0)
            if er >= 5:
                p["health"] = "excellent"
            elif er >= 2:
                p["health"] = "good"
            elif er >= 0.5:
                p["health"] = "needs_attention"
            else:
                p["health"] = "poor"

        return AgentResult(
            task_id="pillar-health",
            success=True,
            data={
                "pillars": pillars,
                "healthy_count": sum(1 for p in pillars if p.get("health") in ("excellent", "good")),
                "needs_attention": [p for p in pillars if p.get("health") in ("needs_attention", "poor")],
            },
        )

    def _ab_test_results(self) -> AgentResult:
        """Compare A/B variant performance (placeholder for now)."""
        return AgentResult(
            task_id="ab-test",
            success=True,
            data={
                "note": "A/B analysis requires at least 2 variants per post published with different IDs.",
                "tests_run": 0,
                "results": [],
            },
        )

    def _content_recommendations(self, pillar: str | None) -> AgentResult:
        """Generate content recommendations."""
        if not self._memory:
            return AgentResult(
                task_id="content-recs",
                success=True,
                data={"recommendations": ["Chưa có đủ dữ liệu để đề xuất."]},
            )

        recs = self._memory.get_recommendations(limit=5)
        return AgentResult(
            task_id="content-recs",
            success=True,
            data={"recommendations": recs},
        )

    def _generate_summary(self, total: int, avg_eng: float, pillars: list[dict], recs: list[str]) -> str:
        """Generate a natural-language summary for reports."""
        lines = [f"📊 Tuần này: {total} bài đăng"]
        lines.append(f"• Engagement trung bình: {avg_eng}")
        if pillars:
            best = max(pillars, key=lambda p: p.get("avg_engagement", 0))
            worst = min(pillars, key=lambda p: p.get("avg_engagement", 0))
            lines.append(f"• Pillar mạnh nhất: {best['pillar']} (Ø{best['avg_engagement']:.0f})")
            lines.append(f"• Pillar yếu nhất: {worst['pillar']} (Ø{worst['avg_engagement']:.0f})")
        if recs:
            lines.append(f"• Gợi ý: {recs[0]}")
        return "\n".join(lines)
