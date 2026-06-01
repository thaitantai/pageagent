import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ResearchBriefDeliveryCliTest(unittest.TestCase):
    def test_deliver_research_brief_builds_sends_and_saves_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            history = tmpdir / "history.csv"
            metrics = tmpdir / "metrics.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"
            artifacts = tmpdir / "artifacts"
            capture = tmpdir / "capture.json"

            history.write_text(
                "published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate\n"
                "2026-06-01,Da thiếu nước nên làm gì?,Hook A,education,reach,https://example.com/1,1200,0.05\n",
                encoding="utf-8",
            )
            metrics.write_text(
                "published_at,topic,pillar,objective,reach,engagements,leads\n"
                "2026-06-03,Khi nào cần soi da?,trust,lead,1500,90,8\n",
                encoding="utf-8",
            )
            comments.write_text(
                "created_at,source,message\n"
                "2026-06-05,inbox,Chi phí soi da là bao nhiêu?\n",
                encoding="utf-8",
            )
            campaign.write_text(
                json.dumps({"campaign_focus": ["soi da"], "priority_objective": "lead"}, ensure_ascii=False),
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
        response = json.dumps({'ok': True, 'result': {'message_id': 88}}).encode('utf-8')
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
                        "deliver-research-brief",
                        "--history-file",
                        str(history),
                        "--metrics-file",
                        str(metrics),
                        "--comment-file",
                        str(comments),
                        "--campaign-file",
                        str(campaign),
                        "--save",
                    ],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                )
            finally:
                try:
                    server.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    server.terminate()
                    server.wait(timeout=10)

            artifact_path = artifacts / "research" / "research-brief.json"
            artifact_exists = artifact_path.exists()
            delivered = json.loads(capture.read_text(encoding="utf-8")) if capture.exists() else None

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(artifact_exists)
        self.assertEqual(payload["delivery"]["sent_count"], 1)
        self.assertEqual(payload["delivery"]["results"][0]["result"]["message_id"], 88)
        self.assertEqual(payload["recommended_objectives"][0], "lead")
        self.assertIsNotNone(delivered)
        self.assertIn("Research Brief", delivered["text"])
        self.assertIn("Chi phí soi da là bao nhiêu?", delivered["text"])


if __name__ == "__main__":
    unittest.main()
