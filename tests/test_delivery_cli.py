import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class DeliveryCliTest(unittest.TestCase):
    def test_deliver_daily_packet_builds_and_sends_plan_and_caption_messages(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "calendar.csv"
            history = tmpdir / "history.csv"
            metrics = tmpdir / "metrics.csv"
            capture = tmpdir / "capture.jsonl"
            artifacts = tmpdir / "artifacts"
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
        with open(capture_path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(data, ensure_ascii=False) + '\\n')
        response = json.dumps({'ok': True, 'result': {'message_id': 100 + sum(1 for _ in open(capture_path, 'r', encoding='utf-8'))}}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)
    def log_message(self, format, *args):
        return
server = HTTPServer(('127.0.0.1', port), Handler)
server.handle_request()
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
                        "deliver-daily-packet",
                        "--brand-file",
                        str(sample),
                        "--run-date",
                        "2026-06-22",
                        "--days",
                        "1",
                        "--calendar-file",
                        str(calendar),
                        "--history-file",
                        str(history),
                        "--metrics-file",
                        str(metrics),
                        "--write-calendar",
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
            sent_messages = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines() if line.strip()]
            artifact_exists = (artifacts / "ops" / "daily-ops-2026-06-22.json").exists()

        self.assertEqual(payload["run_date"], "2026-06-22")
        self.assertEqual(payload["delivery"]["sent_count"], 2)
        self.assertEqual(len(sent_messages), 2)
        self.assertIn("Weekly Plan", sent_messages[0]["text"])
        self.assertIn("Caption Package", sent_messages[1]["text"])
        self.assertTrue(artifact_exists)


if __name__ == "__main__":
    unittest.main()
