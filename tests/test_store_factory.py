import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fanpage_agent.config import Settings
from fanpage_agent.main import DEFAULT_CALENDAR_FILE, DEFAULT_HISTORY_FILE, DEFAULT_METRICS_FILE
from fanpage_agent.adapters.store_factory import build_store


class BuildStoreTest(unittest.TestCase):
    def test_build_store_defaults_to_local_backend(self) -> None:
        settings = Settings(artifacts_dir=Path("/tmp"))
        args = argparse.Namespace(
            store_backend=None,
            calendar_file=str(DEFAULT_CALENDAR_FILE),
            history_file=str(DEFAULT_HISTORY_FILE),
            metrics_file=str(DEFAULT_METRICS_FILE),
        )

        store = build_store(settings=settings, args=args)

        self.assertEqual(store.__class__.__name__, "LocalSheetStore")

    def test_every_backend_satisfies_the_store_protocol(self) -> None:
        """Contract test: backend drift fails here instead of in production."""
        from fanpage_agent.adapters.google_sheets_store import GoogleSheetsStore
        from fanpage_agent.adapters.sheet_store import LocalSheetStore
        from fanpage_agent.adapters.sqlite_store import UnifiedStore
        from fanpage_agent.adapters.store_protocol import FanpageStore

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            backends = [
                LocalSheetStore(calendar_csv=tmpdir / "calendar.csv"),
                UnifiedStore(db_path=tmpdir / "store.db"),
                GoogleSheetsStore(
                    settings=Settings(
                        google_sheets_id="sheet-123",
                        google_service_account_file=str(tmpdir / "fake.json"),
                    ),
                    service=object(),
                ),
            ]
            for store in backends:
                with self.subTest(backend=store.__class__.__name__):
                    self.assertIsInstance(store, FanpageStore)

    def test_build_store_uses_google_backend_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            creds = Path(tmp) / "service-account.json"
            creds.write_text("{}", encoding="utf-8")
            settings = Settings(
                artifacts_dir=Path("/tmp"),
                store_backend="local",
                google_sheets_id="sheet-123",
                google_service_account_file=str(creds),
            )
            args = argparse.Namespace(
                store_backend="google",
                calendar_file=str(DEFAULT_CALENDAR_FILE),
                history_file=str(DEFAULT_HISTORY_FILE),
                metrics_file=str(DEFAULT_METRICS_FILE),
            )

            with patch("fanpage_agent.adapters.store_factory.GoogleSheetsStore") as google_cls:
                google_cls.return_value = object()
                store = build_store(settings=settings, args=args)

        google_cls.assert_called_once()
        self.assertIs(store, google_cls.return_value)


if __name__ == "__main__":
    unittest.main()
