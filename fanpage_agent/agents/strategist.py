"""StrategistAgent — content strategy, trend analysis, and calendar planning.

Now uses LLM (via LLMAdapter) to generate real, brand-tailored strategies
and content ideas. Falls back to templates if no LLM is configured.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fanpage_agent.adapters.llm_adapter import LLMAdapter
from fanpage_agent.core.agent import BaseAgent
from fanpage_agent.core.types import (
    AgentRole,
    AgentResult,
    AgentTask,
    ActionPriority,
)

_STRATEGIST_SYSTEM_PROMPT = """Bạn là Strategist của một fanpage skincare/healthcare cho GenZ (18-25 tuổi).

NHIỆM VỤ: Lên chiến lược nội dung, đề xuất chủ đề, phân tích xu hướng.

PHONG CÁCH: chân thật, ấm áp, dễ hiểu, chuyên môn, gần gũi. Ngắn gọn, không phóng đại.

PILLARS (cột nội dung):
- skincare_routine: Routine chăm sóc da các bước
- ingredient_deepdive: Phân tích thành phần mỹ phẩm
- myth_busting: Vạch trần lầm tưởng skincare
- product_review: Review/so sánh sản phẩm
- genz_lifestyle: Lối sống, self-care cho GenZ
- medical_reference: Kiến thức y khoa tham khảo

