import tempfile
import unittest
from pathlib import Path

from fanpage_agent.adapters.google_sheets_store import GoogleSheetsStore
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.publishing.planner import PlannerTool


class FakeValuesResource:
    def __init__(self, tables: dict[str, list[list[str]]]) -> None:
        self.tables = tables

    def get(self, spreadsheetId: str, range: str):
        tab = range.split("!", 1)[0]
        return FakeRequest({"values": self.tables.get(tab, [])})

    def append(self, spreadsheetId: str, range: str, valueInputOption: str, body: dict):
        tab = range.split("!", 1)[0]
        rows = body["values"]
        self.tables.setdefault(tab, []).extend(rows)
        return FakeRequest({"updates": {"updatedRows": len(rows)}})

    def update(self, spreadsheetId: str, range: str, valueInputOption: str, body: dict):
        tab, row_range = range.split("!", 1)
        start_row_ref = row_range.split(":", 1)[0]
        row_number = int("".join(ch for ch in start_row_ref if ch.isdigit()) or "1")
        rows = self.tables.setdefault(tab, [])
        values = body["values"]
        while len(rows) < row_number - 1:
            rows.append([])
        for index, value_row in enumerate(values, start=row_number - 1):
            if len(rows) <= index:
                rows.append([])
            rows[index] = value_row
        return FakeRequest({"updatedRange": range})


class FakeSpreadsheetsResource:
    def __init__(self, tables: dict[str, list[list[str]]]) -> None:
        self._values = FakeValuesResource(tables)

    def values(self) -> FakeValuesResource:
        return self._values


class FakeSheetsService:
    def __init__(self, tables: dict[str, list[list[str]]]) -> None:
        self.tables = tables
        self._spreadsheets = FakeSpreadsheetsResource(tables)

    def spreadsheets(self) -> FakeSpreadsheetsResource:
        return self._spreadsheets


class FakeRequest:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def execute(self) -> dict:
        return self.payload


class GoogleSheetsStoreTest(unittest.TestCase):
    def test_append_plan_and_publish_flow_updates_fake_sheet_data(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        plan = PlannerTool().plan_week(profile=profile, start_date="2026-06-01", days=1)
        tables: dict[str, list[list[str]]] = {}
        store = GoogleSheetsStore(
            settings=Settings(artifacts_dir=Path("/tmp"), google_sheets_id="sheet-123", google_service_account_file="/tmp/creds.json"),
            service=FakeSheetsService(tables),
        )

        store.append_plan(profile.brand_id, plan)
        row = store.approve_calendar_item(
            calendar_id=f"{plan.plan_title}-1",
            approved_by="Tai",
            final_caption_ref="artifacts/captions/caption.json",
            approved_at="2026-06-01",
        )
        published = store.publish_calendar_item(
            calendar_id=f"{plan.plan_title}-1",
            published_at="2026-06-02",
            permalink="https://example.com/post-1",
            reach=1200,
            engagement_rate=0.08,
        )
        history = store.read_post_history(limit=5)

        self.assertEqual(row["approval_status"], "approved")
        self.assertEqual(published["status"], "published")
        self.assertEqual(published["permalink"], "https://example.com/post-1")
        self.assertEqual(history[0].topic, plan.days[0].topic)

    def test_read_post_metrics_uses_prefix_tabs(self) -> None:
        tables = {
            "fp_post_metrics": [
                ["published_at", "topic", "pillar", "objective", "reach", "engagements", "leads"],
                ["2026-06-02", "Routine dưỡng da", "education", "reach", "1000", "80", "4"],
            ]
        }
        store = GoogleSheetsStore(
            settings=Settings(
                artifacts_dir=Path("/tmp"),
                google_sheets_id="sheet-123",
                google_service_account_file="/tmp/creds.json",
                google_sheets_tabs_prefix="fp",
            ),
            service=FakeSheetsService(tables),
        )

        metrics = store.read_post_metrics()

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].reach, 1000)
        self.assertEqual(metrics[0].engagements, 80)
        self.assertEqual(metrics[0].leads, 4)

    def test_requires_sheet_id_and_service_account_file(self) -> None:
        settings = Settings(artifacts_dir=Path("/tmp"))

        with self.assertRaises(RuntimeError):
            GoogleSheetsStore(settings=settings, service=FakeSheetsService({}))


if __name__ == "__main__":
    unittest.main()
