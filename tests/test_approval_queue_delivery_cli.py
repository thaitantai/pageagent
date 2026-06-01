import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class ApprovalQueueDeliveryCliTest(unittest.TestCase):
    def test_deliver_approval_queue_sends_pending_calendar_digest(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifacts = tmpdir / "artifacts"
            calendar = tmpdir / "calendar.csv"
            history = tmpdir / "history.csv"
            metrics = tmpdir / "metrics.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"
            capture = tmpdir / "capture.json"
            comments.write_text(
                "created_at,source,message\n2026-06-24,inbox,Khách hỏi routine cấp ẩm\n",
                encoding="utf-8",
            )
            campaign.write_text(
                json.dumps({"focus": "đẩy lead treatment cấp ẩm"}, ensure_ascii=False),
                encoding="utf-8",
            )
            env = isolated_subprocess_env()
            env["ARTIFACTS_DIR"] = str(artifacts)
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "run-daily",
                    "--brand-file",
                    str(sample),
                    "--run-date",
                    "2026-06-24",
                    "--days",
                    "1",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--metrics-file",
                    str(metrics),
                    "--comment-file",
                    str(comments),
                    "--campaign-file",
                    str(campaign),
                    "--write-calendar",
                    "--save",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
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
        body = self.rfile.read(length).decode('utf-8')
        data = json.loads(body)
        with open(capture_path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False)
        response = json.dumps({'ok': True, 'result': {'message_id': 701}}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)
    def log_message(self, format, *args):
        return
server = HTTPServer(('127.0.0.1', port), Handler)
server.handle_request()
""",
                encoding="utf-8",
            )
            server = subprocess.Popen(
                [sys.executable, str(server_script), str(capture), str(port)],
                cwd=root,
                env=isolated_subprocess_env(),
            )
            try:
                env.update(
                    {
                        "TELEGRAM_BOT_TOKEN": "bot-token",
                        "TELEGRAM_CHAT_ID": "123456",
                        "TELEGRAM_BASE_URL": f"http://127.0.0.1:{port}",
                    }
                )
                delivered = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "fanpage_agent.main",
                        "deliver-approval-queue",
                        "--calendar-file",
                        str(calendar),
                        "--history-file",
                        str(history),
                        "--metrics-file",
                        str(metrics),
                        "--approval-status",
                        "pending",
                        "--limit",
                        "1",
                    ],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            finally:
                server.wait(timeout=10)

            payload = json.loads(delivered.stdout)
            sent_message = json.loads(capture.read_text(encoding="utf-8"))

        self.assertEqual(payload["summary"]["total_items"], 1)
        self.assertEqual(payload["delivery"]["sent_count"], 1)
        self.assertIn("Approval Queue", sent_message["text"])
        self.assertIn("weekly-plan-brand_abc-2026-06-24-1", sent_message["text"])
        self.assertIn("draft caption", sent_message["text"].lower())


if __name__ == "__main__":
    unittest.main()
