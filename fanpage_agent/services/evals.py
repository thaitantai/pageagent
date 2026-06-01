from __future__ import annotations

from pathlib import Path

from fanpage_agent.adapters.llm_client import MockLLMClient
from fanpage_agent.models import BrandProfile, CaptionPackage, PlanDay, ResearchBrief, WeeklyPlan
from fanpage_agent.services.planner import PlannerService
from fanpage_agent.services.research import ResearchService
from fanpage_agent.services.verifier import VerifierService
from fanpage_agent.services.writer import WriterService


class EvalService:
    def __init__(self, llm_client: object | None = None) -> None:
        self.llm_client = llm_client or MockLLMClient()
        self.research = ResearchService()
        self.planner = PlannerService(llm_client=self.llm_client)
        self.writer = WriterService(llm_client=self.llm_client)
        self.verifier = VerifierService()

    def run_all(
        self,
        profile: BrandProfile,
        store: object,
        comment_csv: str | Path | None = None,
        campaign_notes_file: str | Path | None = None,
        start_date: str = "2026-06-20",
    ) -> dict:
        research_brief = self.research.build_brief(
            store=store,
            comment_csv=comment_csv,
            campaign_notes_file=campaign_notes_file,
        )
        checks = [
            self._eval_research(research_brief),
            self._eval_planner(profile, store, research_brief, start_date),
            self._eval_writer(profile),
            self._eval_verifier(profile),
        ]
        passed = sum(1 for item in checks if item["passed"])
        total = len(checks)
        failed = total - passed
        score = passed / total if total else 0.0
        return {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "score": score,
            },
            "checks": checks,
        }

    @staticmethod
    def _eval_research(brief: ResearchBrief) -> dict:
        passed = bool(brief.recommended_objectives and brief.frequent_questions)
        details: list[str] = []
        if brief.recommended_objectives:
            details.append(f"Recommended objective: {brief.recommended_objectives[0]}")
        else:
            details.append("Missing recommended objectives")
        if brief.frequent_questions:
            details.append(f"Frequent question captured: {brief.frequent_questions[0]}")
        else:
            details.append("Missing frequent questions")
        if brief.campaign_focus:
            details.append(f"Campaign focus present: {brief.campaign_focus[0]}")
        return {"name": "research", "passed": passed, "details": details}

    def _eval_planner(self, profile: BrandProfile, store: object, brief: ResearchBrief, start_date: str) -> dict:
        plan = self.planner.plan_week(profile=profile, start_date=start_date, days=2, research_brief=brief)
        verification = self.verifier.verify_plan(profile, plan, history=store.read_post_history(limit=30))
        has_campaign_focus_note = self._mentions_campaign_focus(plan.strategy_notes, brief)
        passed = len(plan.days) == 2 and verification.passed and has_campaign_focus_note
        details = [
            f"Generated {len(plan.days)} plan days",
            f"Verification passed: {verification.passed}",
            f"Campaign focus applied: {has_campaign_focus_note}",
        ]
        if plan.strategy_notes:
            details.append(f"Strategy note: {plan.strategy_notes[-1]}")
        return {"name": "planner", "passed": passed, "details": details}

    def _eval_writer(self, profile: BrandProfile) -> dict:
        objective = self._pick_eval_objective(profile)
        package = self.writer.write_caption(
            profile=profile,
            topic="Da thiếu nước thì nên bắt đầu treatment từ đâu?",
            pillar=profile.content_pillars[0].pillar_name,
            objective=objective,
            fmt=profile.content_pillars[0].allowed_formats[0] if profile.content_pillars[0].allowed_formats else "post_short",
        )
        verification = self.verifier.verify_caption_package(profile, package)
        expected_cta = self._expected_cta(profile, objective)
        has_expected_cta = any(variant.cta == expected_cta for variant in package.variants)
        passed = verification.passed and bool(package.variants) and has_expected_cta
        details = [
            f"Generated {len(package.variants)} variants",
            f"CTA matched objective: {has_expected_cta}",
            f"Verification passed: {verification.passed}",
        ]
        return {"name": "writer", "passed": passed, "details": details}

    @staticmethod
    def _mentions_campaign_focus(strategy_notes: list[str], brief: ResearchBrief) -> bool:
        joined = " ".join(strategy_notes).lower()
        if "campaign focus" in joined or "campaign" in joined:
            return True
        return any(focus.lower() in joined for focus in brief.campaign_focus)

    def _eval_verifier(self, profile: BrandProfile) -> dict:
        broken_plan = WeeklyPlan(
            plan_title="eval-bad-plan",
            days=[
                PlanDay(
                    date="2026-06-20",
                    pillar=profile.content_pillars[0].pillar_name,
                    objective=self._pick_eval_objective(profile),
                    topic="Eval topic",
                    angle="Eval angle",
                    format=profile.content_pillars[0].allowed_formats[0] if profile.content_pillars[0].allowed_formats else "post_short",
                    hook="Eval hook",
                    cta="",
                    visual_brief="Eval visual",
                    risk_notes=[],
                )
            ],
            strategy_notes=[],
            gaps_or_assumptions=[],
        )
        result = self.verifier.verify_plan(profile, broken_plan, history=[])
        passed = (not result.passed) and any("missing cta" in issue.lower() for issue in result.issues)
        details = result.issues or ["Verifier did not report issues"]
        return {"name": "verifier", "passed": passed, "details": details}

    @staticmethod
    def _pick_eval_objective(profile: BrandProfile) -> str:
        for item in profile.approved_cta_patterns:
            if item.objective:
                return item.objective
        return profile.fanpage_goals[0] if profile.fanpage_goals else "reach"

    @staticmethod
    def _expected_cta(profile: BrandProfile, objective: str) -> str:
        for item in profile.approved_cta_patterns:
            if item.objective == objective:
                return item.cta_text
        return profile.approved_cta_patterns[0].cta_text if profile.approved_cta_patterns else ""
