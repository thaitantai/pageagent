import unittest
from pathlib import Path

from fanpage_agent.adapters.google_sheets_store import GoogleSheetsStore
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.services.planner import PlannerService
from tests.test_google_sheets_store import FakeSheetsService


class GoogleSheetsMetricsBacklogStoreTest(unittest.TestCase):
    def test_list_calendar_items_filters_metrics_pending_rows(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        plan = PlannerService().plan_week(profile=profile, start_date="2026-06-27", days=2)
        tables: dict[str, list[list[str]]] = {}
        store = GoogleSheetsStore(
            settings=Settings(artifacts_dir=Path("/tmp"), google_sheets_id="sheet-123", google_service_account_file="/tmp/creds.json"),
            service=FakeSheetsService(tables),
        )

        store.append_plan(profile.brand_id, plan)
        store.publish_calendar_item(f"{plan.plan_title}-1", "2026-06-27T10:00:00", "https://example.com/post-1")
        store.publish_calendar_item(f"{plan.plan_title}-2", "2026-06-28T10:00:00", "https://example.com/post-2")
        store.record_post_metrics(f"{plan.plan_title}-1", 1700, 119, 9, "2026-06-28T08:00:00")

        items = store.list_calendar_items(status="published", metrics_pending=True)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["calendar_id"], f"{plan.plan_title}-2")
        self.assertEqual(items[0]["reach"], "0")


if __name__ == "__main__":
    unittest.main()
