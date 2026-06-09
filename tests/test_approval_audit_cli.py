import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


HEADERS = [
    "brand_id",
    "calendar_id",
    "date",
    "pillar",
    "objective",
    "topic",
    "angle",
    "format",
    "hook",
    "cta",
    "visual_brief",
    "status",
    "approval_status",
    "approved_by",
    "final_caption_ref",
    "draft_caption_ref",
    "campaign_tag",
    "notes",
    "last_updated",
    "published_at",
    "permalink",
    "reach",
    "engagement_rate",
]


class ApprovalAuditCliTest(unittest.TestCase):
    def test_approval_audit_reports_overdue_pending_and_status_counts(self) -> None:
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            calendar = Path(tmp) / "content_calendar.csv"
            with calendar.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=HEADERS)
                writer.writeheader()
                writer.writerows(
                    [
                        self._row(
                            calendar_id="cal-old",
                            date="2026-06-20",
                            topic="Old pending caption",
                            approval_status="pending",
                            status="planned",
                            last_updated="2026-06-20",
                            draft_caption_ref="artifacts/captions/cal-old.json",
                        ),
                        self._row(
                            calendar_id="cal-new",
                            date="2026-06-23",
                            topic="Fresh pending caption",
                            approval_status="pending",
                            status="planned",
                            last_updated="2026-06-23",
                            draft_caption_ref="artifacts/captions/cal-new.json",
                        ),
                        self._row(
                            calendar_id="cal-approved",
                            date="2026-06-21",
                            topic="Approved caption",
                            approval_status="approved",
                            status="approved",
                            approved_by="Tai",
                            last_updated="2026-06-22",
                        ),
                        self._row(
                            calendar_id="cal-rejected",
                            date="2026-06-22",
                            topic="Rejected caption",
                            approval_status="rejected",
                            status="needs_revision",
                            notes="CTA chưa ổn",
                            last_updated="2026-06-23",
                        ),
                    ]
                )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "approval-audit",
                    "--calendar-file",
                    str(calendar),
                    "--as-of",
                    "2026-06-24",
                    "--sla-days",
                    "2",
                    "--limit",
                    "5",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["summary"]["total_audited"], 4)
        self.assertEqual(payload["summary"]["pending"], 2)
        self.assertEqual(payload["summary"]["overdue_pending"], 1)
        self.assertEqual(payload["summary"]["approved"], 1)
        self.assertEqual(payload["summary"]["rejected"], 1)
        self.assertEqual(payload["overdue_items"][0]["calendar_id"], "cal-old")
        self.assertEqual(payload["overdue_items"][0]["days_pending"], 4)
        self.assertEqual(payload["overdue_items"][0]["draft_caption_ref"], "artifacts/captions/cal-old.json")

    def _row(self, **overrides: str) -> dict[str, str]:
        row = {header: "" for header in HEADERS}
        row.update(
            {
                "brand_id": "brand_abc",
                "pillar": "education",
                "objective": "lead",
                "format": "post_short",
                "status": "planned",
                "approval_status": "pending",
                "reach": "0",
                "engagement_rate": "0.0",
            }
        )
        row.update(overrides)
        return row


if __name__ == "__main__":
    unittest.main()
