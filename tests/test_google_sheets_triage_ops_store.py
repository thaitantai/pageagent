import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fanpage_agent.adapters.google_sheets_store import GoogleSheetsStore
from fanpage_agent.config import Settings
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.services.community_triage import CommunityTriageService
from tests.test_google_sheets_store import FakeSheetsService


class GoogleSheetsTriageOpsStoreTest(unittest.TestCase):
    def test_list_resolve_and_reopen_triage_rows_in_fake_sheet(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sample = root / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)
        with TemporaryDirectory() as tmp:
            comments = Path(tmp) / "comment_inbox.csv"
            comments.write_text(
                "id,post_id,created_at,source,message\n"
                ",,2026-06-08,comment,Da thieu nuoc thi nen bat dau tu dau?\n",
                encoding="utf-8",
            )
            batch = CommunityTriageService().triage_from_csv(profile=profile, comment_csv=comments)
        tables: dict[str, list[list[str]]] = {}
        store = GoogleSheetsStore(
            settings=Settings(artifacts_dir=Path("/tmp"), google_sheets_id="sheet-123", google_service_account_file="/tmp/creds.json"),
            service=FakeSheetsService(tables),
        )

        rows = store.upsert_triage_items(profile.brand_id, batch.items)
        triage_id = rows[0]["triage_id"]
        store.resolve_triage_item(triage_id=triage_id, resolved_at="2026-06-24T10:00:00", assigned_to="closer-1")
        listed = store.list_triage_items(status="resolved")
        reopened = store.reopen_triage_item(triage_id=triage_id, reopened_at="2026-06-24T11:00:00", assigned_to="qa-reviewer")

        self.assertEqual(listed[0]["triage_id"], triage_id)
        self.assertEqual(listed[0]["status"], "resolved")
        self.assertEqual(reopened["status"], "reopened")
        self.assertEqual(reopened["assigned_to"], "qa-reviewer")


if __name__ == "__main__":
    unittest.main()
