import unittest
from pathlib import Path

from fanpage_agent.adapters.google_sheets_store import GoogleSheetsStore
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.services.community_triage import CommunityTriageService
from tests.test_google_sheets_store import FakeSheetsService


class GoogleSheetsTriageStoreTest(unittest.TestCase):
    def test_upsert_and_approve_triage_rows_in_fake_sheet(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        batch = CommunityTriageService().triage_from_csv(profile=profile, comment_csv=Path(__file__).resolve().parents[1] / "data" / "comment_inbox.csv")
        tables: dict[str, list[list[str]]] = {}
        store = GoogleSheetsStore(
            settings=Settings(artifacts_dir=Path("/tmp"), google_sheets_id="sheet-123", google_service_account_file="/tmp/creds.json"),
            service=FakeSheetsService(tables),
        )

        rows = store.upsert_triage_items(profile.brand_id, batch.items)
        approved = store.approve_triage_reply(
            triage_id=rows[0]["triage_id"],
            approved_by="Tai",
            approved_at="2026-06-24T09:00:00",
            assigned_to="closer-1",
        )

        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "new")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["approved_by"], "Tai")
        self.assertEqual(approved["assigned_to"], "closer-1")


if __name__ == "__main__":
    unittest.main()
