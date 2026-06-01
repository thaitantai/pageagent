import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class MetricsBacklogCliTest(unittest.TestCase):
    def test_list_calendar_items_and_delivery_filter_published_items_missing_metrics(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "calendar.csv"
            history = tmpdir / "history.csv"
            metrics = tmpdir / "metrics.csv"
            capture = tmpdir / "telegram_capture.json"
            server_script = tmpdir / "server.py"
            server_script.write_text(
                """
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
capture = Path(sys.argv[1])
port = int(sys.argv[2])
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length).decode('utf-8')
        capture.write_text(json.dumps({'path': self.path, 'body': raw}), encoding='utf-8')
        payload = json.dumps({'ok': True, 'result': {'message_id': 1}}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, format, *args):
        return
HTTPServer(('127.0.0.1', port), Handler).serve_forever()
""".strip(),
                encoding="utf-8",
            )

            subprocess.run([
                sys.executable, "-m", "fanpage_agent.main", "plan-week",
                "--brand-file", str(sample),
                "--start-date", "2026-06-27",
                "--days", "2",
                "--calendar-file", str(calendar),
                "--history-file", str(history),
                "--write-calendar",
            ], cwd=root, env=isolated_subprocess_env(), capture_output=True, text=True, check=True)

            for calendar_id, published_at, permalink in [
                ("weekly-plan-brand_abc-2026-06-27-1", "2026-06-27T10:00:00", "https://example.com/post-1"),
                ("weekly-plan-brand_abc-2026-06-27-2", "2026-06-28T10:00:00", "https://example.com/post-2"),
            ]:
                subprocess.run([
                    sys.executable, "-m", "fanpage_agent.main", "publish-post",
                    "--calendar-file", str(calendar),
                    "--history-file", str(history),
                    "--metrics-file", str(metrics),
                    "--calendar-id", calendar_id,
                    "--published-at", published_at,
                    "--permalink", permalink,
                ], cwd=root, env=isolated_subprocess_env(), capture_output=True, text=True, check=True)

            subprocess.run([
                sys.executable, "-m", "fanpage_agent.main", "record-post-metrics",
                "--calendar-file", str(calendar),
                "--history-file", str(history),
                "--metrics-file", str(metrics),
                "--calendar-id", "weekly-plan-brand_abc-2026-06-27-1",
                "--reach", "1700",
                "--engagements", "119",
                "--leads", "9",
                "--recorded-at", "2026-06-28T08:00:00",
            ], cwd=root, env=isolated_subprocess_env(), capture_output=True, text=True, check=True)

            listed = subprocess.run([
                sys.executable, "-m", "fanpage_agent.main", "list-calendar-items",
                "--calendar-file", str(calendar),
                "--history-file", str(history),
                "--metrics-file", str(metrics),
                "--status", "published",
                "--metrics-pending",
            ], cwd=root, env=isolated_subprocess_env(), capture_output=True, text=True, check=True)

            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            server = subprocess.Popen(
                [sys.executable, str(server_script), str(capture), str(port)],
                cwd=root,
                env=isolated_subprocess_env(),
            )
            try:
                env = isolated_subprocess_env()
                env["TELEGRAM_BOT_TOKEN"] = "test-token"
                env["TELEGRAM_CHAT_ID"] = "123456"
                env["TELEGRAM_BASE_URL"] = f"http://127.0.0.1:{port}"
                delivered = subprocess.run([
                    sys.executable, "-m", "fanpage_agent.main", "deliver-metrics-backlog",
                    "--calendar-file", str(calendar),
                    "--history-file", str(history),
                    "--metrics-file", str(metrics),
                    "--status", "published",
                    "--metrics-pending",
                ], cwd=root, env=env, capture_output=True, text=True, check=True)
            finally:
                server.terminate()
                server.wait(timeout=5)

            listed_payload = json.loads(listed.stdout)
            delivered_payload = json.loads(delivered.stdout)
            sent_message = json.loads(capture.read_text(encoding="utf-8"))

        self.assertEqual(listed_payload["summary"]["total_items"], 1)
        self.assertEqual(listed_payload["items"][0]["calendar_id"], "weekly-plan-brand_abc-2026-06-27-2")
        self.assertEqual(delivered_payload["summary"]["total_items"], 1)
        self.assertEqual(delivered_payload["delivery"]["sent_count"], 1)
        self.assertIn("Metrics Backlog", sent_message["body"])
        self.assertIn("weekly-plan-brand_abc-2026-06-27-2", sent_message["body"])


if __name__ == "__main__":
    unittest.main()
