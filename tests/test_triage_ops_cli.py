import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TriageOpsCliTest(unittest.TestCase):
    def test_list_resolve_and_reopen_triage_items_with_filters(self) -> None:
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
                capture_output=True,
                text=True,
                check=True,
            )
            triage_payload = json.loads(triage.stdout)
            lead_id = triage_payload["items"][0]["triage_id"]

            subprocess.run(
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
                capture_output=True,
                text=True,
                check=True,
            )
            resolved = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "resolve-triage-item",
                    "--triage-file",
                    str(triage_file),
                    "--triage-id",
                    lead_id,
                    "--resolved-at",
                    "2026-06-24T10:00:00",
                    "--assigned-to",
                    "closer-1",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            listed_resolved = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "list-triage-items",
                    "--triage-file",
                    str(triage_file),
                    "--status",
                    "resolved",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            reopened = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "reopen-triage-item",
                    "--triage-file",
                    str(triage_file),
                    "--triage-id",
                    lead_id,
                    "--reopened-at",
                    "2026-06-24T11:00:00",
                    "--assigned-to",
                    "qa-reviewer",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            listed_reopened = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "list-triage-items",
                    "--triage-file",
                    str(triage_file),
                    "--status",
                    "reopened",
                    "--assigned-to",
                    "qa-reviewer",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )

        resolved_data = json.loads(resolved.stdout)
        resolved_list = json.loads(listed_resolved.stdout)
        reopened_data = json.loads(reopened.stdout)
        reopened_list = json.loads(listed_reopened.stdout)

        self.assertEqual(resolved_data["status"], "resolved")
        self.assertEqual(resolved_data["resolved_at"], "2026-06-24T10:00:00")
        self.assertEqual(resolved_list["summary"]["total_items"], 1)
        self.assertEqual(resolved_list["summary"]["by_status"]["resolved"], 1)
        self.assertEqual(resolved_list["items"][0]["triage_id"], lead_id)
        self.assertEqual(reopened_data["status"], "reopened")
        self.assertEqual(reopened_data["assigned_to"], "qa-reviewer")
        self.assertEqual(reopened_list["summary"]["total_items"], 1)
        self.assertEqual(reopened_list["summary"]["by_status"]["reopened"], 1)
        self.assertEqual(reopened_list["items"][0]["triage_id"], lead_id)


if __name__ == "__main__":
    unittest.main()
