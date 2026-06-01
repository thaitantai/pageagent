import csv
import tempfile
import unittest
from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.services.planner import PlannerService


class LocalSheetStoreTest(unittest.TestCase):
    def test_append_plan_writes_rows_to_calendar_csv(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        plan = PlannerService().plan_week(profile=profile, start_date="2026-06-01", days=2)

        with tempfile.TemporaryDirectory() as tmp:
            calendar = Path(tmp) / "content_calendar.csv"
            store = LocalSheetStore(calendar)
            store.append_plan(profile.brand_id, plan)

            with calendar.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["brand_id"], "brand_abc")
        self.assertEqual(rows[0]["topic"], plan.days[0].topic)
        self.assertEqual(rows[1]["approval_status"], "pending")


if __name__ == "__main__":
    unittest.main()
