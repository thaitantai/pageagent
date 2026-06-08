"""Test DataFetchTool with mock FacebookClient + mock store."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fanpage_agent.adapters.google_sheets_store import GoogleSheetsStore
from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.config import Settings
from fanpage_agent.tools.data.data_fetch import DataFetchTool


class MockFacebookClient:
    """Minimal mock returning controlled data."""

    def __init__(self, settings: object = None) -> None:
        self.settings = settings

    def get_page_posts(self, limit: int = 25) -> list[dict]:
        return [
            {
                "id": "123_001",
                "message": "Post 1 về skincare",
                "created_time": "2026-06-08T10:00:00+0000",
                "permalink_url": "https://fb.com/123_001",
                "reach": 1500,
                "likes": 100,
                "comments": 20,
                "shares": 5,
                "engagements": 125,
                "engagement_rate": 0.0833,
            },
            {
                "id": "123_002",
                "message": "Post 2 về retinol",
                "created_time": "2026-06-07T14:00:00+0000",
                "permalink_url": "https://fb.com/123_002",
                "reach": 800,
                "likes": 50,
                "comments": 10,
                "shares": 2,
                "engagements": 62,
                "engagement_rate": 0.0775,
            },
        ]

    def get_comments(
        self, post_id: str, limit: int = 25
    ) -> list[dict]:
        return [
            {
                "id": f"c_{post_id}_1",
                "message": "Sản phẩm này dùng có tốt không?",
                "from_name": "Nguyễn Văn A",
                "created_time": "2026-06-08T11:00:00+0000",
            },
        ]


class FakeSheetsService:
    """Minimal Google Sheets API mock for bulk_load_data testing."""

    class FakeValuesResource:
        def __init__(self, tables: dict) -> None:
            self.tables = tables

        def get(self, spreadsheetId: str, range: str) -> "FakeRequest":
            tab = range.split("!", 1)[0]
            return FakeRequest({"values": self.tables.get(tab, [])})

        def update(
            self, spreadsheetId: str, range: str, valueInputOption: str, body: dict
        ) -> "FakeRequest":
            tab = range.split("!", 1)[0]
            self.tables[tab] = body["values"]
            return FakeRequest({"updatedRange": range})

    class FakeSpreadsheetsResource:
        def __init__(self, tables: dict) -> None:
            self._values = FakeSheetsService.FakeValuesResource(tables)

        def values(self) -> "FakeSheetsService.FakeValuesResource":
            return self._values

        def get(self, spreadsheetId: str) -> "FakeRequest":
            return FakeRequest({
                "sheets": [
                    {"properties": {"title": tab}}
                    for tab in self._values.tables
                ]
            })

        def batchUpdate(self, spreadsheetId: str, body: dict) -> "FakeRequest":
            # Simulate creating a new tab
            for req in body.get("requests", []):
                props = req.get("addSheet", {}).get("properties", {})
                title = props.get("title", "")
                if title and title not in self._values.tables:
                    self._values.tables[title] = []
            return FakeRequest({"replies": []})

    def __init__(self, tables: dict) -> None:
        self.tables = tables
        self._spreadsheets = self.FakeSpreadsheetsResource(tables)

    def spreadsheets(self) -> FakeSpreadsheetsResource:
        return self._spreadsheets


class FakeRequest:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def execute(self) -> dict:
        return self.payload


class DataFetchToolTest(unittest.TestCase):

    def test_fetch_all_with_google_sheets_store(self) -> None:
        """fetch_all populates post_history + post_metrics tabs."""
        tables: dict[str, list[list[str]]] = {}
        settings = Settings(
            artifacts_dir=Path("/tmp"),
            google_sheets_id="sheet-123",
            google_service_account_file="/tmp/fake.json",
        )
        store = GoogleSheetsStore(
            settings=settings,
            service=FakeSheetsService(tables),
        )
        service = DataFetchTool(
            settings=settings,
            fb_client=MockFacebookClient(),
            store=store,
        )
        result = service.fetch_all(post_limit=10, comment_posts=0, comment_limit=0)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["posts_fetched"], 2)
        self.assertGreaterEqual(result["history_written"], 2)
        self.assertGreaterEqual(result["metrics_written"], 2)

        # Verify data is readable
        history = store.read_post_history(limit=5)
        metrics = store.read_post_metrics()
        self.assertGreaterEqual(len(history), 2)
        self.assertGreaterEqual(len(metrics), 2)
        self.assertEqual(history[0].permalink, "https://fb.com/123_001")
        self.assertEqual(metrics[0].reach, 1500)

    def test_fetch_all_with_local_sheet_store(self) -> None:
        """fetch_all populates local CSV files."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history_csv = tmp_path / "post_history.csv"
            metrics_csv = tmp_path / "post_metrics.csv"

            store = LocalSheetStore(
                calendar_csv=tmp_path / "calendar.csv",
                history_csv=history_csv,
                metrics_csv=metrics_csv,
            )
            settings = Settings(artifacts_dir=tmp_path)
            service = DataFetchTool(
                settings=settings,
                fb_client=MockFacebookClient(),
                store=store,
            )
            result = service.fetch_all(post_limit=10, comment_posts=0, comment_limit=0)

            self.assertEqual(result["history_written"], 2)
            self.assertEqual(result["metrics_written"], 2)
            self.assertTrue(history_csv.exists())
            self.assertTrue(metrics_csv.exists())

            # Verify readable
            history = store.read_post_history(limit=5)
            metrics = store.read_post_metrics()
            self.assertEqual(len(history), 2)
            self.assertEqual(len(metrics), 2)

    def test_fetch_comments_dedup(self) -> None:
        """Comments are deduped by FB comment ID."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            comment_csv = tmp_path / "comments.csv"

            # Pre-seed with one existing comment
            import csv
            with comment_csv.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["id", "post_id", "created_at", "source", "message"])
                w.writeheader()
                w.writerow({
                    "id": "c_123_001_1",
                    "post_id": "123_001",
                    "created_at": "2026-06-08T11:00:00+0000",
                    "source": "facebook_comment",
                    "message": "Sản phẩm này dùng có tốt không?",
                })

            service = DataFetchTool(
                settings=Settings(artifacts_dir=tmp_path),
                fb_client=MockFacebookClient(),
                store=None,
                comment_csv=comment_csv,
            )
            count = service.fetch_comments(post_limit=5, comment_limit=25)
            # 1 comment (c_123_002_1) is new; c_123_001_1 already exists
            self.assertEqual(count, 1)

    def test_fetch_post_history_only(self) -> None:
        """fetch_post_history returns correct row count."""
        tables: dict[str, list[list[str]]] = {}
        settings = Settings(
            artifacts_dir=Path("/tmp"),
            google_sheets_id="sheet-456",
            google_service_account_file="/tmp/fake.json",
        )
        store = GoogleSheetsStore(
            settings=settings,
            service=FakeSheetsService(tables),
        )
        service = DataFetchTool(
            settings=settings,
            fb_client=MockFacebookClient(),
            store=store,
        )
        count = service.fetch_post_history(post_limit=10)
        self.assertEqual(count, 2)
        history = store.read_post_history(limit=5)
        self.assertEqual(len(history), 2)

    def test_fetch_post_metrics_only(self) -> None:
        """fetch_post_metrics returns correct row count."""
        tables: dict[str, list[list[str]]] = {}
        settings = Settings(
            artifacts_dir=Path("/tmp"),
            google_sheets_id="sheet-789",
            google_service_account_file="/tmp/fake.json",
        )
        store = GoogleSheetsStore(
            settings=settings,
            service=FakeSheetsService(tables),
        )
        service = DataFetchTool(
            settings=settings,
            fb_client=MockFacebookClient(),
            store=store,
        )
        count = service.fetch_post_metrics(post_limit=10)
        self.assertEqual(count, 2)
        metrics = store.read_post_metrics()
        self.assertEqual(len(metrics), 2)


if __name__ == "__main__":
    unittest.main()
