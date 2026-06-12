from __future__ import annotations

from fanpage_agent.adapters.llm import MockLLMClient
from fanpage_agent.models import BrandProfile, ContentStrategy, ResearchBrief, WeeklyPlan


class PlannerTool:
    def __init__(self, llm_client: object | None = None) -> None:
        self.llm_client = llm_client or MockLLMClient()

    def plan_week(
        self,
        profile: BrandProfile,
        start_date: str,
        days: int = 7,
        research_brief: ResearchBrief | None = None,
        strategy: ContentStrategy | None = None,
    ) -> WeeklyPlan:
        return self.llm_client.generate_weekly_plan(
            profile=profile,
            start_date=start_date,
            days=days,
            research_brief=research_brief,
            strategy=strategy,
        )
