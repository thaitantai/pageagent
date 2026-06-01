import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TelegramPreviewCliTest(unittest.TestCase):
    def test_preview_telegram_renders_plan_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = {
            "plan_title": "weekly-plan-brand_abc-2026-06-08",
            "days": [
                {
                    "date": "2026-06-08",
                    "pillar": "education",
                    "objective": "reach",
                    "topic": "Routine cấp ẩm cho da",
                    "angle": "checklist 3 bước",
                    "format": "post_short",
                    "hook": "3 bước cấp ẩm bạn nên biết",
                    "cta": "Lưu lại khi cần",
                    "visual_brief": "Layout checklist",
                    "risk_notes": [],
                }
            ],
            "strategy_notes": ["Giữ mix pillar"],
            "gaps_or_assumptions": [],
            "verification": {"passed": True, "issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "plan.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "preview-telegram",
                    "--artifact-type",
                    "plan",
                    "--input-file",
                    str(artifact),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )

        self.assertIn("Weekly Plan", completed.stdout)
        self.assertIn("Routine cấp ẩm cho da", completed.stdout)

    def test_preview_telegram_renders_approval_audit_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = {
            "summary": {
                "total_items": 1,
                "pending": 1,
                "overdue_pending": 1,
                "approved": 0,
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

        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "approval-audit.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "fanpage_agent.main", "preview-telegram", "--artifact-type", "approval_audit", "--input-file", str(artifact)],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Approval Audit", completed.stdout)
        self.assertIn("overdue pending: 1", completed.stdout)

    def test_preview_telegram_renders_approval_queue_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = {
            "summary": {
                "total_items": 1,
                "by_status": {"planned": 1},
                "by_approval_status": {"pending": 1},
                "by_pillar": {"education": 1},
            },
            "items": [
                {
                    "calendar_id": "cal-approval-1",
                    "date": "2026-06-30",
                    "topic": "Routine sáng cho da dầu",
                    "status": "planned",
                    "approval_status": "pending",
                    "pillar": "education",
                    "draft_caption_ref": "artifacts/captions/cal-approval-1.json",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "approval-queue.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "fanpage_agent.main", "preview-telegram", "--artifact-type", "approval", "--input-file", str(artifact)],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Approval Queue", completed.stdout)
        self.assertIn("cal-approval-1", completed.stdout)

    def test_preview_telegram_renders_metrics_backlog_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = {
            "summary": {
                "total_items": 1,
                "by_status": {"published": 1},
                "by_approval_status": {"approved": 1},
                "by_pillar": {"education": 1},
            },
            "items": [
                {
                    "calendar_id": "cal-metrics-1",
                    "date": "2026-06-30",
                    "topic": "Routine phục hồi sau treatment",
                    "status": "published",
                    "approval_status": "approved",
                    "pillar": "education",
                    "published_at": "2026-06-30T10:00:00",
                    "permalink": "https://example.com/post-1",
                    "reach": "0",
                    "engagement_rate": "0.0",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "metrics-backlog.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "fanpage_agent.main", "preview-telegram", "--artifact-type", "metrics", "--input-file", str(artifact)],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Metrics Backlog", completed.stdout)
        self.assertIn("https://example.com/post-1", completed.stdout)

    def test_preview_telegram_renders_research_brief_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = {
            "top_performing_topics": ["Routine phục hồi da"],
            "overused_topics": ["Routine cấp ẩm"],
            "frequent_questions": ["Chi phí soi da là bao nhiêu?"],
            "campaign_focus": ["soi da"],
            "recommended_pillars": ["trust"],
            "recommended_objectives": ["lead"],
            "next_angles": ["Bảng giá soi da"],
            "recommendations": ["Ưu tiên objective lead trong vòng nội dung kế tiếp."],
        }

        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "research-brief.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "fanpage_agent.main", "preview-telegram", "--artifact-type", "research", "--input-file", str(artifact)],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Research Brief", completed.stdout)
        self.assertIn("Chi phí soi da là bao nhiêu?", completed.stdout)
    def test_preview_telegram_renders_approved_triage_replies_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = {
            "summary": {"total_items": 1, "by_status": {"approved": 1}, "by_priority": {"high": 1}},
            "items": [
                {
                    "triage_id": "triage-approved-1",
                    "source": "inbox",
                    "message": "Chi phí soi da là bao nhiêu?",
                    "priority": "high",
                    "category": "lead",
                    "draft_reply": "Dạ bạn inbox để bên mình tư vấn chi tiết hơn nhé.",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "approved-triage-replies.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "fanpage_agent.main", "preview-telegram", "--artifact-type", "approved_replies", "--input-file", str(artifact)],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Approved Triage Replies", completed.stdout)
        self.assertIn("triage-approved-1", completed.stdout)
        self.assertIn("mark-triage-reply-sent", completed.stdout)
    def test_preview_telegram_renders_operator_digest_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = {
            "summary": {"pending_captions": 1, "approved_replies": 1, "metrics_backlog": 1},
            "approval_queue": {"items": [{"calendar_id": "cal-1", "topic": "Routine sáng"}]},
            "approved_replies": {"items": [{"triage_id": "triage-1", "message": "Chi phí?"}]},
            "metrics_backlog": {"items": [{"calendar_id": "cal-2", "topic": "Routine tối"}]},
        }

        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "operator-digest.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "fanpage_agent.main", "preview-telegram", "--artifact-type", "operator", "--input-file", str(artifact)],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Daily Operator Digest", completed.stdout)
        self.assertIn("cal-1", completed.stdout)
        self.assertIn("triage-1", completed.stdout)
        self.assertIn("cal-2", completed.stdout)


if __name__ == "__main__":
    unittest.main()
