from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from fanpage_agent.config import Settings
from fanpage_agent.tools.analytics.analytics_reviewer import AnalyticsReviewer, _parse_fb_datetime, _parse_int


class TestParseHelpers:
    def test_parse_fb_datetime_utc(self):
        dt = _parse_fb_datetime("2026-06-01T10:00:00+0000")
        assert dt.year == 2026
        assert dt.month == 6
        assert dt.day == 1
        assert dt.hour == 10

    def test_parse_fb_datetime_z(self):
        dt = _parse_fb_datetime("2026-06-01T10:00:00Z")
        assert dt.year == 2026
        assert dt.hour == 10

    def test_parse_fb_datetime_invalid(self):
        dt = _parse_fb_datetime("")
        assert dt == datetime.min.replace(tzinfo=timezone.utc)

    def test_parse_int_none(self):
        assert _parse_int(None) == 0

    def test_parse_int_str(self):
        assert _parse_int("42") == 42

    def test_parse_int_int(self):
        assert _parse_int(42) == 42


class TestAnalyticsReviewer:
    @pytest.fixture
    def settings(self):
        s = MagicMock(spec=Settings)
        s.fb_page_id = "test_page"
        s.fb_page_token = "test_token"
        s.fb_api_version = "v21.0"
        return s

    @pytest.fixture
    def fb_client(self):
        return MagicMock()

    @pytest.fixture
    def store(self):
        store = MagicMock()
        store.list_calendar_items.return_value = [
            {
                "calendar_id": "cal_001",
                "date": "2026-06-01",
                "topic": "review sản phẩm mới",
                "pillar": "educational",
                "objective": "awareness",
                "status": "published",
                "published_at": "2026-06-01T08:00:00",
                "hook": "review sản phẩm",
            },
            {
                "calendar_id": "cal_002",
                "date": "2026-06-02",
                "topic": "tips chăm sóc da",
                "pillar": "educational",
                "objective": "awareness",
                "status": "published",
                "published_at": "2026-06-02T08:00:00",
                "hook": "chăm sóc da",
            },
        ]
        store.read_post_metrics.return_value = []
        return store

    @pytest.fixture
    def reviewer(self, settings, fb_client):
        return AnalyticsReviewer(settings, fb_client=fb_client)

    def create_fb_post(
        self,
        post_id: str,
        message: str,
        created_time: str,
        reach: int = 100,
        likes: int = 10,
        comments: int = 3,
        shares: int = 2,
        permalink: str = "",
    ):
        return {
            "id": post_id,
            "message": message,
            "created_time": created_time,
            "reach": reach,
            "likes": {"summary": {"total_count": likes}},
            "comments": {"summary": {"total_count": comments}},
            "shares": {"count": shares},
            "permalink_url": permalink or f"https://fb.com/{post_id}",
        }

    def test_run_review_matched(self, reviewer, store, fb_client):
        """Should match FB posts to calendar items and return matched entries."""
        fb_client.get_page_posts.return_value = [
            self.create_fb_post(
                post_id="post_001",
                message="Hôm nay mình review sản phẩm mới các bạn nhé",
                created_time="2026-06-01T10:00:00+0000",
                reach=500,
                likes=40,
                comments=10,
                shares=5,
            ),
            self.create_fb_post(
                post_id="post_002",
                message="Tips chăm sóc da buổi sáng",
                created_time="2026-06-02T09:00:00+0000",
                reach=300,
                likes=20,
                comments=5,
                shares=3,
            ),
        ]

        payload = reviewer.run_review(store=store, days=30, record=False)

        assert payload["fetched"] == 2
        assert payload["matched"] == 2
        assert payload["unmatched"] == 0
        assert payload["recorded"] == 0
        assert len(payload["matched_posts"]) == 2
        # First match: cal_001 (review sản phẩm mới)
        assert payload["matched_posts"][0]["calendar_id"] == "cal_001"
        assert payload["matched_posts"][0]["topic"] == "review sản phẩm mới"
        assert payload["matched_posts"][0]["reach"] == 500
        assert payload["matched_posts"][0]["engagements"] == 55  # 40 + 10 + 5

        # record_post_metrics should NOT be called
        store.record_post_metrics.assert_not_called()

    def test_run_review_unmatched(self, reviewer, store, fb_client):
        """Should report unmatched FB posts."""
        fb_client.get_page_posts.return_value = [
            self.create_fb_post(
                post_id="post_003",
                message="Nội dung không có trong calendar",
                created_time="2026-06-05T10:00:00+0000",
                reach=200,
                likes=15,
                comments=5,
                shares=2,
            ),
        ]

        payload = reviewer.run_review(store=store, days=30, record=False)

        assert payload["fetched"] == 1
        assert payload["matched"] == 0
        assert payload["unmatched"] == 1
        assert len(payload["unmatched_posts"]) == 1
        assert "Nội dung không có" in payload["unmatched_posts"][0]["message_preview"]

    def test_run_review_record_true(self, reviewer, store, fb_client):
        """Should call record_post_metrics when record=True."""
        fb_client.get_page_posts.return_value = [
            self.create_fb_post(
                post_id="post_001",
                message="Hôm nay mình review sản phẩm mới",
                created_time="2026-06-01T10:00:00+0000",
                reach=500,
                likes=40,
                comments=10,
                shares=5,
            ),
        ]

        payload = reviewer.run_review(store=store, days=30, record=True)

        assert payload["recorded"] == 1
        store.record_post_metrics.assert_called_once_with(
            calendar_id="cal_001",
            reach=500,
            engagements=55,
            leads=0,
            recorded_at=payload["review_period"]["end"],
        )

    def test_run_review_no_recent_posts(self, reviewer, store, fb_client):
        """Should return empty if no posts in the review period."""
        fb_client.get_page_posts.return_value = [
            self.create_fb_post(
                post_id="post_old",
                message="Bài cũ",
                created_time="2025-01-01T10:00:00+0000",
            ),
        ]

        payload = reviewer.run_review(store=store, days=7, record=True)

        assert payload["fetched"] == 0
        assert payload["matched"] == 0
        assert payload["unmatched"] == 0
        assert payload["recorded"] == 0
        store.record_post_metrics.assert_not_called()

    def test_run_review_no_calendar_filter_by_status(self, reviewer, fb_client):
        """Should only match against published calendar items."""
        store = MagicMock()
        # Only return unpublished items
        store.list_calendar_items.return_value = []
        store.read_post_metrics.return_value = []

        fb_client.get_page_posts.return_value = [
            self.create_fb_post(
                post_id="post_001",
                message="review sản phẩm mới",
                created_time="2026-06-01T10:00:00+0000",
            ),
        ]

        payload = reviewer.run_review(store=store, days=30, record=True)

        assert payload["fetched"] == 1
        assert payload["matched"] == 0
        assert payload["unmatched"] == 1
        # Verify status filter was used
        store.list_calendar_items.assert_called_once_with(status="published")

    def test_run_review_error_no_fb_token(self, store):
        """Should raise RuntimeError if FB token is missing."""
        settings = MagicMock(spec=Settings)
        settings.fb_page_id = ""
        settings.fb_page_token = ""

        with pytest.raises(RuntimeError, match="FB_PAGE_ID"):
            AnalyticsReviewer(settings)

    def test_match_by_date_proximity(self, reviewer, store, fb_client):
        """Should match by ±1 day proximity when exact date has no items."""
        # Only June 2 calendar item exists; FB post is on June 1 → ±1 day match
        store.list_calendar_items.return_value = [
            {
                "calendar_id": "cal_002",
                "date": "2026-06-02",
                "topic": "tips chăm sóc da",
                "pillar": "educational",
                "objective": "awareness",
                "status": "published",
                "published_at": "2026-06-02T08:00:00",
                "hook": "chăm sóc da",
            },
        ]

        fb_client.get_page_posts.return_value = [
            self.create_fb_post(
                post_id="post_001",
                message="chăm sóc da hàng ngày",
                created_time="2026-06-01T10:00:00+0000",
                reach=400,
                likes=30,
                comments=8,
                shares=4,
            ),
        ]

        payload = reviewer.run_review(store=store, days=30, record=False)

        # June 1 post should match June 2 calendar item via proximity + topic
        assert payload["matched"] == 1
        assert payload["matched_posts"][0]["calendar_id"] == "cal_002"

    def test_no_store_call_on_preview(self, reviewer, store, fb_client):
        """Verifies metrics aren't written when record=False."""
        fb_client.get_page_posts.return_value = [
            self.create_fb_post(
                post_id="post_001",
                message="review sản phẩm mới",
                created_time="2026-06-01T10:00:00+0000",
                reach=100,
                likes=5,
                comments=2,
                shares=1,
            ),
        ]

        payload = reviewer.run_review(store=store, days=30, record=False)
        assert payload["recorded"] == 0
        store.record_post_metrics.assert_not_called()
        # Should include summary from analytics service
        assert "report" in payload
        assert "summary" in payload["report"]
