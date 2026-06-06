import unittest

from fanpage_agent.models import AnalyticsReport, AnalyticsSummary, CaptionPackage, CaptionVariant, PlanDay, PostMetric, WeeklyPlan
from fanpage_agent.services.telegram_formatter import TelegramFormatterService


class TelegramFormatterServiceTest(unittest.TestCase):
    def test_format_weekly_plan_contains_header_and_verification(self) -> None:
        plan = WeeklyPlan(
            plan_title="weekly-plan-brand_abc-2026-06-08",
            days=[
                PlanDay(
                    date="2026-06-08",
                    pillar="education",
                    objective="reach",
                    topic="Routine cấp ẩm cho da",
                    angle="checklist 3 bước",
                    format="post_short",
                    hook="3 bước cấp ẩm bạn nên biết",
                    cta="Lưu lại khi cần",
                    visual_brief="Layout checklist",
                    risk_notes=[],
                )
            ],
            strategy_notes=["Giữ mix pillar"],
            gaps_or_assumptions=[],
        )
        payload = plan.model_dump(mode="json")
        payload["verification"] = {"passed": True, "issues": []}
        message = TelegramFormatterService().format_weekly_plan(payload)

        self.assertIn("Weekly Plan", message)
        self.assertIn("Routine cấp ẩm cho da", message)
        self.assertIn("verification: PASS", message)

    def test_format_caption_package_contains_variants(self) -> None:
        package = CaptionPackage(
            topic="Routine cấp ẩm cho da",
            variants=[
                CaptionVariant(
                    label="A",
                    hook="Hook A",
                    caption="Caption A",
                    cta="CTA A",
                    tone_tags=["ấm", "rõ"],
                    visual_brief="Visual A",
                )
            ],
            dos=["Giữ câu ngắn"],
            donts=["Không claim tuyệt đối"],
        )
        payload = package.model_dump(mode="json")
        payload["verification"] = {"passed": True, "issues": []}
        message = TelegramFormatterService().format_caption_package(payload)

        self.assertIn("Caption Package", message)
        self.assertIn("Variant A", message)
        self.assertIn("Caption A", message)

    def test_format_weekly_report_contains_summary_and_top_post(self) -> None:
        payload = {
            "summary": {
                "total_posts": 3,
                "total_reach": 3950,
                "total_engagements": 282,
                "total_leads": 24,
                "avg_engagement_rate": 0.0714,
            },
            "top_post": {
                "topic": "Routine phục hồi da sau treatment",
                "pillar": "trust",
                "objective": "lead",
                "reach": 1800,
                "engagements": 120,
                "leads": 11,
            },
            "recommendations": ["Tăng nội dung trust cho nhóm treatment."],
        }

        rendered = TelegramFormatterService().format_weekly_report(payload)

        self.assertIn("Weekly Report", rendered)
        self.assertIn("Routine phục hồi da sau treatment", rendered)
        self.assertIn("Tăng nội dung trust", rendered)

    def test_format_community_triage_contains_summary_and_top_priority_items(self) -> None:
        payload = {
            "summary": {
                "total_items": 3,
                "by_category": {"lead": 1, "complaint": 1, "spam": 1},
                "by_priority": {"high": 1, "urgent": 1, "low": 1},
                "escalation_count": 2,
                "approval_required_count": 3,
            },
            "items": [
                {
                    "category": "lead",
                    "priority": "high",
                    "source": "inbox",
                    "message": "Chi phí soi da là bao nhiêu?",
                    "recommended_action": "reply_and_route_to_inbox",
                    "escalation_required": True,
                },
                {
                    "category": "complaint",
                    "priority": "urgent",
                    "source": "comment",
                    "message": "Mình bị kích ứng sau treatment, cần hỗ trợ gấp",
                    "recommended_action": "escalate_to_human",
                    "escalation_required": True,
                },
                {
                    "category": "spam",
                    "priority": "low",
                    "source": "comment",
                    "message": "Xem ngay http://spam.example để nhận quà",
                    "recommended_action": "ignore_or_hide",
                    "escalation_required": False,
                },
            ],
        }

        rendered = TelegramFormatterService().format_community_triage(payload)

        self.assertIn("Community Triage", rendered)
        self.assertIn("total items: 3", rendered)
        self.assertIn("lead: 1", rendered)
        self.assertIn("complaint: 1", rendered)
        self.assertIn("urgent", rendered.lower())
        self.assertIn("Chi phí soi da là bao nhiêu?", rendered)

    def test_format_approval_queue_contains_pending_items_and_draft_refs(self) -> None:
        payload = {
            "summary": {
                "total_items": 2,
                "by_status": {"planned": 2},
                "by_approval_status": {"pending": 2},
                "by_pillar": {"education": 1, "trust": 1},
            },
            "items": [
                {
                    "calendar_id": "cal-1",
                    "date": "2026-06-20",
                    "topic": "Routine sáng cho da dầu",
                    "status": "planned",
                    "approval_status": "pending",
                    "pillar": "education",
                    "draft_caption_ref": "artifacts/captions/cal-1.json",
                }
            ],
        }

        rendered = TelegramFormatterService().format_approval_queue(payload)

        self.assertIn("Approval Queue", rendered)
        self.assertIn("total items: 2", rendered)
        self.assertIn("cal-1", rendered)
        self.assertIn("artifacts/captions/cal-1.json", rendered)
        self.assertIn("approve-caption --calendar-id cal-1", rendered)
        self.assertIn("--caption-file artifacts/captions/cal-1.json", rendered)
        self.assertIn("reject-caption --calendar-id cal-1", rendered)

    def test_format_approval_audit_contains_overdue_items_and_actions(self) -> None:
        payload = {
            "summary": {
                "total_items": 3,
                "pending": 2,
                "overdue_pending": 1,
                "approved": 1,
                "rejected": 0,
                "sla_days": 2,
                "as_of": "2026-06-24",
            },
            "overdue_items": [
                {
                    "calendar_id": "cal-old",
                    "topic": "Old pending caption",
                    "date": "2026-06-20",
                    "days_pending": 4,
                    "draft_caption_ref": "artifacts/captions/cal-old.json",
                }
            ],
        }

        rendered = TelegramFormatterService().format_approval_audit(payload)

        self.assertIn("Approval Audit", rendered)
        self.assertIn("overdue pending: 1", rendered)
        self.assertIn("cal-old", rendered)
        self.assertIn("days pending: 4", rendered)
        self.assertIn("approve-caption --calendar-id cal-old", rendered)

    def test_format_approval_audit_is_compact_and_next_action_focused(self) -> None:
        payload = {
            "summary": {
                "total_items": 3,
                "pending": 2,
                "overdue_pending": 1,
                "approved": 1,
                "rejected": 0,
                "sla_days": 2,
                "as_of": "2026-06-24",
            },
            "overdue_items": [
                {
                    "calendar_id": "cal-old",
                    "topic": "Old pending caption",
                    "date": "2026-06-20",
                    "days_pending": 4,
                    "draft_caption_ref": "artifacts/captions/cal-old.json",
                }
            ],
        }

        rendered = TelegramFormatterService().format_approval_audit(payload)

        self.assertLessEqual(len(rendered.splitlines()), 9)
        self.assertIn("Next:", rendered)
        self.assertIn("approve-caption --calendar-id cal-old", rendered)
        self.assertNotIn("actions:", rendered)
        self.assertNotIn("total items:", rendered)

    def test_format_approved_triage_replies_contains_copy_paste_instructions(self) -> None:
        payload = {
            "summary": {
                "total_items": 1,
                "by_status": {"approved": 1},
                "by_priority": {"high": 1},
            },
            "items": [
                {
                    "triage_id": "triage-1",
                    "source": "inbox",
                    "message": "Chi phí soi da là bao nhiêu?",
                    "priority": "high",
                    "category": "lead",
                    "draft_reply": "Dạ bạn inbox để bên mình tư vấn chi tiết hơn nhé.",
                    "assigned_to": "closer-1",
                }
            ],
        }

        rendered = TelegramFormatterService().format_approved_triage_replies(payload)

        self.assertIn("Approved Triage Replies", rendered)
        self.assertIn("triage-1", rendered)
        self.assertIn("Chi phí soi da là bao nhiêu?", rendered)
        self.assertIn("draft_reply:", rendered)
        self.assertIn("mark-triage-reply-sent", rendered)

    def test_format_operator_digest_contains_three_operational_queues(self) -> None:
        payload = {
            "summary": {
                "pending_captions": 1,
                "approved_replies": 1,
                "metrics_backlog": 1,
            },
            "approval_queue": {
                "items": [
                    {"calendar_id": "cal-1", "topic": "Routine sáng", "draft_caption_ref": "artifacts/captions/cal-1.json"}
                ]
            },
            "approved_replies": {
                "items": [
                    {"triage_id": "triage-1", "message": "Chi phí?", "draft_reply": "Dạ bạn inbox nhé", "priority": "high"}
                ]
            },
            "metrics_backlog": {
                "items": [
                    {"calendar_id": "cal-2", "topic": "Routine tối", "published_at": "2026-06-25T10:00:00"}
                ]
            },
        }

        rendered = TelegramFormatterService().format_operator_digest(payload)

        self.assertIn("Daily Operator Digest", rendered)
        self.assertIn("Pending captions: 1", rendered)
        self.assertIn("Approved replies: 1", rendered)
        self.assertIn("Metrics backlog: 1", rendered)
        self.assertIn("cal-1", rendered)
        self.assertIn("approve-caption --calendar-id cal-1", rendered)
        self.assertIn("triage-1", rendered)
        self.assertIn("cal-2", rendered)

    def test_format_operator_digest_is_compact_and_next_action_focused(self) -> None:
        payload = {
            "summary": {
                "pending_captions": 1,
                "approved_replies": 1,
                "metrics_backlog": 1,
            },
            "approval_queue": {
                "items": [
                    {"calendar_id": "cal-1", "topic": "Routine sáng", "draft_caption_ref": "artifacts/captions/cal-1.json"}
                ]
            },
            "approved_replies": {
                "items": [
                    {"triage_id": "triage-1", "message": "Chi phí?", "draft_reply": "Dạ bạn inbox nhé", "priority": "high"}
                ]
            },
            "metrics_backlog": {
                "items": [
                    {"calendar_id": "cal-2", "topic": "Routine tối", "published_at": "2026-06-25T10:00:00"}
                ]
            },
        }

        rendered = TelegramFormatterService().format_operator_digest(payload)

        self.assertLessEqual(len(rendered.splitlines()), 12)
        self.assertIn("Next:", rendered)
        self.assertIn("approve-caption --calendar-id cal-1", rendered)
        self.assertIn("reply triage-1", rendered)
        self.assertIn("record metrics for cal-2", rendered)
        self.assertNotIn("actions:", rendered)
        self.assertNotIn("draft_reply:", rendered)

    def test_format_metrics_backlog_contains_pending_metric_items(self) -> None:
        payload = {
            "summary": {
                "total_items": 1,
                "by_status": {"published": 1},
                "by_approval_status": {"approved": 1},
                "by_pillar": {"education": 1},
            },
            "items": [
                {
                    "calendar_id": "cal-2",
                    "date": "2026-06-28",
                    "topic": "Routine phục hồi cuối ngày",
                    "status": "published",
                    "approval_status": "approved",
                    "pillar": "education",
                    "published_at": "2026-06-28T10:00:00",
                    "permalink": "https://example.com/post-2",
                    "reach": "0",
                    "engagement_rate": "0.0",
                }
            ],
        }

        rendered = TelegramFormatterService().format_metrics_backlog(payload)

        self.assertIn("Metrics Backlog", rendered)
        self.assertIn("total items: 1", rendered)
        self.assertIn("cal-2", rendered)
        self.assertIn("https://example.com/post-2", rendered)

    def test_format_research_brief_surfaces_quality_and_source_insights(self) -> None:
        payload = {
            "confidence_score": 0.82,
            "recommended_objectives": ["lead"],
            "source_documents": [
                {
                    "source_id": "derm-01",
                    "name": "Derm Clinic Blog",
                    "trust_score": 0.95,
                }
            ],
            "evidence": [
                {
                    "evidence_type": "source_claim",
                    "claim": "Khach hang can soi da truoc treatment.",
                    "source": "Derm Clinic Blog",
                    "confidence": 0.9,
                }
            ],
            "quality_warnings": ["Can them nguon doc lap."],
        }

        rendered = TelegramFormatterService().format_research_brief(payload)

        self.assertIn("confidence: 0.82", rendered)
        self.assertIn("sources: 1 | evidence: 1 | warnings: 1", rendered)
        self.assertIn("source-backed insights:", rendered)
        self.assertIn("Khach hang can soi da", rendered)
        self.assertIn("quality warnings:", rendered)

    def test_format_research_brief_accepts_research_packet_artifact(self) -> None:
        payload = {
            "packet_id": "rpkt-1",
            "brief": {
                "confidence_score": 0.76,
                "source_documents": [{"source_id": "faq", "name": "FAQ", "trust_score": 0.9}],
                "evidence": [{"evidence_type": "source_claim", "claim": "Khach hoi ve soi da.", "source": "FAQ"}],
            },
        }

        rendered = TelegramFormatterService().format_research_brief(payload)

        self.assertIn("confidence: 0.76", rendered)
        self.assertIn("sources: 1 | evidence: 1 | warnings: 0", rendered)
        self.assertIn("Khach hoi ve soi da", rendered)

    def test_format_research_brief_accepts_live_confidence_alias(self) -> None:
        payload = {
            "brief": {
                "confidence": 0.82,
                "source_documents": [{"source_id": "pilot", "title": "Pilot", "trust_score": 0.8}],
                "evidence": [{"evidence_type": "source_claim", "claim": "Pilot smoke ok.", "source": "Pilot"}],
                "quality_warnings": [{"code": "pilot", "message": "Human approval required."}],
            }
        }

        rendered = TelegramFormatterService().format_research_brief(payload)

        self.assertIn("confidence: 0.82", rendered)
        self.assertIn("sources: 1 | evidence: 1 | warnings: 1", rendered)
        self.assertIn("Pilot smoke ok", rendered)


if __name__ == "__main__":
    unittest.main()
