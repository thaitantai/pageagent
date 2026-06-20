from __future__ import annotations

from typing import Any

from fanpage_agent.models import BrandProfile, CaptionPackage, CaptionVariant, ResearchBrief
from fanpage_agent.tools.content.verifier import VerifierTool
from fanpage_agent.tools.content.writer import WriterTool
from fanpage_agent.tools.publishing.planner import PlannerTool
from fanpage_agent.tools.publishing.telegram_formatter import TelegramFormatterTool


class DailyOpsTool:
    def __init__(
        self,
        planner: PlannerTool | None = None,
        writer: WriterTool | None = None,
        verifier: VerifierTool | None = None,
        formatter: TelegramFormatterTool | None = None,
    ) -> None:
        self.planner = planner or PlannerTool()
        self.writer = writer or WriterTool()
        self.verifier = verifier or VerifierTool()
        self.formatter = formatter or TelegramFormatterTool()

    def build_packet(
        self,
        profile: BrandProfile,
        run_date: str,
        store: object,
        days: int = 1,
        write_calendar: bool = False,
        research_brief: ResearchBrief | None = None,
        research_packet: Any | None = None,
    ) -> dict:
        plan = self.planner.plan_week(profile=profile, start_date=run_date, days=days, research_brief=research_brief)
        history = store.read_post_history(limit=30)
        plan_verification = self.verifier.verify_plan(profile, plan, history=history)
        handoff_policy = getattr(research_packet, "handoff_policy", {}) or {}
        max_safe_use = handoff_policy.get("max_safe_use") if isinstance(handoff_policy, dict) else None
        gate_blocks_writer = max_safe_use == "draft_questions_only"

        if write_calendar:
            store.append_plan(profile.brand_id, plan)

        primary_day = plan.days[0]
        if gate_blocks_writer:
            reasons = getattr(research_packet, "gate_reasons", []) or []
            reason_text = "; ".join(str(reason) for reason in reasons) or "Research chưa đủ an toàn."
            caption_package = CaptionPackage(
                topic=f"Research blocked: {primary_day.topic}",
                variants=[
                    CaptionVariant(
                        label="Research",
                        hook="Evidence Gate chặn draft claim mua hàng.",
                        caption=(
                            "Chỉ tạo checklist nghiên cứu, chưa tạo caption đăng công khai. "
                            f"Lý do: {reason_text}"
                        ),
                        cta="Bổ sung nguồn/evidence rồi chạy lại daily packet.",
                        tone_tags=["chuyên môn"],
                        visual_brief="Không tạo visual public cho đến khi ResearchPacket qua Evidence Gate.",
                    )
                ],
                dos=["Bổ sung tối thiểu 2 URL/source độc lập trước khi Writer viết claim."],
                donts=["Không publish hoặc đưa affiliate recommendation khi ResearchPacket bị blocked."],
            )
            caption_verification = self.verifier.verify_caption_package(profile, caption_package)
            caption_verification.passed = False
            caption_verification.issues.append("Evidence Gate blocked writer output")
        else:
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

        actions = ["review_research", "review_plan"]
        if gate_blocks_writer:
            actions.extend(["add_sources", "rerun_research"])
        else:
            actions.extend(["review_caption", "approve_or_revise"])

        payload = {
            "run_date": run_date,
            "calendar_id": f"{plan.plan_title}-1",
            "plan": plan_payload,
            "caption_package": caption_payload,
            "telegram_preview": {
                "plan_message": self.formatter.format_weekly_plan(plan_payload),
                "caption_message": self.formatter.format_caption_package(caption_payload),
            },
            "actions": actions,
        }
        if research_brief:
            payload["research_brief"] = research_brief.model_dump(mode="json")
        return payload
