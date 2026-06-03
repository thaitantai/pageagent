"""StrategistAgent — content strategy, trend analysis, and calendar planning."""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fanpage_agent_v2.core.agent import BaseAgent
from fanpage_agent_v2.core.types import (
    AgentRole,
    AgentResult,
    AgentTask,
    ActionPriority,
    ContentPackage,
    ContentVariant,
    PerformancePattern,
)


class StrategistAgent(BaseAgent):
    """Strategist — plans content strategy based on trends and learned patterns.

    Capabilities:
    - analyse_trends: Scan for trending topics and hooks
    - plan_weekly: Create weekly content calendar with pillar mix
    - gap_analysis: Find calendar gaps and suggest fills
    - pillar_recommend: Recommend pillar balance based on performance
    - generate_ideas: Generate N content ideas for a given pillar
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        performance_memory=None,
        brand_id: str = "skincare_genz",
    ) -> None:
        super().__init__(config)
        self._memory = performance_memory
        self._brand_id = brand_id
        self._pillar_templates: dict[str, list[str]] = (config or {}).get("pillar_templates", {
            "skincare_routine": [
                "Morning routine với sản phẩm đơn giản",
                "Night routine có tác động kép",
                "Layering đúng thứ tự cho da dầu",
                "Skincare minimalism vs maximalism",
            ],
            "ingredient_deepdive": [
                "Vitamin C serum — cách chọn nồng độ phù hợp",
                "Retinol cho người mới — bắt đầu thế nào",
                "Niacinamide kết hợp cùng gì hiệu quả nhất",
                "SPF hoá học vs vật lý — cái nào tốt hơn",
                "Peptide có thực sự cần thiết?",
            ],
            "myth_busting": [
                "[Myth] Dưỡng nhiều bước là tốt nhất",
                "[Myth] Da dầu không cần dưỡng ẩm",
                "[Myth] Đắt tiền = hiệu quả",
                "[Myth] Chống nắng chỉ cần khi trời nắng",
            ],
            "product_review": [
                "[Review] Sản phẩm giá rẻ dưới 200k",
                "[Review] Toner cho da dầu mụn Top 5",
                "[So sánh] Kem chống nắng Nhật vs Hàn",
                "[Review] Mặt nạ giấy đáng thử nhất 2026",
            ],
            "genz_lifestyle": [
                "Skincare cho dân văn phòng điều hoà cả ngày",
                "Budget skincare cho sinh viên",
                "Skincare khi đi du lịch — túi gọn nhẹ",
                "Self-care routine tối giản cho GenZ",
            ],
            "medical_reference": [
                "Bác sĩ da liễu nói gì về...",
                "Khi nào cần gặp bác sĩ da liễu",
                "Phân biệt mụn viêm và mụn không viêm",
                "Dấu hiệu da cần đổi routine",
            ],
        })

    @property
    def role(self) -> AgentRole:
        return AgentRole.STRATEGIST

    @property
    def capabilities(self) -> list[str]:
        return [
            "analyse_trends",
            "plan_weekly",
            "gap_analysis",
            "pillar_recommend",
            "generate_ideas",
        ]

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params

        if action == "plan_weekly":
            return self._plan_weekly(params.get("days", 7), params.get("existing_calendar", []))
        elif action == "gap_analysis":
            return self._gap_analysis(params.get("calendar", []))
        elif action == "pillar_recommend":
            return self._pillar_recommend()
        elif action == "generate_ideas":
            return self._generate_ideas(params.get("pillar", ""), params.get("count", 3))
        elif action == "analyse_trends":
            return self._analyse_trends(params.get("pillars", []))
        return AgentResult(task_id=task.id, success=False, error=f"Unknown action: {action}")

    def _plan_weekly(self, days: int, existing_calendar: list[dict]) -> AgentResult:
        """Create a weekly content schedule with balanced pillars."""
        # Get pillar performance from memory
        pillar_perf: dict[str, float] = {}
        if self._memory:
            perf = self._memory.pillar_performance()
            for p in perf:
                pillar_perf[p["pillar"]] = p.get("avg_engagement", 0)

        # Pillar weighting — prefer underperforming pillars to test
        pillars = list(self._pillar_templates.keys())
        weights: list[float] = []
        for p in pillars:
            if p in pillar_perf:
                # Lower weight for high performers (already doing well)
                weights.append(max(0.3, 1.0 - (pillar_perf[p] / 100)))
            else:
                weights.append(1.0)

        # Generate schedule
        schedule = []
        for day_offset in range(days):
            chosen = random.choices(pillars, weights=weights, k=1)[0]
            template = random.choice(self._pillar_templates[chosen])

            schedule.append({
                "day_offset": day_offset,
                "pillar": chosen,
                "topic_template": template,
                "platform": "facebook",
            })

        return AgentResult(
            task_id=f"plan-{days}d",
            success=True,
            data={
                "brand_id": self._brand_id,
                "schedule": schedule,
                "pillar_distribution": {
                    p: sum(1 for s in schedule if s["pillar"] == p)
                    for p in pillars
                },
                "recommended_posting_times": self._recommend_times(),
            },
        )

    def _recommend_times(self) -> list[str]:
        """Return optimal posting times based on memory."""
        if not self._memory:
            return ["09:00", "12:00", "20:00"]
        top = self._memory.get_top_patterns(pattern_type="posting_hour", limit=3)
        return [p.value for p in top] if top else ["09:00", "12:00", "20:00"]

    def _gap_analysis(self, calendar: list[dict]) -> AgentResult:
        """Identify gaps in the content calendar."""
        gaps = []
        for i, item in enumerate(calendar):
            if i < len(calendar) - 1:
                # Check for gaps > 24h
                pass  # Would check timestamps
        return AgentResult(
            task_id="gap-analysis",
            success=True,
            data={"gaps": gaps, "total_gap_days": len(gaps)},
        )

    def _pillar_recommend(self) -> AgentResult:
        """Recommend pillar balance based on performance data."""
        recs = []
        if self._memory:
            perf = self._memory.pillar_performance()
            if perf:
                best = perf[0]
                worst = perf[-1]
                recs.append(f"Ưu tiên pillar '{best['pillar']}' (Ø{best['avg_engagement']:.0f} eng)")
                if worst["avg_engagement"] < 5:
                    recs.append(f"Cân nhắc giảm tần suất pillar '{worst['pillar']}'")

        patterns = []
        if self._memory:
            patterns = [
                {"type": p.pattern_type, "value": p.value, "avg_engagement": p.avg_engagement}
                for p in self._memory.get_top_patterns(limit=5)
            ]

        return AgentResult(
            task_id="pillar-recommend",
            success=True,
            data={"recommendations": recs, "top_patterns": patterns},
        )

    def _generate_ideas(self, pillar: str, count: int = 3) -> AgentResult:
        """Generate content ideas for a specific pillar."""
        templates = self._pillar_templates.get(pillar, [
            f"Content về {pillar} — câu chuyện/kiến thức/mẹo"
        ])
        ideas = []
        for i in range(count):
            ideas.append({
                "id": f"idea-{pillar}-{i}",
                "pillar": pillar,
                "hook": random.choice(templates),
                "format": random.choice(["carousel", "video", "text_image", "reel"]),
                "tone": "thân thiện, chuyên môn",
            })
        return AgentResult(
            task_id=f"ideas-{pillar}",
            success=True,
            data={"pillar": pillar, "ideas": ideas},
        )

    def _analyse_trends(self, pillars: list[str]) -> AgentResult:
        """Analyse trends — stub that returns structure for LLM to fill."""
        active = pillars or list(self._pillar_templates.keys())
        return AgentResult(
            task_id="trends",
            success=True,
            data={
                "pillars_to_scan": active,
                "observations": [],
                "hot_topics": [],
                "analysis_time": datetime.now(timezone.utc).isoformat(),
            },
        )
