import csv
import tempfile
import unittest
from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.publishing.planner import PlannerTool
from fanpage_agent.tools.content.verifier import VerifierTool


class HistoryAndDuplicateCheckTest(unittest.TestCase):
    def test_read_post_history_and_flag_duplicate_plan_topic(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        plan = PlannerTool().plan_week(profile=profile, start_date="2026-06-01", days=2)

        with tempfile.TemporaryDirectory() as tmp:
            history_csv = Path(tmp) / "post_history.csv"
            with history_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["published_at", "topic", "hook", "pillar", "objective", "permalink", "reach", "engagement_rate"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "published_at": "2026-05-28",
                        "topic": plan.days[0].topic,
                        "hook": plan.days[0].hook,
                        "pillar": plan.days[0].pillar,
                        "objective": plan.days[0].objective,
                        "permalink": "https://example.com/post-1",
                        "reach": "1200",
                        "engagement_rate": "0.08",
                    }
                )

            store = LocalSheetStore(calendar_csv=Path(tmp) / "calendar.csv", history_csv=history_csv)
            history = store.read_post_history(limit=10)
            result = VerifierTool().verify_plan(profile, plan, history=history)

        self.assertEqual(len(history), 1)
        self.assertFalse(result.passed)
        self.assertTrue(any("Duplicate topic with recent history" in issue for issue in result.issues))


if __name__ == "__main__":
    unittest.main()
