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


if __name__ == "__main__":
    unittest.main()
