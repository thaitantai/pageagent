import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class OperatorDigestDeliveryCliTest(unittest.TestCase):
    def test_deliver_operator_digest_sends_combined_operational_queues_and_saves_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifacts = tmpdir / "artifacts"
            calendar = tmpdir / "calendar.csv"
            history = tmpdir / "history.csv"
            metrics = tmpdir / "metrics.csv"
            triage_file = tmpdir / "comment_triage.csv"
            comments = tmpdir / "comment_inbox.csv"
            campaign = tmpdir / "campaign_notes.json"
            capture = tmpdir / "capture.json"

            comments.write_text(
                "created_at,source,message\n"
                "2026-06-24,inbox,Chi phí soi da là bao nhiêu?\n",
                encoding="utf-8",
            )
            campaign.write_text(json.dumps({"focus": "soi da"}, ensure_ascii=False), encoding="utf-8")
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
                    "2",
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
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "publish-post",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--metrics-file",
                    str(metrics),
                    "--calendar-id",
                    "weekly-plan-brand_abc-2026-06-24-2",
                    "--published-at",
                    "2026-06-25T10:00:00",
                    "--permalink",
                    "https://example.com/post-2",
                    "--allow-unapproved",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
                check=True,
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
            triage_id = json.loads(triage.stdout)["items"][0]["triage_id"]
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "approve-triage-reply",
                    "--triage-file",
                    str(triage_file),
                    "--triage-id",
                    triage_id,
                    "--approved-by",
                    "Tai",
                    "--approved-at",
                    "2026-06-24T09:00:00",
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
        response = json.dumps({'ok': True, 'result': {'message_id': 901}}).encode('utf-8')
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
                deliver_env = isolated_subprocess_env()
                deliver_env.update(
                    {
                        "ARTIFACTS_DIR": str(artifacts),
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
                        "deliver-operator-digest",
                        "--calendar-file",
                        str(calendar),
                        "--history-file",
                        str(history),
                        "--metrics-file",
                        str(metrics),
                        "--triage-file",
                        str(triage_file),
                        "--limit",
                        "3",
                        "--save",
                    ],
                    cwd=root,
                    env=deliver_env,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            finally:
                server.wait(timeout=10)

            payload = json.loads(delivered.stdout)
            sent_message = json.loads(capture.read_text(encoding="utf-8"))
            artifact_exists = (artifacts / "ops" / "operator-digest.json").exists()

        self.assertTrue(artifact_exists)
        self.assertEqual(payload["summary"]["pending_captions"], 1)
        self.assertEqual(payload["summary"]["approved_replies"], 1)
        self.assertEqual(payload["summary"]["metrics_backlog"], 1)
        self.assertEqual(payload["delivery"]["sent_count"], 1)
        self.assertIn("Daily Operator Digest", sent_message["text"])
        self.assertIn("Pending captions", sent_message["text"])
        self.assertIn("Approved replies", sent_message["text"])
        self.assertIn("Metrics backlog", sent_message["text"])
        self.assertIn("weekly-plan-brand_abc-2026-06-24-1", sent_message["text"])
        self.assertIn(triage_id, sent_message["text"])
        self.assertIn("weekly-plan-brand_abc-2026-06-24-2", sent_message["text"])

    def test_deliver_operator_digest_skip_empty_does_not_require_telegram_or_send(self) -> None:
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifacts = tmpdir / "artifacts"
            calendar = tmpdir / "calendar.csv"
            history = tmpdir / "history.csv"
            metrics = tmpdir / "metrics.csv"
            triage_file = tmpdir / "comment_triage.csv"
            env = isolated_subprocess_env()
            env["ARTIFACTS_DIR"] = str(artifacts)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "deliver-operator-digest",
                    "--calendar-file",
                    str(calendar),
                    "--history-file",
                    str(history),
                    "--metrics-file",
                    str(metrics),
                    "--triage-file",
                    str(triage_file),
                    "--skip-empty",
                    "--save",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )
            artifact_exists = (artifacts / "ops" / "operator-digest.json").exists()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(artifact_exists)
        self.assertEqual(payload["summary"]["pending_captions"], 0)
        self.assertEqual(payload["summary"]["approved_replies"], 0)
        self.assertEqual(payload["summary"]["metrics_backlog"], 0)
        self.assertEqual(payload["delivery"]["sent_count"], 0)
        self.assertTrue(payload["delivery"]["skipped"])
        self.assertEqual(payload["delivery"]["reason"], "empty_digest")


if __name__ == "__main__":
    unittest.main()
