from __future__ import annotations

from fanpage_agent.models import BrandProfile, ResearchBrief
from fanpage_agent.services.planner import PlannerService
from fanpage_agent.services.telegram_formatter import TelegramFormatterService
from fanpage_agent.services.verifier import VerifierService
from fanpage_agent.services.writer import WriterService


class DailyOpsService:
    def __init__(
        self,
        planner: PlannerService | None = None,
        writer: WriterService | None = None,
        verifier: VerifierService | None = None,
        formatter: TelegramFormatterService | None = None,
    ) -> None:
        self.planner = planner or PlannerService()
        self.writer = writer or WriterService()
        self.verifier = verifier or VerifierService()
        self.formatter = formatter or TelegramFormatterService()

    def build_packet(
        self,
        profile: BrandProfile,
        run_date: str,
        store: object,
        days: int = 1,
        write_calendar: bool = False,
        research_brief: ResearchBrief | None = None,
    ) -> dict:
        plan = self.planner.plan_week(profile=profile, start_date=run_date, days=days, research_brief=research_brief)
        history = store.read_post_history(limit=30)
        plan_verification = self.verifier.verify_plan(profile, plan, history=history)

        if write_calendar:
            store.append_plan(profile.brand_id, plan)

        primary_day = plan.days[0]
        caption_package = self.writer.write_caption(
            profile=profile,
            topic=primary_day.topic,
            pillar=primary_day.pillar,
            objective=primary_day.objective,
            fmt=primary_day.format,
        )
        caption_verification = self.verifier.verify_caption_package(profile, caption_package)

        plan_payload = plan.model_dump(mode="json")
        plan_payload["verification"] = plan_verification.model_dump(mode="json")
        caption_payload = caption_package.model_dump(mode="json")
        caption_payload["verification"] = caption_verification.model_dump(mode="json")

        payload = {
            "run_date": run_date,
            "calendar_id": f"{plan.plan_title}-1",
            "plan": plan_payload,
            "caption_package": caption_payload,
            "telegram_preview": {
                "plan_message": self.formatter.format_weekly_plan(plan_payload),
                "caption_message": self.formatter.format_caption_package(caption_payload),
            },
            "actions": [
                "review_research",
                "review_plan",
                "review_caption",
                "approve_or_revise",
            ],
        }
        if research_brief:
            payload["research_brief"] = research_brief.model_dump(mode="json")
        return payload
