import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class TriageReplySentCliTest(unittest.TestCase):
    def test_mark_triage_reply_sent_updates_status_and_delivery_metadata(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            comments = tmpdir / "comment_inbox.csv"
            triage_file = tmpdir / "comment_triage.csv"
            comments.write_text(
                "created_at,source,message\n"
                "2026-06-24,inbox,Chi phí soi da là bao nhiêu?\n",
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
            triage_id = json.loads(triage.stdout)["items"][0]["triage_id"]

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "approve-triage-reply",
                    "--triage-file",
                    str(triage_file),
                    "--triage-id",
                    triage_id,
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

            sent = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "mark-triage-reply-sent",
                    "--triage-file",
                    str(triage_file),
                    "--triage-id",
                    triage_id,
                    "--sent-at",
                    "2026-06-24T09:15:00",
                    "--reply-permalink",
                    "https://facebook.com/comment/123",
                    "--assigned-to",
                    "closer-1",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            listed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "list-triage-items",
                    "--triage-file",
                    str(triage_file),
                    "--status",
                    "replied",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            with triage_file.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        sent_data = json.loads(sent.stdout)
        listed_data = json.loads(listed.stdout)
        self.assertEqual(sent_data["status"], "replied")
        self.assertEqual(sent_data["reply_sent_at"], "2026-06-24T09:15:00")
        self.assertEqual(sent_data["reply_permalink"], "https://facebook.com/comment/123")
        self.assertEqual(sent_data["assigned_to"], "closer-1")
        self.assertEqual(rows[0]["status"], "replied")
        self.assertEqual(rows[0]["reply_sent_at"], "2026-06-24T09:15:00")
        self.assertEqual(rows[0]["reply_permalink"], "https://facebook.com/comment/123")
        self.assertEqual(listed_data["summary"]["total_items"], 1)
        self.assertEqual(listed_data["items"][0]["triage_id"], triage_id)


if __name__ == "__main__":
    unittest.main()
