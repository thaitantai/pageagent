import unittest
from pathlib import Path

from fanpage_agent.adapters.google_sheets_store import GoogleSheetsStore
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.publishing.planner import PlannerTool
from tests.test_google_sheets_store import FakeSpreadsheetsResource, FakeSheetsService


class NoTablesSheetsService:
    def __init__(self, tables: dict[str, list[list[str]]]) -> None:
        self._spreadsheets = FakeSpreadsheetsResource(tables)

    def spreadsheets(self) -> FakeSpreadsheetsResource:
        return self._spreadsheets


class GoogleSheetsMetricsOpsStoreTest(unittest.TestCase):
    def test_record_post_metrics_updates_calendar_and_metrics_tab(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        plan = PlannerTool().plan_week(profile=profile, start_date="2026-06-25", days=1)
        tables: dict[str, list[list[str]]] = {}
        store = GoogleSheetsStore(
            settings=Settings(artifacts_dir=Path("/tmp"), google_sheets_id="sheet-123", google_service_account_file="/tmp/creds.json"),
            service=FakeSheetsService(tables),
        )

        store.append_plan(profile.brand_id, plan)
        store.publish_calendar_item(
            calendar_id=f"{plan.plan_title}-1",
            published_at="2026-06-25T10:00:00",
            permalink="https://example.com/post-1",
        )
        payload = store.record_post_metrics(
            calendar_id=f"{plan.plan_title}-1",
            reach=1800,
            engagements=126,
            leads=11,
            recorded_at="2026-06-26T08:00:00",
        )
        metrics = store.read_post_metrics()

        self.assertEqual(payload["calendar"]["reach"], "1800")
        self.assertEqual(payload["calendar"]["engagement_rate"], "0.07")
        self.assertEqual(payload["metric"]["engagements"], "126")
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].reach, 1800)
        self.assertEqual(metrics[0].engagements, 126)
        self.assertEqual(metrics[0].leads, 11)

    def test_record_post_metrics_does_not_require_fake_tables_attr(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        plan = PlannerTool().plan_week(profile=profile, start_date="2026-06-25", days=1)
        tables: dict[str, list[list[str]]] = {}
        store = GoogleSheetsStore(
            settings=Settings(artifacts_dir=Path("/tmp"), google_sheets_id="sheet-123", google_service_account_file="/tmp/creds.json"),
            service=NoTablesSheetsService(tables),
        )

        store.append_plan(profile.brand_id, plan)
        store.publish_calendar_item(
            calendar_id=f"{plan.plan_title}-1",
            published_at="2026-06-25T10:00:00",
            permalink="https://example.com/post-1",
        )
        payload = store.record_post_metrics(
            calendar_id=f"{plan.plan_title}-1",
            reach=1800,
            engagements=126,
            leads=11,
            recorded_at="2026-06-26T08:00:00",
        )
        metrics = store.read_post_metrics()

        self.assertEqual(payload["calendar"]["reach"], "1800")
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].engagements, 126)


if __name__ == "__main__":
    unittest.main()
