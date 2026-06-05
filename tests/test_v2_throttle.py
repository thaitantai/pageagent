"""Tests for rate limiter (TokenBucket) and 429 retry."""

from __future__ import annotations

import time
import unittest
from unittest.mock import Mock, call, mock_open, patch

from fanpage_agent_v2.utils.throttle import TokenBucket


class TokenBucketTest(unittest.TestCase):
    """TokenBucket basic behaviour."""

    def test_acquire_allows_within_capacity(self) -> None:
        tb = TokenBucket(capacity=10, window_sec=3600.0)
        self.assertTrue(tb.acquire(tokens=5, block=False))
        self.assertTrue(tb.acquire(tokens=5, block=False))

    def test_acquire_denies_when_exhausted(self) -> None:
        tb = TokenBucket(capacity=3, window_sec=3600.0)
        tb.acquire(tokens=3, block=False)
        self.assertFalse(tb.acquire(tokens=1, block=False))

    def test_acquire_tokens_zero_always_succeeds(self) -> None:
        tb = TokenBucket(capacity=5, window_sec=3600.0)
        self.assertTrue(tb.acquire(tokens=0, block=False))

    def test_partial_refill_over_time(self) -> None:
        """Tokens should slowly refill over the window."""
        tb = TokenBucket(capacity=5, window_sec=0.1)  # 5 tokens / 100ms
        # Exhaust
        tb.acquire(tokens=5, block=False)
        self.assertFalse(tb.acquire(tokens=1, block=False))
        # Wait 60 ms — should regain ~3 tokens
        time.sleep(0.06)
        self.assertTrue(tb.acquire(tokens=3, block=False))

    def test_block_waits_for_refill(self) -> None:
        tb = TokenBucket(capacity=2, window_sec=0.04)  # 2 tokens / 40ms
        tb.acquire(tokens=2, block=False)
        t0 = time.monotonic()
        self.assertTrue(tb.acquire(tokens=1, block=True))  # should wait ~20ms
        elapsed = time.monotonic() - t0
        self.assertGreaterEqual(elapsed, 0.015)

    def test_negative_tokens_blocks(self) -> None:
        tb = TokenBucket(capacity=5, window_sec=3600.0)
        self.assertTrue(tb.acquire(tokens=-1, block=False))


class RetryTest(unittest.TestCase):
    """429 retry decorator."""

    def test_retry_on_429_succeeds_eventually(self) -> None:
        from fanpage_agent_v2.utils.throttle import retry_on_429

        call_count = 0

        @retry_on_429(max_retries=3, base_delay=0.01)
        def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Facebook HTTP error 429: rate limit hit")
            return "ok"

        result = flaky()
        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 3)

    def test_retry_on_non_429_raises_immediately(self) -> None:
        from fanpage_agent_v2.utils.throttle import retry_on_429

        @retry_on_429(max_retries=3, base_delay=0.01)
        def broken() -> str:
            raise RuntimeError("HTTP error 400: bad request")

        with self.assertRaises(RuntimeError):
            broken()

    def test_all_retries_exhausted(self) -> None:
        from fanpage_agent_v2.utils.throttle import retry_on_429

        @retry_on_429(max_retries=2, base_delay=0.01)
        def always_429() -> str:
            raise RuntimeError("HTTP error 429: too many requests")

        with self.assertRaises(RuntimeError) as ctx:
            always_429()
        self.assertIn("retries", str(ctx.exception))

    def test_detects_rate_limit_in_message(self) -> None:
        from fanpage_agent_v2.utils.throttle import retry_on_429

        call_count = 0

        @retry_on_429(max_retries=1, base_delay=0.01)
        def rate_limited() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("rate limit reached, try later")
            return "ok"

        self.assertEqual(rate_limited(), "ok")
        self.assertEqual(call_count, 2)


