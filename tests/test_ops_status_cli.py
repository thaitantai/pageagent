import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


class OpsStatusCliTest(unittest.TestCase):
    def test_ops_status_reports_expected_artifacts_and_missing_files(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            (artifacts / "ops").mkdir(parents=True)
            (artifacts / "reports").mkdir(parents=True)
            (artifacts / "ops" / "operator-digest.json").write_text(
                json.dumps({"summary": {"pending_captions": 1}}, ensure_ascii=False),
                encoding="utf-8",
            )
            (artifacts / "reports" / "weekly-report.json").write_text(
                json.dumps({"summary": {"total_posts": 3}}, ensure_ascii=False),
                encoding="utf-8",
            )
            (artifacts / "approvals").mkdir(parents=True)
            (artifacts / "approvals" / "approval-audit.json").write_text(
                json.dumps({"summary": {"overdue_pending": 2}}, ensure_ascii=False),
                encoding="utf-8",
            )
            (artifacts / "evals").mkdir(parents=True)
            (artifacts / "evals" / "eval-summary-2026-06-01.json").write_text(
                json.dumps({"summary": {"passed": 4, "failed": 0}}, ensure_ascii=False),
                encoding="utf-8",
            )
            env = isolated_subprocess_env()
            env["ARTIFACTS_DIR"] = str(artifacts)
            completed = subprocess.run(
                [sys.executable, "-m", "fanpage_agent.main", "ops-status"],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["artifacts_dir"], str(artifacts))
        by_name = {item["name"]: item for item in payload["artifacts"]}
        self.assertTrue(by_name["operator_digest"]["exists"])
        self.assertTrue(by_name["weekly_report"]["exists"])
        self.assertTrue(by_name["approval_audit"]["exists"])
        self.assertFalse(by_name["daily_ops_latest"]["exists"])
        self.assertTrue(by_name["eval_latest"]["exists"])
        self.assertEqual(by_name["operator_digest"]["summary"], {"pending_captions": 1})
        self.assertEqual(by_name["weekly_report"]["summary"], {"total_posts": 3})
        self.assertEqual(by_name["approval_audit"]["summary"], {"overdue_pending": 2})
        self.assertEqual(by_name["eval_latest"]["summary"], {"passed": 4, "failed": 0})
        self.assertEqual(payload["summary"]["existing"], 4)
        self.assertGreaterEqual(payload["summary"]["missing"], 1)

    def test_ops_status_marks_artifacts_stale_with_lane_thresholds(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            (artifacts / "ops").mkdir(parents=True)
            operator = artifacts / "ops" / "operator-digest.json"
            operator.write_text(
                json.dumps({"summary": {"pending_captions": 1}}, ensure_ascii=False),
                encoding="utf-8",
            )
            old_timestamp = 1780185600.0  # 2026-05-31T00:00:00+00:00
            operator.touch()
            import os

            os.utime(operator, (old_timestamp, old_timestamp))

            env = isolated_subprocess_env()
            env["ARTIFACTS_DIR"] = str(artifacts)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "ops-status",
                    "--now",
                    "2026-06-02T08:00:00+00:00",
                    "--max-age-hours",
                    "operator_digest=24",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        by_name = {item["name"]: item for item in payload["artifacts"]}
        self.assertEqual(payload["summary"]["stale"], 1)
        self.assertEqual(payload["summary"]["fresh"], 0)
        self.assertTrue(by_name["operator_digest"]["freshness"]["stale"])
        self.assertEqual(by_name["operator_digest"]["freshness"]["max_age_hours"], 24.0)
        self.assertGreater(by_name["operator_digest"]["freshness"]["age_hours"], 24.0)

    def test_ops_status_fail_on_stale_returns_nonzero(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            (artifacts / "ops").mkdir(parents=True)
            operator = artifacts / "ops" / "operator-digest.json"
            operator.write_text(json.dumps({"summary": {}}, ensure_ascii=False), encoding="utf-8")
            old_timestamp = 1780185600.0  # 2026-05-31T00:00:00+00:00
            import os

            os.utime(operator, (old_timestamp, old_timestamp))

            env = isolated_subprocess_env()
            env["ARTIFACTS_DIR"] = str(artifacts)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "ops-status",
                    "--now",
                    "2026-06-02T08:00:00+00:00",
                    "--max-age-hours",
                    "operator_digest=24",
                    "--fail-on-stale",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["summary"]["stale"], 1)

    def test_ops_status_reports_runtime_config_without_secret_values(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            artifacts.mkdir(parents=True)
            env = isolated_subprocess_env()
            env.update(
                {
                    "ARTIFACTS_DIR": str(artifacts),
                    "STORE_BACKEND": "google",
                    "GOOGLE_SHEETS_ID": "sheet-123",
                    "GOOGLE_SERVICE_ACCOUNT_FILE": str(Path(tmp) / "missing.json"),
                    "TELEGRAM_BOT_TOKEN": "[REDACTED]",
                    "TELEGRAM_CHAT_ID": "chat-123",
                    "FB_PAGE_ID": "page-123",
                    "FB_PAGE_TOKEN": "[REDACTED]",
                    "LLM_PROVIDER": "openai",
                }
            )
            completed = subprocess.run(
                [sys.executable, "-m", "fanpage_agent.main", "ops-status"],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("sheet-123", completed.stdout)
        self.assertNotIn("chat-123", completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["summary"]["runtime_failed"], 2)
        checks = {item["name"]: item for item in payload["runtime_config"]["checks"]}
        self.assertTrue(checks["telegram_delivery"]["ok"])
        self.assertTrue(checks["facebook_publish"]["ok"])
        self.assertFalse(checks["google_store"]["ok"])
        self.assertIn("google_service_account_file_not_found", checks["google_store"]["reason_codes"])
        self.assertFalse(checks["llm_generation"]["ok"])
        self.assertIn("missing_llm_api_key", checks["llm_generation"]["reason_codes"])

    def test_ops_status_fail_on_runtime_returns_nonzero(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "artifacts"
            artifacts.mkdir(parents=True)
            env = isolated_subprocess_env()
            env["ARTIFACTS_DIR"] = str(artifacts)
            completed = subprocess.run(
                [sys.executable, "-m", "fanpage_agent.main", "ops-status", "--fail-on-runtime"],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertGreaterEqual(payload["summary"]["runtime_failed"], 1)


if __name__ == "__main__":
    unittest.main()
