import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class TriageStateCliTest(unittest.TestCase):
    def test_triage_write_store_then_approve_and_reject_reply_updates_rows(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            comments = tmpdir / "comment_inbox.csv"
            triage_file = tmpdir / "comment_triage.csv"
            comments.write_text(
                "created_at,source,message\n"
                "2026-06-24,inbox,Chi phí soi da là bao nhiêu?\n"
                "2026-06-24,comment,Mình bị kích ứng sau treatment, cần hỗ trợ gấp\n",
                encoding="utf-8",
            )

            triage = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "triage-community",
                    "--brand-file",
                    str(sample),
                    "--comment-file",
                    str(comments),
                    "--triage-file",
                    str(triage_file),
                    "--write-store",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            triage_payload = json.loads(triage.stdout)
            lead_id = triage_payload["items"][0]["triage_id"]
            complaint_id = triage_payload["items"][1]["triage_id"]

            approved = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "approve-triage-reply",
                    "--triage-file",
                    str(triage_file),
                    "--triage-id",
                    lead_id,
                    "--approved-by",
                    "Tai",
                    "--approved-at",
                    "2026-06-24T09:00:00",
                    "--assigned-to",
                    "closer-1",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            rejected = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "reject-triage-reply",
                    "--triage-file",
                    str(triage_file),
                    "--triage-id",
                    complaint_id,
                    "--reason",
                    "Cần bác sĩ duyệt trước",
                    "--rejected-at",
                    "2026-06-24T09:05:00",
                    "--assigned-to",
                    "support-lead",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )

            with triage_file.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        approved_data = json.loads(approved.stdout)
        rejected_data = json.loads(rejected.stdout)
        self.assertEqual(triage_payload["summary"]["total_items"], 2)
        self.assertEqual(rows[0]["status"], "approved")
        self.assertEqual(rows[0]["approved_by"], "Tai")
        self.assertEqual(rows[0]["assigned_to"], "closer-1")
        self.assertEqual(rows[1]["status"], "needs_revision")
        self.assertIn("Cần bác sĩ duyệt trước", rows[1]["rejected_reason"])
        self.assertEqual(approved_data["triage_id"], lead_id)
        self.assertEqual(rejected_data["triage_id"], complaint_id)


if __name__ == "__main__":
    unittest.main()
