from __future__ import annotations

import json
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.config import Settings


class FakeHttpResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeHttpErrorResponse:
    """Simulates an HTTPError for the urllib.error.HTTPError path."""

    def __init__(self, code: int, body: dict) -> None:
        self.code = code
        self._body = body

    def read(self) -> bytes:
        return json.dumps(self._body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FacebookClientTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.settings = Settings.from_env(
            env={
                "FB_PAGE_ID": "883890888134656",
                "FB_PAGE_TOKEN": "test-page-token",
                "FB_API_VERSION": "v21.0",
            },
            root_dir=root,
            load_dotenv=False,
        )

    # ------------------------------------------------------------------
    # Init validation
    # ------------------------------------------------------------------

    def test_init_raises_without_page_id(self) -> None:
        root = Path(__file__).resolve().parents[1]
        s = Settings.from_env(
            env={"FB_PAGE_TOKEN": "token"},
            root_dir=root,
            load_dotenv=False,
        )
        with self.assertRaises(RuntimeError):
            FacebookClient(s)

    def test_init_raises_without_page_token(self) -> None:
        root = Path(__file__).resolve().parents[1]
        s = Settings.from_env(
            env={"FB_PAGE_ID": "123"},
            root_dir=root,
            load_dotenv=False,
        )
        with self.assertRaises(RuntimeError):
            FacebookClient(s)

    def test_init_succeeds_with_valid_settings(self) -> None:
        client = FacebookClient(self.settings)
        self.assertEqual(client.page_id, "883890888134656")
        self.assertEqual(client.api_version, "v21.0")

    # ------------------------------------------------------------------
    # post_to_page
    # ------------------------------------------------------------------

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_post_to_page_basic(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse({"id": "123_456"})
        client = FacebookClient(self.settings)
        result = client.post_to_page("Hello world")
        self.assertEqual(result, {"id": "123_456"})
        # Verify URL contains access_token
        req = mock_urlopen.call_args[0][0]
        self.assertIn("access_token=test-page-token", req.full_url)
        # Verify POST body contains message
        self.assertIn(b"Hello+world", req.data)

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_post_to_page_with_link(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse({"id": "789_012"})
        client = FacebookClient(self.settings)
        result = client.post_to_page("Check this out", link="https://example.com")
        self.assertEqual(result, {"id": "789_012"})
        # POST body contains the message and link (not in URL)
        req = mock_urlopen.call_args[0][0]
        body = req.data.decode("utf-8")
        self.assertIn("Check+this+out", body)
        self.assertIn("https%3A%2F%2Fexample.com", body)

    # ------------------------------------------------------------------
    # reply_to_comment
    # ------------------------------------------------------------------

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_reply_to_comment(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse({"id": "reply_999"})
        client = FacebookClient(self.settings)
        result = client.reply_to_comment("comment_456", "Thanks!")
        self.assertEqual(result, {"id": "reply_999"})
        url = mock_urlopen.call_args[0][0].full_url
        self.assertIn("/v21.0/comment_456/comments", url)

    # ------------------------------------------------------------------
    # get_post_insights
    # ------------------------------------------------------------------

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_get_post_insights(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse({
            "id": "123_456",
            "message": "My post",
            "created_time": "2026-01-01T00:00:00+0000",
            "permalink_url": "https://fb.com/123_456",
            "likes": {"summary": {"total_count": 42}},
            "comments": {"summary": {"total_count": 7}},
            "shares": {"count": 3},
        })
        client = FacebookClient(self.settings)
        result = client.get_post_insights("123_456")
        self.assertEqual(result["id"], "123_456")
        self.assertEqual(result["message"], "My post")
        self.assertEqual(result["likes"], 42)
        self.assertEqual(result["comments"], 7)
        self.assertEqual(result["shares"], 3)
        self.assertEqual(result["engagements"], 52)
        self.assertEqual(result["permalink_url"], "https://fb.com/123_456")

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_get_post_insights_zero_counts(self, mock_urlopen) -> None:
        """Edge case: no likes/comments/shares data."""
        mock_urlopen.return_value = FakeHttpResponse({
            "id": "123_456",
            "message": "No engagement",
            "created_time": "2026-01-01T00:00:00+0000",
            "permalink_url": "https://fb.com/123_456",
        })
        client = FacebookClient(self.settings)
        result = client.get_post_insights("123_456")
        self.assertEqual(result["likes"], 0)
        self.assertEqual(result["comments"], 0)
        self.assertEqual(result["shares"], 0)
        self.assertEqual(result["engagements"], 0)

    # ------------------------------------------------------------------
    # get_page_posts
    # ------------------------------------------------------------------

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_get_page_posts(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse({
            "data": [
                {
                    "id": "post_1",
                    "message": "First post",
                    "created_time": "2026-01-01T00:00:00+0000",
                    "permalink_url": "https://fb.com/post_1",
                    "likes": {"summary": {"total_count": 10}},
                    "comments": {"summary": {"total_count": 2}},
                    "shares": {"count": 1},
                },
                {
                    "id": "post_2",
                    "message": "Second post",
                    "created_time": "2026-01-02T00:00:00+0000",
                    "permalink_url": "https://fb.com/post_2",
                    "likes": {"summary": {"total_count": 5}},
                    "comments": {"summary": {"total_count": 0}},
                },
            ],
        })
        client = FacebookClient(self.settings)
        results = client.get_page_posts(limit=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], "post_1")
        self.assertEqual(results[0]["engagements"], 13)
        self.assertEqual(results[1]["id"], "post_2")
        self.assertEqual(results[1]["engagements"], 5)

    # ------------------------------------------------------------------
    # get_comments
    # ------------------------------------------------------------------

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_get_comments(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse({
            "data": [
                {
                    "id": "c_1",
                    "message": "Great post!",
                    "from": {"name": "Alice"},
                    "created_time": "2026-01-01T01:00:00+0000",
                },
                {
                    "id": "c_2",
                    "message": "Love it",
                    "from": {"name": "Bob"},
                    "created_time": "2026-01-01T02:00:00+0000",
                },
            ],
        })
        client = FacebookClient(self.settings)
        results = client.get_comments("post_1")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], "c_1")
        self.assertEqual(results[0]["from_name"], "Alice")
        self.assertEqual(results[1]["message"], "Love it")

    # ------------------------------------------------------------------
    # update_post / delete_post
    # ------------------------------------------------------------------

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_update_post(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse({"success": True})
        client = FacebookClient(self.settings)
        result = client.update_post("123_456", "Updated message")
        self.assertEqual(result, {"success": True})

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_delete_post(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse({"success": True})
        client = FacebookClient(self.settings)
        result = client.delete_post("123_456")
        self.assertEqual(result, {"success": True})

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_graph_api_error_raises_runtime_error(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse({
            "error": {
                "code": 190,
                "message": "Invalid OAuth access token",
                "type": "OAuthException",
            }
        })
        client = FacebookClient(self.settings)
        with self.assertRaises(RuntimeError) as ctx:
            client.get_post_insights("123_456")
        self.assertIn("190", str(ctx.exception))
        self.assertIn("Invalid OAuth", str(ctx.exception))

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_non_json_response_raises_runtime_error(self, mock_urlopen) -> None:
        class NonJsonResponse:
            def read(self) -> bytes:
                return b"<html>not json</html>"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        mock_urlopen.return_value = NonJsonResponse()
        client = FacebookClient(self.settings)
        with self.assertRaises(RuntimeError) as ctx:
            client.get_post_insights("123_456")
        self.assertIn("non-JSON", str(ctx.exception))

    # ------------------------------------------------------------------
    # get_conversations
    # ------------------------------------------------------------------

    @patch("fanpage_agent.adapters.facebook_client.urlopen")
    def test_get_conversations(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse({
            "data": [
                {"id": "conv_1", "message": "Hi", "unread": True},
            ],
        })
        client = FacebookClient(self.settings)
        results = client.get_conversations(limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "conv_1")


if __name__ == "__main__":
    unittest.main()
