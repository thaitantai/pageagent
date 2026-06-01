from __future__ import annotations

import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

EXPECTED_WRAPPERS = {
    "run_daily_packet.sh": "deliver-daily-packet",
    "run_weekly_report.sh": "deliver-weekly-report",
    "run_operator_digest.sh": "deliver-operator-digest",
    "run_research_brief.sh": "deliver-research-brief",
    "run_triage_community.sh": "deliver-triage-community",
    "run_approved_triage_replies.sh": "deliver-approved-triage-replies",
    "run_approval_queue.sh": "deliver-approval-queue",
    "run_approval_audit.sh": "deliver-approval-audit",
    "run_metrics_backlog.sh": "deliver-metrics-backlog",
}


class CronWrapperScriptTest(unittest.TestCase):
    def test_all_cron_delivery_lanes_have_executable_wrappers(self) -> None:
        for script_name, command in EXPECTED_WRAPPERS.items():
            with self.subTest(script=script_name):
                script_path = SCRIPTS_DIR / script_name
                self.assertTrue(script_path.exists(), f"missing cron wrapper: {script_name}")
                self.assertTrue(os.access(script_path, os.X_OK), f"cron wrapper is not executable: {script_name}")

                content = script_path.read_text(encoding="utf-8")
                self.assertIn("set -euo pipefail", content)
                self.assertIn('PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"', content)
                self.assertIn(command, content)
                self.assertIn("--save", content)
                self.assertIn("STORE_ARGS", content)
                self.assertIn('--store-backend "$STORE_BACKEND"', content)


if __name__ == "__main__":
    unittest.main()
