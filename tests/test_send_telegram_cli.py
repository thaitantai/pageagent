import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SendTelegramPreviewCliTest(unittest.TestCase):
    def test_send_telegram_preview_delivers_formatted_message(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = {
            "plan_title": "weekly-plan-brand_abc-2026-06-08",
            "days": [
                {
                    "date": "2026-06-08",
                    "pillar": "education",
                    "objective": "reach",
                    "topic": "Routine cấp ẩm cho da",
                    "angle": "checklist 3 bước",
                    "format": "post_short",
                    "hook": "3 bước cấp ẩm bạn nên biết",
                    "cta": "Lưu lại khi cần",
                    "visual_brief": "Layout checklist",
                    "risk_notes": [],
                }
            ],
            "strategy_notes": ["Giữ mix pillar"],
            "gaps_or_assumptions": [],
            "verification": {"passed": True, "issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifact = tmpdir / "plan.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            capture = tmpdir / "capture.json"
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
        response = json.dumps({'ok': True, 'result': {'message_id': 99}}).encode('utf-8')
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
                        "send-telegram-preview",
                        "--artifact-type",
                        "plan",
                        "--input-file",
                        str(artifact),
                    ],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            finally:
                server.wait(timeout=10)

            delivered = json.loads(capture.read_text(encoding="utf-8"))
            payload = json.loads(completed.stdout)

        self.assertEqual(payload["result"]["message_id"], 99)
        self.assertEqual(delivered["chat_id"], "123456")
        self.assertIn("Weekly Plan", delivered["text"])
        self.assertIn("Routine cấp ẩm cho da", delivered["text"])

    def test_send_telegram_preview_delivers_metrics_backlog_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = {
            "summary": {
                "total_items": 1,
                "by_status": {"published": 1},
                "by_approval_status": {"approved": 1},
                "by_pillar": {"education": 1},
            },
            "items": [
                {
                    "calendar_id": "cal-metrics-1",
                    "date": "2026-06-30",
                    "topic": "Routine phục hồi sau treatment",
                    "status": "published",
                    "approval_status": "approved",
                    "pillar": "education",
                    "published_at": "2026-06-30T10:00:00",
                    "permalink": "https://example.com/post-1",
                    "reach": "0",
                    "engagement_rate": "0.0",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifact = tmpdir / "metrics-backlog.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            capture = tmpdir / "capture.json"
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
                env = os.environ.copy()
                env.update(
                    {
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
                        "send-telegram-preview",
                        "--artifact-type",
                        "metrics",
                        "--input-file",
                        str(artifact),
                    ],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                )
            finally:
                server.wait(timeout=10)

            if capture.exists():
                delivered = json.loads(capture.read_text(encoding="utf-8"))
            else:
                delivered = None

        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["result"]["message_id"], 77)
        self.assertIsNotNone(delivered)
        self.assertIn("Metrics Backlog", delivered["text"])
        self.assertIn("https://example.com/post-1", delivered["text"])

    def test_send_telegram_preview_delivers_research_brief_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = {
            "top_performing_topics": ["Routine phục hồi da"],
            "overused_topics": ["Routine cấp ẩm"],
            "frequent_questions": ["Chi phí soi da là bao nhiêu?"],
            "campaign_focus": ["soi da"],
            "recommended_pillars": ["trust"],
            "recommended_objectives": ["lead"],
            "next_angles": ["Bảng giá soi da"],
            "recommendations": ["Ưu tiên objective lead trong vòng nội dung kế tiếp."],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifact = tmpdir / "research-brief.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            capture = tmpdir / "capture.json"
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
        response = json.dumps({'ok': True, 'result': {'message_id': 55}}).encode('utf-8')
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
                        "send-telegram-preview",
                        "--artifact-type",
                        "research",
                        "--input-file",
                        str(artifact),
                    ],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                )
            finally:
                server.wait(timeout=10)

            if capture.exists():
                delivered = json.loads(capture.read_text(encoding="utf-8"))
            else:
                delivered = None

        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["result"]["message_id"], 55)
        self.assertIsNotNone(delivered)
        self.assertIn("Research Brief", delivered["text"])
        self.assertIn("Chi phí soi da là bao nhiêu?", delivered["text"])


if __name__ == "__main__":
    unittest.main()
