import csv
import json
import socket
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


class ApprovalAuditDeliveryCliTest(unittest.TestCase):
    def test_deliver_approval_audit_sends_digest_and_saves_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "content_calendar.csv"
            artifacts = tmpdir / "artifacts"
            capture = tmpdir / "capture.json"
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
                            last_updated="2026-06-20",
                            draft_caption_ref="artifacts/captions/cal-old.json",
                        )
                    ]
                )

            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            server_script = tmpdir / "fake_telegram_server.py"
            server_script.write_text(
                """
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
capture_path = sys.argv[1]
port = int(sys.argv[2])
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        data = json.loads(self.rfile.read(length).decode('utf-8'))
        with open(capture_path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False)
        response = json.dumps({'ok': True, 'result': {'message_id': 802}}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)
    def log_message(self, format, *args):
        return
HTTPServer(('127.0.0.1', port), Handler).handle_request()
""",
                encoding="utf-8",
            )
            server = subprocess.Popen(
                [sys.executable, str(server_script), str(capture), str(port)],
                cwd=root,
                env=isolated_subprocess_env(),
            )
            try:
                env = isolated_subprocess_env()
                env.update(
                    {
                        "ARTIFACTS_DIR": str(artifacts),
                        "TELEGRAM_BOT_TOKEN": "bot-token",
                        "TELEGRAM_CHAT_ID": "123456",
                        "TELEGRAM_BASE_URL": f"http://127.0.0.1:{port}",
                    }
                )
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "fanpage_agent.main",
                        "deliver-approval-audit",
                        "--calendar-file",
                        str(calendar),
                        "--as-of",
                        "2026-06-24",
                        "--sla-days",
                        "2",
                        "--save",
                    ],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            finally:
                server.wait(timeout=10)

            payload = json.loads(completed.stdout)
            sent_message = json.loads(capture.read_text(encoding="utf-8"))
            artifact_exists = (artifacts / "approvals" / "approval-audit.json").exists()

        self.assertEqual(payload["delivery"]["sent_count"], 1)
        self.assertTrue(artifact_exists)
        self.assertIn("Approval Audit", sent_message["text"])
        self.assertIn("overdue pending: 1", sent_message["text"])
        self.assertIn("approve-caption --calendar-id cal-old", sent_message["text"])

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
