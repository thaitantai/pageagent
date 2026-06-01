import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fanpage_agent.main import EXPECTED_HERMES_CRON_JOBS
from tests.test_env import isolated_subprocess_env


class HermesCronStatusCliTest(unittest.TestCase):
    def test_hermes_cron_status_reports_all_jobs_ok(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            scripts_dir = tmpdir / "scripts"
            scripts_dir.mkdir()
            jobs = []
            for idx, (name, expected) in enumerate(EXPECTED_HERMES_CRON_JOBS.items(), start=1):
                wrapper = scripts_dir / expected["script"]
                wrapper.write_text(
                    f"#!/usr/bin/env bash\nset -euo pipefail\nexec /repo/{expected['project_script']}\n",
                    encoding="utf-8",
                )
                wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
                jobs.append(
                    {
                        "id": f"job-{idx}",
                        "name": name,
                        "script": expected["script"],
                        "no_agent": True,
                        "schedule": {"display": expected["schedule"]},
                        "schedule_display": expected["schedule"],
                        "deliver": "local",
                        "workdir": "/repo",
                        "enabled": True,
                        "state": "scheduled",
                        "last_delivery_error": None,
                    }
                )
            jobs_file = tmpdir / "jobs.json"
            jobs_file.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "hermes-cron-status",
                    "--jobs-file",
                    str(jobs_file),
                    "--scripts-dir",
                    str(scripts_dir),
                    "--workdir",
                    "/repo",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["summary"], {"expected": 9, "configured": 9, "ok": 9, "failed": 0})
        self.assertTrue(all(item["ok"] for item in payload["checks"]))

    def test_hermes_cron_status_fails_when_job_or_wrapper_is_wrong(self) -> None:
        root = Path(__file__).resolve().parents[1]
        name, expected = next(iter(EXPECTED_HERMES_CRON_JOBS.items()))
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            scripts_dir = tmpdir / "scripts"
            scripts_dir.mkdir()
            wrapper = scripts_dir / expected["script"]
            wrapper.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            jobs_file = tmpdir / "jobs.json"
            jobs_file.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "bad-job",
                                "name": name,
                                "script": "wrong.sh",
                                "no_agent": False,
                                "schedule_display": "* * * * *",
                                "deliver": "origin",
                                "workdir": "/wrong",
                                "enabled": False,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "hermes-cron-status",
                    "--jobs-file",
                    str(jobs_file),
                    "--scripts-dir",
                    str(scripts_dir),
                    "--workdir",
                    "/repo",
                ],
                cwd=root,
                env=isolated_subprocess_env(),
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 1, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertGreater(payload["summary"]["failed"], 0)
        first = payload["checks"][0]
        self.assertIn("wrong_schedule", first["errors"])
        self.assertIn("wrong_script", first["errors"])
        self.assertIn("not_no_agent", first["errors"])
        self.assertIn("wrong_deliver", first["errors"])
        self.assertIn("wrong_workdir", first["errors"])
        self.assertIn("not_enabled", first["errors"])
        self.assertIn("wrapper_not_executable", first["errors"])
        self.assertIn("wrapper_wrong_target", first["errors"])


if __name__ == "__main__":
    unittest.main()
