import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ApprovedTriageRepliesDeliveryCliTest(unittest.TestCase):
    def test_deliver_approved_triage_replies_sends_copy_paste_digest_and_saves_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            capture = tmpdir / "capture.json"
            comments = tmpdir / "comment_inbox.csv"
            triage_file = tmpdir / "comment_triage.csv"
            artifacts = tmpdir / "artifacts"
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
            approved_id = json.loads(triage.stdout)["items"][0]["triage_id"]
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "approve-triage-reply",
                    "--triage-file",
                    str(triage_file),
                    "--triage-id",
                    approved_id,
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
        response = json.dumps({'ok': True, 'result': {'message_id': 654}}).encode('utf-8')
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
            server = subprocess.Popen([sys.executable, str(server_script), str(capture), str(port)], cwd=root)
            try:
                env = os.environ.copy()
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
                        "deliver-approved-triage-replies",
                        "--triage-file",
                        str(triage_file),
                        "--limit",
                        "5",
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
            artifact_exists = (artifacts / "community" / "approved-triage-replies.json").exists()

        self.assertTrue(artifact_exists)
        self.assertEqual(payload["summary"]["total_items"], 1)
        self.assertEqual(payload["delivery"]["sent_count"], 1)
        self.assertIn("Approved Triage Replies", sent_message["text"])
        self.assertIn(approved_id, sent_message["text"])
        self.assertIn("Chi phí soi da là bao nhiêu?", sent_message["text"])
        self.assertIn("draft_reply:", sent_message["text"])
        self.assertIn("mark-triage-reply-sent", sent_message["text"])


if __name__ == "__main__":
    unittest.main()
