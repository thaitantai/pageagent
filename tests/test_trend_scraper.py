from __future__ import annotations

import threading
import unittest
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from fanpage_agent.models import TrendItem
from fanpage_agent.scraping.trend_scraper import DEFAULT_TREND_SOURCES, TrendScraper


# ---------------------------------------------------------------------------
# Local test server tra ve HTML mau
# ---------------------------------------------------------------------------
_HTML_BODY = """\
<html>
<head><title>Test Page</title></head>
<body>
    <h3 class="title-news"><a href="/skincare-1">Summer skincare tips from experts</a></h3>
    <h3 class="title-news"><a href="/skincare-2">Retinol for beginners guide</a></h3>
    <h3 class="title-news"><a href="/skincare-3">Sunscreen for oily skin</a></h3>
    <p>Some additional skincare content not in the selector.</p>
</body>
</html>
"""


class _TestHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        body = _HTML_BODY.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    # Silence logs
    def log_message(self, *_: object) -> None:
        pass


class TrendScraperTest(unittest.TestCase):
    """Test TrendScraper voi local HTTP server -- khong can internet."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = Path(tempfile.mkdtemp())
        cls._server = HTTPServer(("127.0.0.1", 0), _TestHandler)
        cls._port = cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._server.shutdown()

    @property
    def _url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def test_fetch_with_selector(self) -> None:
        """CSS selector phai trich xuat dung title + link."""
        scraper = TrendScraper(sources=[])
        items = scraper.fetch(self._url, name="test-local", selector="h3.title-news a")

        self.assertGreaterEqual(len(items), 1)
        self.assertIsInstance(items[0], TrendItem)
        self.assertIn("Summer skincare", items[0].title)
        self.assertEqual(items[0].source, "test-local")
        self.assertIn("skincare-1", items[0].url)

    def test_fetch_all_with_selector_source(self) -> None:
        """fetch_all voi source co selector phai parse dung."""
        scraper = TrendScraper(
            sources=[
                {
                    "name": "test-selector",
                    "url": self._url,
                    "selector": "h3.title-news a",
                }
            ]
        )
        items = scraper.fetch_all()
        self.assertGreaterEqual(len(items), 3)
        titles = [i.title for i in items]
        self.assertIn("Retinol for beginners guide", titles)

    def test_fallback_text_mode(self) -> None:
        """Khi khong co selector, phai fallback ve text splitting."""
        scraper = TrendScraper(
            sources=[
                {
                    "name": "test-text",
                    "url": self._url,
                    "selector": "",  # No selector -> fallback
                }
            ]
        )
        items = scraper.fetch_all()
        self.assertGreaterEqual(len(items), 1)
        self.assertIsInstance(items[0], TrendItem)
        self.assertTrue(len(items[0].title) > 0)

    def test_fetch_all_skips_on_error(self) -> None:
        """Source bi loi (URL khong ton tai) khong lam fail ca batch."""
        scraper = TrendScraper(
            sources=[
                {
                    "name": "broken",
                    "url": "http://127.0.0.1:1/nonexistent",
                    "selector": "h3",
                }
            ]
        )
        items = scraper.fetch_all()
        self.assertEqual(items, [])

    def test_fetch_empty_url(self) -> None:
        """URL rong tra ve []."""
        scraper = TrendScraper(sources=[])
        items = scraper.fetch("", name="empty")
        self.assertEqual(items, [])

    def test_default_sources_defined(self) -> None:
        """DEFAULT_TREND_SOURCES phai co 4 nguon VN thuc su."""
        self.assertEqual(len(DEFAULT_TREND_SOURCES), 4)
        names = {s["name"] for s in DEFAULT_TREND_SOURCES}
        self.assertIn("VnExpress - Sức khỏe", names)
        self.assertIn("24h - Làm đẹp", names)
        self.assertIn("24h - Sức khỏe", names)
        self.assertIn("Afamily - Sức khỏe", names)
        for s in DEFAULT_TREND_SOURCES:
            self.assertIn("name", s)
            self.assertIn("url", s)
            self.assertIn("selector", s)

    def test_trend_item_model(self) -> None:
        """TrendItem khoi tao duoc voi cac field co ban."""
        item = TrendItem(title="Test Trend", source="test", url="https://example.com", snippet="Snippet text")
        self.assertEqual(item.title, "Test Trend")
        self.assertEqual(item.source, "test")
        self.assertEqual(item.url, "https://example.com")
        self.assertEqual(item.snippet, "Snippet text")
        self.assertEqual(item.relevance, "")


import tempfile  # noqa: E402 (needed by setUpClass)

if __name__ == "__main__":
    unittest.main()
