"""Tests cho OfferDiscoveryService — phát hiện offer từ web crawl."""

from __future__ import annotations

import pytest

from fanpage_agent.models import SourceDocument, TrendItem
from fanpage_agent.services.offer_discovery import OfferDiscoveryService


@pytest.fixture
def discovery() -> OfferDiscoveryService:
    return OfferDiscoveryService()


@pytest.fixture
def skincare_review_doc() -> SourceDocument:
    return SourceDocument(
        source_name="healthline.com",
        source_id="hl-123",
        source_type="rss",
        url="https://healthline.com/skincare/review-best-sunscreen-2026",
        title="Review kem chống nắng tốt nhất 2026: trải nghiệm thực tế",
        content=(
            "Chúng tôi đã test 15 loại kem chống nắng trong 30 ngày. "
            "So sánh SPF, kết cấu và giá cả. "
            "Sản phẩm nổi bật: serum vitamin C có SPF, kem chống nắng vật lý, "
            "kem dưỡng ẩm có chỉ số chống nắng. "
            "Review chi tiết sản phẩm tốt nhất cho từng loại da."
        ),
        trust_score=0.8,
        freshness_score=0.9,
        metadata={},
    )


@pytest.fixture
def trending_article() -> TrendItem:
    return TrendItem(
        title="Top 10 retinol cho người mới bắt đầu: review và so sánh giá",
        url="https://example.com/best-retinol-beginners",
        source="web_search",
    )


class TestOfferDiscoveryService:
    def test_discover_from_review_doc(self, discovery: OfferDiscoveryService, skincare_review_doc: SourceDocument) -> None:
        """Phát hiện sản phẩm từ bài review."""
        offers = discovery.discover(source_documents=[skincare_review_doc])
        assert len(offers) >= 1
        product_names = {o.product_name.lower() for o in offers}
        assert "serum vitamin c" in product_names or "kem chống nắng" in product_names

    def test_discover_from_trending_article(self, discovery: OfferDiscoveryService, trending_article: TrendItem) -> None:
        """Phát hiện sản phẩm từ external trend."""
        offers = discovery.discover(external_trends=[trending_article])
        assert len(offers) >= 1
        assert any("retinol" in o.product_name.lower() for o in offers)

    def test_discover_no_matches_returns_empty(self, discovery: OfferDiscoveryService) -> None:
        """Text không liên quan → không phát hiện offer."""
        doc = SourceDocument(
            source_name="news.com",
            source_id="n-1",
            source_type="rss",
            url="https://news.com/politics",
            title="Tin tức thời sự",
            content="Hôm nay trời đẹp, không có sản phẩm nào được nhắc đến.",
            trust_score=0.5,
            freshness_score=0.5,
            metadata={},
        )
        offers = discovery.discover(source_documents=[doc])
        assert len(offers) == 0

    def test_discover_from_both_sources(self, discovery: OfferDiscoveryService, skincare_review_doc: SourceDocument, trending_article: TrendItem) -> None:
        """Gom từ cả source documents + external trends."""
        offers = discovery.discover(
            source_documents=[skincare_review_doc],
            external_trends=[trending_article],
        )
        assert len(offers) >= 2  # Ít nhất 1 từ doc + 1 từ trend

    def test_discover_dedup_same_product(self, discovery: OfferDiscoveryService) -> None:
        """Cùng sản phẩm từ nhiều nguồn → chỉ giữ 1 candidate."""
        doc1 = SourceDocument(
            source_name="healthline.com",
            source_id="hl-1",
            source_type="rss",
            url="https://healthline.com/skincare/sunscreen-review",
            title="Review kem chống nắng",
            content="Kem chống nắng tốt nhất cho da dầu mụn. So sánh các loại kem chống nắng.",
            trust_score=0.8,
            freshness_score=0.8,
            metadata={},
        )
        doc2 = SourceDocument(
            source_name="byrdie.com",
            source_id="by-1",
            source_type="rss",
            url="https://byrdie.com/best-sunscreen",
            title="Best sunscreen 2026 review",
            content="Top kem chống nắng năm 2026, đánh giá chi tiết từng sản phẩm.",
            trust_score=0.7,
            freshness_score=0.9,
            metadata={},
        )
        offers = discovery.discover(
            source_documents=[doc1, doc2],
            existing_offers=[],
        )
        # Dù 2 doc có cùng marker "kem chống nắng", merged chỉ giữ 1
        sunscreen_offers = [o for o in offers if "kem chống nắng" in o.product_name.lower()]
        assert len(sunscreen_offers) == 1

    def test_discover_respects_existing_offers(self, discovery: OfferDiscoveryService, skincare_review_doc: SourceDocument) -> None:
        """Offer đã có trong existing_offers → không thêm lại."""
        offers = discovery.discover(
            source_documents=[skincare_review_doc],
            existing_offers=["Kem chống nắng"],
        )
        # "Kem chống nắng" bị loại, nhưng "serum vitamin c" vẫn còn
        sunscreen_count = sum(1 for o in offers if "kem chống nắng" in o.product_name.lower())
        assert sunscreen_count == 0
        assert len(offers) >= 1

    def test_detect_angle_buying_guide(self, discovery: OfferDiscoveryService) -> None:
        assert discovery._detect_angle("top best kem chống nắng nên mua", 4) == "buying_guide"

    def test_detect_angle_comparison(self, discovery: OfferDiscoveryService) -> None:
        assert discovery._detect_angle("so sánh kem chống nắng vs kem dưỡng", 2) == "comparison"

    def test_detect_angle_education(self, discovery: OfferDiscoveryService) -> None:
        assert discovery._detect_angle("công dụng của retinol", 0) == "education"

    def test_scan_text_empty(self, discovery: OfferDiscoveryService) -> None:
        assert discovery._scan_text("", "", "", "") == []

    def test_scan_text_no_marker(self, discovery: OfferDiscoveryService) -> None:
        assert discovery._scan_text("thời tiết hôm nay đẹp", "", "", "") == []

    def test_merge_candidates_dedup(self, discovery: OfferDiscoveryService) -> None:
        from fanpage_agent.services.product_topic_discovery import ProductTopicCandidate
        c1 = ProductTopicCandidate(
            topic="A", angle="review", product_name="Kem chống nắng",
            customer_pain="da dầu", research_query="test",
            product_relevance=0.8, customer_value=0.7, reason_codes=["a"],
        )
        c2 = ProductTopicCandidate(
            topic="B", angle="review", product_name="Kem chống nắng",
            customer_pain="da dầu", research_query="test2",
            product_relevance=0.9, customer_value=0.75, reason_codes=["b"],
        )
        merged = discovery._merge_candidates([c1, c2])
        assert len(merged) == 1
        assert merged[0].product_relevance == 0.9  # Giữ score cao nhất

    def test_estimate_customer_value_review_context(self, discovery: OfferDiscoveryService) -> None:
        value = discovery._estimate_customer_value("review đánh giá kem chống nắng trải nghiệm", 3)
        assert value >= 0.7