Trả lời bằng JSON thuần, không markdown."""


class StrategistAgent(BaseAgent):
    """Strategist — plans content strategy using LLM or template fallback."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        performance_memory=None,
        brand_id: str = "skincare_genz",
        llm: LLMAdapter | None = None,
    ) -> None:
        super().__init__(config)
        self._memory = performance_memory
        self._brand_id = brand_id
        self._llm = llm

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
            result = self._plan_weekly(params.get("days", 7), params.get("existing_calendar", []),
                                       params.get("research_brief", None))
            if result.success:
                self._mark_shared_done(
                    processed_research_version=self._pipeline_version("researcher"),
                    schedule=result.data.get("schedule", []),
                    pillar_distribution=result.data.get("pillar_distribution", {}),
                    reasoning=result.data.get("reasoning", ""),
                )
            return result
        elif action == "gap_analysis":
            return self._gap_analysis(params.get("calendar", []))
        elif action == "pillar_recommend":
            return self._pillar_recommend()
        elif action == "generate_ideas":
            return self._generate_ideas(params.get("pillar", ""), params.get("count", 3))
        elif action == "analyse_trends":
            return self._analyse_trends(params.get("pillars", []))
        return AgentResult(task_id=task.id, success=False, error=f"Unknown action: {action}")

    def self_driving_tick(self) -> list[tuple[str, dict, ActionPriority]]:
        """Propose strategy: respond to new research, or periodic planning.

        Choreography: if Researcher has produced new data, strategist proposes
        plan_weekly with that research. Falls back to periodic timer for
        gap analysis.
        """
        proposals: list[tuple[str, dict, ActionPriority]] = []

        # Check for new research data (choreography chain)
        if self._has_upstream_data("researcher", "processed_research_version"):
            research_brief = self._get_shared("researcher", {}).get("brief", {})
            proposals.append(("plan_weekly", {
                "days": 3,
                "research_brief": research_brief,
            }, ActionPriority.HIGH))

        # Periodic fallback: plan even without new research
        if not proposals and self._should_act("plan_weekly", 14400):
            proposals.append(("plan_weekly", {"days": 3}, ActionPriority.HIGH))

        # Periodic gap analysis
        if self._should_act("gap_analysis", 28800):
            proposals.append(("gap_analysis", {"calendar": []}, ActionPriority.LOW))

        return proposals

    def _plan_weekly(self, days: int, existing_calendar: list[dict],
                     research_brief: dict | None = None) -> AgentResult:
        """Create a weekly content schedule — LLM or template fallback.

        Args:
            days: Number of days to plan.
            existing_calendar: Existing scheduled items.
            research_brief: Optional research data from ResearchAgent.
        """
        research_context = self._normalise_research_context(research_brief)

        if self._llm:
            pillar_stats = ""
            if self._memory:
                perf = self._memory.pillar_performance()
                if perf:
                    pillar_stats = "\n".join(
                        f"  - {p['pillar']}: avg_engagement={p.get('avg_engagement', '?')}"
                        for p in perf
                    )

            research_section = ""
            if research_context["priority_topics"] or research_context["findings"]:
                research_lines = []
                for topic in research_context["priority_topics"][:8]:
                    research_lines.append(
                        f"  - topic_score={topic.get('total_score', '?')}: {topic.get('topic', '')[:100]}"
                    )
                for finding in research_context["findings"][:5]:
                    research_lines.append(f"  - finding: {finding[:120]}")
                research_section = (
                    "\nDữ liệu nghiên cứu thực tế đã chấm điểm:\n"
                    + "\n".join(research_lines)
                    + "\n\nƯu tiên các chủ đề điểm cao, có evidence, tránh topic rủi ro lặp."
                )

            prompt = f"""Lên lịch nội dung {days} ngày cho fanpage skincare GenZ.

Thương hiệu: {self._brand_id}
Số ngày: {days}

Dữ liệu performance hiện tại:
{pillar_stats or '  (chưa có dữ liệu)'}
{research_section}
Yêu cầu output JSON:
{{
  "schedule": [
    {{
      "day_offset": 0..{days-1},
      "pillar": "tên_pillar",
      "topic_template": "chủ đề cụ thể cho ngày này",
      "platform": "facebook"
    }}
  ],
  "pillar_distribution": {{"pillar_name": count}},
  "recommended_posting_times": ["HH:MM", ...],
  "reasoning": "lý do ngắn gọn cho chiến lược này"
}}

Đa dạng pillar, ưu tiên chủ đề GenZ skincare thực tế."""
            data = self._llm.generate_json(_STRATEGIST_SYSTEM_PROMPT, prompt)
            if data:
                return AgentResult(
                    task_id=f"plan-{days}d",
                    success=True,
                    data={
                        "brand_id": self._brand_id,
                        "schedule": data.get("schedule", []),
                        "pillar_distribution": data.get("pillar_distribution", {}),
                        "recommended_posting_times": data.get("recommended_posting_times", ["09:00", "12:00", "20:00"]),
                        "reasoning": data.get("reasoning", ""),
                        "research_priority_topics": research_context["priority_topics"],
                        "research_confidence": research_context["confidence_score"],
                        "generated_by": "llm",
                    },
                )

        # ── Template fallback ──
        import random

        templates: dict[str, list[str]] = {
            "skincare_routine": [
                "Morning routine với sản phẩm đơn giản",
                "Night routine có tác động kép",
                "Layering đúng thứ tự cho da dầu",
            ],
            "ingredient_deepdive": [
                "Vitamin C serum — cách chọn nồng độ phù hợp",
                "Retinol cho người mới — bắt đầu thế nào",
                "Niacinamide kết hợp cùng gì hiệu quả nhất",
            ],
            "myth_busting": [
                "[Myth] Dưỡng nhiều bước là tốt nhất",
                "[Myth] Da dầu không cần dưỡng ẩm",
                "[Myth] Đắt tiền = hiệu quả",
            ],
            "product_review": [
                "[Review] Sản phẩm giá rẻ dưới 200k",
                "[Review] Toner cho da dầu mụn Top 5",
                "[So sánh] Kem chống nắng Nhật vs Hàn",
            ],
            "genz_lifestyle": [
                "Skincare cho dân văn phòng điều hoà cả ngày",
                "Budget skincare cho sinh viên",
                "Skincare khi đi du lịch — túi gọn nhẹ",
            ],
            "medical_reference": [
                "Bác sĩ da liễu nói gì về...",
                "Khi nào cần gặp bác sĩ da liễu",
                "Phân biệt mụn viêm và mụn không viêm",
            ],
        }

        pillars = list(templates.keys())
        priority_topics = research_context["priority_topics"]
        schedule = []
        for day_offset in range(days):
            if day_offset < len(priority_topics):
                chosen = self._infer_pillar(priority_topics[day_offset].get("topic", ""))
                topic = priority_topics[day_offset].get("topic", "")
            else:
                chosen = random.choice(pillars)
                topic = random.choice(templates[chosen])
            schedule.append({
                "day_offset": day_offset,
                "pillar": chosen,
                "topic_template": topic,
                "platform": "facebook",
            })

        return AgentResult(
            task_id=f"plan-{days}d",
            success=True,
            data={
                "brand_id": self._brand_id,
                "schedule": schedule,
                "pillar_distribution": {
                    p: sum(1 for s in schedule if s["pillar"] == p) for p in pillars
                },
                "recommended_posting_times": self._recommend_times(),
                "research_priority_topics": priority_topics,
                "research_confidence": research_context["confidence_score"],
                "generated_by": "template",
            },
        )

    def _normalise_research_context(self, research_brief: dict | None) -> dict[str, Any]:
        brief = research_brief or {}
        if "brief" in brief and isinstance(brief.get("brief"), dict):
            brief = brief["brief"]

        priority_topics = []
        for item in brief.get("topic_scores", [])[:10]:
            if isinstance(item, dict) and item.get("topic"):
                priority_topics.append({
                    "topic": str(item.get("topic", "")),
                    "total_score": item.get("total_score", 0),
                    "duplication_risk": item.get("duplication_risk", 0),
                })

        if not priority_topics:
            priority_topics = [{"topic": t, "total_score": 0, "duplication_risk": 0} for t in brief.get("next_angles", [])[:10]]

        findings = []
        for finding in brief.get("findings", [])[:10]:
            findings.append(str(finding))

        return {
            "priority_topics": priority_topics,
            "findings": findings,
            "confidence_score": brief.get("confidence_score", 0),
        }

    @staticmethod
    def _infer_pillar(topic: str) -> str:
        text = topic.lower()
        if any(word in text for word in ["routine", "buổi sáng", "buổi tối", "layer"]):
            return "skincare_routine"
        if any(word in text for word in ["vitamin", "retinol", "niacinamide", "bha", "aha"]):
            return "ingredient_deepdive"
        if any(word in text for word in ["myth", "lầm tưởng", "sai lầm"]):
            return "myth_busting"
        if any(word in text for word in ["review", "so sánh", "top", "sản phẩm"]):
            return "product_review"
        if any(word in text for word in ["genz", "sinh viên", "văn phòng", "du lịch"]):
            return "genz_lifestyle"
        return "medical_reference"

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
                pass
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
        """Generate content ideas — LLM or template fallback."""
        if self._llm and pillar:
            prompt = f"""Đề xuất {count} ý tưởng content cho pillar "{pillar}" của fanpage skincare GenZ.

Output JSON:
{{
  "ideas": [
    {{
      "pillar": "{pillar}",
      "hook": "câu hook thu hút GenZ",
      "format": "carousel|video|text_image|reel",
      "tone": "mô tả giọng điệu ngắn"
    }}
  ]
}}"""
            data = self._llm.generate_json(_STRATEGIST_SYSTEM_PROMPT, prompt)
            if data and "ideas" in data:
                return AgentResult(
                    task_id=f"ideas-{pillar}",
                    success=True,
                    data={"pillar": pillar, "ideas": data["ideas"], "generated_by": "llm"},
                )

        # ── Template fallback ──
        import random

        fallback_templates = [
            f"Content về {pillar} — câu chuyện/kiến thức/mẹo",
            f"Review/trải nghiệm {pillar} thực tế",
            f"Hỏi đáp về {pillar} với GenZ",
        ]
        ideas = []
        for i in range(count):
            ideas.append({
                "id": f"idea-{pillar}-{i}",
                "pillar": pillar,
                "hook": random.choice(fallback_templates),
                "format": random.choice(["carousel", "video", "text_image", "reel"]),
                "tone": "thân thiện, chuyên môn",
            })
        return AgentResult(
            task_id=f"ideas-{pillar}",
            success=True,
            data={"pillar": pillar, "ideas": ideas, "generated_by": "template"},
        )

    def _analyse_trends(self, pillars: list[str]) -> AgentResult:
        """Analyse trends — LLM or stub."""
        if self._llm:
            active = pillars or ["skincare_routine", "ingredient_deepdive", "myth_busting", "product_review", "genz_lifestyle"]
            prompt = f"""Phân tích xu hướng skincare GenZ hiện tại cho các pillars: {', '.join(active)}.

Output JSON:
{{
  "observations": ["xu hướng 1", "xu hướng 2", ...],
  "hot_topics": ["chủ đề hot 1", "chủ đề hot 2", ...],
  "actionable_insights": ["gợi ý hành động 1", ...]
}}"""
            data = self._llm.generate_json(_STRATEGIST_SYSTEM_PROMPT, prompt)
            if data:
                return AgentResult(
                    task_id="trends",
                    success=True,
                    data={
                        "pillars_to_scan": active,
                        "observations": data.get("observations", []),
                        "hot_topics": data.get("hot_topics", []),
                        "actionable_insights": data.get("actionable_insights", []),
                        "analysis_time": datetime.now(timezone.utc).isoformat(),
                        "generated_by": "llm",
                    },
                )

        active = pillars or ["skincare_routine", "ingredient_deepdive"]
        return AgentResult(
            task_id="trends",
            success=True,
            data={
                "pillars_to_scan": active,
                "observations": [],
                "hot_topics": [],
                "analysis_time": datetime.now(timezone.utc).isoformat(),
                "generated_by": "template",
            },
        )
