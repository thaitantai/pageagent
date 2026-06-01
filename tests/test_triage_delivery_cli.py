import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CommunityTriageDeliveryCliTest(unittest.TestCase):
    def test_deliver_triage_community_builds_and_sends_summary_message(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            capture = tmpdir / "capture.json"
            comments = tmpdir / "comment_inbox.csv"
            artifacts = tmpdir / "artifacts"
            comments.write_text(
                "created_at,source,message\n"
                "2026-06-24,inbox,Chi phí soi da là bao nhiêu?\n"
                "2026-06-24,comment,Mình bị kích ứng sau treatment, cần hỗ trợ gấp\n"
                "2026-06-24,comment,Xem ngay http://spam.example để nhận quà\n",
                encoding="utf-8",
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
        response = json.dumps({'ok': True, 'result': {'message_id': 321}}).encode('utf-8')
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
                        "deliver-triage-community",
                        "--brand-file",
                        str(sample),
                        "--comment-file",
                        str(comments),
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
            artifact_exists = (artifacts / "community" / "community-triage.json").exists()

        self.assertTrue(artifact_exists)
        self.assertEqual(payload["delivery"]["sent_count"], 1)
        self.assertIn("Community Triage", sent_message["text"])
        self.assertIn("lead: 1", sent_message["text"])
        self.assertIn("complaint: 1", sent_message["text"])
        self.assertIn("spam: 1", sent_message["text"])
        self.assertIn("urgent", sent_message["text"].lower())


if __name__ == "__main__":
    unittest.main()
