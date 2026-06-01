import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CommunityTriageCliTest(unittest.TestCase):
    def test_triage_community_outputs_batch_and_saves_artifact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifacts_dir = tmpdir / "artifacts"
            comments = tmpdir / "comment_inbox.csv"
            comments.write_text(
                "created_at,source,message\n"
                "2026-06-24,inbox,Chi phí soi da là bao nhiêu?\n"
                "2026-06-24,comment,Mình bị kích ứng sau treatment, cần hỗ trợ gấp\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["ARTIFACTS_DIR"] = str(artifacts_dir)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fanpage_agent.main",
                    "triage-community",
                    "--brand-file",
                    str(sample),
                    "--comment-file",
                    str(comments),
                    "--save",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )

            payload = json.loads(completed.stdout)
            artifact = artifacts_dir / "community" / "community-triage.json"
            artifact_exists = artifact.exists()

            self.assertTrue(artifact_exists)
            self.assertEqual(payload["summary"]["total_items"], 2)
            self.assertEqual(payload["summary"]["by_category"]["lead"], 1)
            self.assertEqual(payload["summary"]["by_category"]["complaint"], 1)
            self.assertEqual(payload["items"][0]["category"], "lead")
            self.assertEqual(payload["items"][1]["priority"], "urgent")
            self.assertTrue(payload["items"][1]["escalation_required"])


if __name__ == "__main__":
    unittest.main()