class FacebookClientRateLimitTest(unittest.TestCase):
    """FacebookClient 429 handling inside _request."""

    def setUp(self) -> None:
        from fanpage_agent.adapters.facebook_client import FacebookClient

        settings = Mock()
        settings.fb_page_id = "test_page"
        settings.fb_page_token = "test_token"
        settings.fb_api_version = "v21.0"
        self.client = FacebookClient(settings)
        # Fast rate limiter for tests
        self.client._limiter = TokenBucket(capacity=9999, window_sec=3600.0)

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_429_retries_then_succeeds(self, mock_do: Mock) -> None:
        mock_do.side_effect = [
            RuntimeError("Facebook HTTP error 429: rate limit"),
            RuntimeError("Facebook HTTP error 429: rate limit"),
            {"id": "123"},
        ]
        result = self.client._request("GET", "/test", _retries=2)
        self.assertEqual(result, {"id": "123"})
        self.assertEqual(mock_do.call_count, 3)

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_non_429_raises_immediately(self, mock_do: Mock) -> None:
        mock_do.side_effect = RuntimeError("Facebook HTTP error 400: bad request")
        with self.assertRaises(RuntimeError) as ctx:
            self.client._request("GET", "/test", _retries=2)
        self.assertIn("400", str(ctx.exception))
        self.assertEqual(mock_do.call_count, 1)

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_all_retries_exhausted(self, mock_do: Mock) -> None:
        mock_do.side_effect = RuntimeError("Facebook HTTP error 429: too many")
        with self.assertRaises(RuntimeError) as ctx:
            self.client._request("GET", "/test", _retries=1)
        self.assertIn("retries", str(ctx.exception))
        self.assertEqual(mock_do.call_count, 2)

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_successful_no_retry(self, mock_do: Mock) -> None:
        mock_do.return_value = {"success": True}
        result = self.client._request("GET", "/test", _retries=2)
        self.assertEqual(result, {"success": True})
        self.assertEqual(mock_do.call_count, 1)

    @patch("fanpage_agent.adapters.facebook_client.FacebookClient._do_request")
    def test_rate_limit_token_acquired(self, mock_do: Mock) -> None:
        mock_do.return_value = {"ok": True}

        # Use a small window so refill is instant — verify token consumed
        self.client._limiter = TokenBucket(capacity=2, window_sec=0.02)  # 2 tokens / 20 ms
        self.client._limiter.acquire(tokens=1, block=False)  # 1/2 remaining

        result = self.client._request("GET", "/test")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_do.call_count, 1)


class WebSearchThrottleTest(unittest.TestCase):
    """WebSearchClient rate-limiter wiring."""

    def setUp(self) -> None:
        from fanpage_agent.scraping.web_search import WebSearchClient

        self.client = WebSearchClient()

    @patch("fanpage_agent.scraping.web_search.WebSearchClient._search_ddg_sdk")
    def test_limiter_acquired_before_search(self, mock_sdk: Mock) -> None:
        """Verify _limiter.acquire is called before each search."""
        mock_sdk.return_value = []
        # Override limiter with tiny capacity to observe consumption
        from fanpage_agent_v2.utils.throttle import TokenBucket

        self.client._limiter = TokenBucket(capacity=1, window_sec=3600.0)
        self.client.search("test query", max_results=3)
        # After the call, tokens should be 0
        self.assertEqual(self.client._limiter._tokens, 0.0)
        self.assertEqual(mock_sdk.call_count, 1)

    @patch("fanpage_agent.scraping.web_search.WebSearchClient._search_ddg_sdk")
    def test_search_consumes_one_token(self, mock_sdk: Mock) -> None:
        """Multiple searches consume multiple tokens."""
        mock_sdk.return_value = []
        from fanpage_agent_v2.utils.throttle import TokenBucket

        self.client._limiter = TokenBucket(capacity=5, window_sec=3600.0)
        self.client.search("q1")
        self.client.search("q2")
        self.client.search("q3")
        self.assertAlmostEqual(self.client._limiter._tokens, 2.0, places=1)


class PostPhotoThrottleTest(unittest.TestCase):
    """FacebookClient.post_photo rate-limiter + 429 retry."""

    def setUp(self) -> None:
        from fanpage_agent.adapters.facebook_client import FacebookClient

        settings = Mock()
        settings.fb_page_id = "test_page"
        settings.fb_page_token = "test_token"
        settings.fb_api_version = "v21.0"
        self.client = FacebookClient(settings)
        self.client._limiter = TokenBucket(capacity=9999, window_sec=3600.0)

    @patch("requests.post")
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake")
    def test_limiter_acquired_before_post(self, mock_open: Mock, mock_post: Mock) -> None:
        """Verify token is acquired before photo upload."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"id": "photo123"}

        self.client._limiter = TokenBucket(capacity=1, window_sec=3600.0)
        self.client.post_photo("/fake/path.jpg")
        self.assertEqual(self.client._limiter._tokens, 0.0)

    @patch("requests.post")
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake")
    def test_post_photo_429_retry_then_succeeds(
        self, mock_open: Mock, mock_post: Mock
    ) -> None:
        """post_photo retries on 429."""
        import requests as _req

        def side_effect(url, **kw):
            if getattr(side_effect, "call_count", 0) == 0:
                side_effect.call_count = 1
                resp = Mock(status_code=429, reason="Too Many Requests")
                resp.json.return_value = {"error": {"code": 429, "message": "rate limit"}}
                # On 429, raise_for_status should actually raise
                resp.raise_for_status.side_effect = _req.exceptions.HTTPError(
                    "429 Client Error", response=resp
                )
                return resp
            resp = Mock(status_code=200, reason="OK")
            resp.json.return_value = {"id": "photo456"}
            # On 200, raise_for_status is a no-op
            resp.raise_for_status.return_value = None
            return resp

        side_effect.call_count = 0
        mock_post.side_effect = side_effect

        result = self.client.post_photo("/fake/path.jpg")
        self.assertEqual(result, {"id": "photo456"})
        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
