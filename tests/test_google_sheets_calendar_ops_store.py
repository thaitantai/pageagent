import unittest
from pathlib import Path

from fanpage_agent.adapters.google_sheets_store import GoogleSheetsStore
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.publishing.planner import PlannerTool
from tests.test_google_sheets_store import FakeSheetsService


class GoogleSheetsCalendarOpsStoreTest(unittest.TestCase):
    def test_attach_draft_caption_ref_and_list_calendar_items(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        plan = PlannerTool().plan_week(profile=profile, start_date="2026-06-24", days=1)
        tables: dict[str, list[list[str]]] = {}
        store = GoogleSheetsStore(
            settings=Settings(artifacts_dir=Path("/tmp"), google_sheets_id="sheet-123", google_service_account_file="/tmp/creds.json"),
            service=FakeSheetsService(tables),
        )

        store.append_plan(profile.brand_id, plan)
        updated = store.attach_draft_caption_ref(
            calendar_id=f"{plan.plan_title}-1",
            caption_ref="artifacts/captions/daily-caption-weekly-plan-brand_abc-2026-06-24-1.json",
            updated_at="2026-06-24T08:30:00",
        )
        listed = store.list_calendar_items(approval_status="pending")

        self.assertTrue(updated["draft_caption_ref"].endswith("daily-caption-weekly-plan-brand_abc-2026-06-24-1.json"))
        self.assertEqual(listed[0]["calendar_id"], f"{plan.plan_title}-1")
        self.assertEqual(listed[0]["approval_status"], "pending")


if __name__ == "__main__":
    unittest.main()
