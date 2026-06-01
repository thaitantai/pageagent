import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class CommunityTriageStoreDigestCliTest(unittest.TestCase):
    def test_deliver_triage_community_from_store_filters_pending_items(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            capture = tmpdir / "capture.json"
            comments = tmpdir / "comment_inbox.csv"
            triage_file = tmpdir / "comment_triage.csv"
            comments.write_text(
                "created_at,source,message\n"
                "2026-06-24,inbox,Chi phí soi da là bao nhiêu?\n"
                "2026-06-24,comment,Mình bị kích ứng sau treatment, cần hỗ trợ gấp\n"
                "2026-06-24,comment,Xem ngay http://spam.example để nhận quà\n",
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
            subprocess.run(
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
                env=isolated_subprocess_env(),
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
server = HTTPServer(('127.0.0.1', port), Handler)
server.handle_request()
""",
                encoding="utf-8",
            )
            server = subprocess.Popen([sys.executable, str(server_script), str(capture), str(port)], cwd=root)
            time.sleep(0.2)
            try:
                env = isolated_subprocess_env(
                    TELEGRAM_BOT_TOKEN="bot-token",
                    TELEGRAM_CHAT_ID="123456",
                    TELEGRAM_BASE_URL=f"http://127.0.0.1:{port}",
                )
                delivered = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "fanpage_agent.main",
                        "deliver-triage-community",
                        "--triage-file",
                        str(triage_file),
                        "--from-store",
                        "--status",
                        "new",
                        "--limit",
                        "2",
                        "--brand-file",
                        str(sample),
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
            for _ in range(20):
                if capture.exists():
                    break
                time.sleep(0.1)
            sent_message = json.loads(capture.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["total_items"], 2)
            self.assertEqual(payload["summary"]["by_status"]["new"], 2)
            self.assertNotIn(lead_id, sent_message["text"])
            self.assertIn("Community Triage", sent_message["text"])
            self.assertIn("status: new", sent_message["text"].lower())


if __name__ == "__main__":
    unittest.main()
