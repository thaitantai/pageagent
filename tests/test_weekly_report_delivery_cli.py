import csv
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class WeeklyReportDeliveryCliTest(unittest.TestCase):
    def test_deliver_weekly_report_builds_and_sends_report_message(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            metrics_csv = tmpdir / "post_metrics.csv"
            with metrics_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["published_at", "topic", "pillar", "objective", "reach", "engagements", "leads"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "published_at": "2026-05-26",
                        "topic": "Routine 3 bước cho da thiếu nước",
                        "pillar": "education",
                        "objective": "engagement",
                        "reach": "1500",
                        "engagements": "180",
                        "leads": "8",
                    }
                )
            capture = tmpdir / "capture.json"
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
        with open(capture_path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False)
        response = json.dumps({'ok': True, 'result': {'message_id': 77}}).encode('utf-8')
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
                env = isolated_subprocess_env(
                    ARTIFACTS_DIR=str(artifacts),
                    TELEGRAM_BOT_TOKEN="bot-token",
                    TELEGRAM_CHAT_ID="123456",
                    TELEGRAM_BASE_URL=f"http://127.0.0.1:{port}",
                )
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "fanpage_agent.main",
                        "deliver-weekly-report",
                        "--brand-file",
                        str(sample),
                        "--metrics-file",
                        str(metrics_csv),
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
            delivered = json.loads(capture.read_text(encoding="utf-8"))
            artifact_exists = (artifacts / "reports" / "weekly-report.json").exists()

        self.assertEqual(payload["delivery"]["sent_count"], 1)
        self.assertEqual(payload["delivery"]["results"][0]["result"]["message_id"], 77)
        self.assertIn("Weekly Report", delivered["text"])
        self.assertIn("Routine 3 bước cho da thiếu nước", delivered["text"])
        self.assertTrue(artifact_exists)


if __name__ == "__main__":
    unittest.main()
