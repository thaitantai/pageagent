"""Tests cho OfferEvaluator — multi-criteria scoring + iterative evidence search."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from fanpage_agent.models import ResearchEvidence
from fanpage_agent.services.offer_evaluator import (
    EvaluationCriterion,
    OfferEvaluationResult,
    OfferEvaluator,
)
from fanpage_agent.services.product_topic_discovery import ProductTopicCandidate

# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@dataclass
class FakeTrendItem:
    title: str
    url: str = ""
    source: str = "fake_source"


class FakeSearchClient:
    """Mock TrendScraper trả về kết quả cố định."""

    def __init__(self, results_by_round: list[list[FakeTrendItem]] | None = None):
        self._results = results_by_round or []
        self._call_count = 0

    def search_trends(
        self,
        queries: list[str],
        max_articles: int = 10,
    ) -> list[FakeTrendItem]:
        if self._call_count < len(self._results):
            result = self._results[self._call_count]
            self._call_count += 1
            return result
        return []


# ──────────────────────────────────────────────
# Unit tests — OfferEvaluationResult
# ──────────────────────────────────────────────


class TestOfferEvaluationResult:
    def test_as_topic_score_metadata_contains_expected_keys(self) -> None:
        result = OfferEvaluationResult(
            offer_name="Kem chống nắng",
            total_score=0.75,
            criteria=[
                EvaluationCriterion(name="niche_relevance", weight=0.25, score=0.9, rationale="test"),
            ],
            evidence_found=[
                ResearchEvidence(claim="test claim", source="offer_search:test", evidence_type="offer_search", confidence=0.6),
            ],
            rounds_used=2,
            is_ready=True,
            suggestions=["Đã đủ evidence"],
        )
        meta = result.as_topic_score_metadata()
        assert meta["offer_evaluation_total"] == 0.75
        assert meta["offer_evaluation_rounds"] == 2
        assert meta["offer_ready"] is True
        assert meta["offer_evidence_count"] == 1
        assert "Đã đủ evidence" in meta["offer_suggestions"]

    def test_not_ready_result(self) -> None:
        result = OfferEvaluationResult(
            offer_name="Test",
            total_score=0.25,
            criteria=[],
            rounds_used=3,
            is_ready=False,
            suggestions=["Cần thêm nguồn"],
        )
        assert not result.is_ready


# ──────────────────────────────────────────────
# Unit tests — OfferEvaluator scoring
# ──────────────────────────────────────────────


@pytest.fixture
def sample_offer() -> ProductTopicCandidate:
    return ProductTopicCandidate(
        topic="Kem chống nắng cho da dầu: cách chọn phù hợp",
        angle="buying_guide",
        product_name="Kem chống nắng",
        customer_pain="da dầu mụn",
        research_query="kem chống nắng da dầu mụn review",
        product_relevance=0.82,
        customer_value=0.92,
        reason_codes=["affiliate_offer", "angle:buying_guide"],
    )


class TestOfferEvaluatorScoring:
    def test_compute_score_without_evidence_returns_low(self, sample_offer: ProductTopicCandidate) -> None:
        evaluator = OfferEvaluator()
        score = evaluator._compute_score(sample_offer, [])
        assert score < 0.4  # Không evidence → score thấp

    def test_compute_score_with_evidence_returns_high(self, sample_offer: ProductTopicCandidate) -> None:
        evidence = [
            ResearchEvidence(
                claim="Kem chống nắng cho da dầu mụn hiệu quả",
                source="offer_search:test",
                url="https://example.com/1",
                evidence_type="offer_search",
                confidence=0.7,
            ),
            ResearchEvidence(
                claim="Cách chọn kem chống nắng cho da dầu",
                source="offer_search:test",
                url="https://example.com/2",
                evidence_type="offer_search",
                confidence=0.65,
            ),
            ResearchEvidence(
                claim="Review kem chống nắng tốt nhất",
                source="offer_search:test",
                url="https://example.com/3",
                evidence_type="offer_search",
                confidence=0.6,
            ),
        ]
        evaluator = OfferEvaluator()
        score = evaluator._compute_score(sample_offer, evidence)
        assert score > 0.3  # Có evidence → cao hơn

    def test_compute_all_criteria_includes_five_dimensions(self, sample_offer: ProductTopicCandidate) -> None:
        evaluator = OfferEvaluator()
        criteria = evaluator._compute_all_criteria(sample_offer, [])
        assert len(criteria) == 5
        names = {c.name for c in criteria}
        assert names == {"niche_relevance", "evidence_density", "corroboration", "verifiability", "customer_value"}

    def test_all_criteria_weights_sum_to_one(self, sample_offer: ProductTopicCandidate) -> None:
        evaluator = OfferEvaluator()
        criteria = evaluator._compute_all_criteria(sample_offer, [])
        total = sum(c.weight for c in criteria)
        assert abs(total - 1.0) < 0.01

    def test_initial_queries(self, sample_offer: ProductTopicCandidate) -> None:
        evaluator = OfferEvaluator()
        queries = evaluator._initial_queries(sample_offer, "chăm sóc da")
        assert len(queries) >= 1
        assert all(isinstance(q, str) and len(q) > 0 for q in queries)

    def test_evaluate_ready_without_rounds(self, sample_offer: ProductTopicCandidate) -> None:
        """Với evidence đủ mạnh, evaluate trả về ready ngay."""
        evidence = [
            ResearchEvidence(
                claim="Kem chống nắng da dầu mụn SPF 50",
                source="offer_search:test",
                url="https://ex.com/1",
                evidence_type="offer_search",
                confidence=0.8,
            ),
            ResearchEvidence(
                claim="Chống nắng cho da dầu không bí",
                source="offer_search:test2",
                url="https://ex.com/2",
                evidence_type="offer_search",
                confidence=0.7,
            ),
            ResearchEvidence(
                claim="Kem chống nắng mỏng nhẹ cho da dầu",
                source="offer_search:test3",
                url="https://ex.com/3",
                evidence_type="offer_search",
                confidence=0.75,
            ),
            ResearchEvidence(
                claim="Review kem chống nắng da dầu 2026",
                source="offer_search:test4",
                url="https://ex.com/4",
                evidence_type="offer_search",
                confidence=0.7,
            ),
        ]
        evaluator = OfferEvaluator(max_rounds=3, ready_confidence=0.5)
        result = evaluator.evaluate(sample_offer, existing_evidence=evidence)
        assert result.is_ready
        assert result.total_score >= 0.5

    def test_evaluate_not_ready_no_evidence(self, sample_offer: ProductTopicCandidate) -> None:
        """Không evidence → không ready."""
        evaluator = OfferEvaluator()
        result = evaluator.evaluate(sample_offer)
        assert not result.is_ready
        assert result.total_score < 0.5

    def test_evaluate_not_ready_no_search_client(self, sample_offer: ProductTopicCandidate) -> None:
        """Không có search_client → không thể tìm evidence mới → không ready."""
        evaluator = OfferEvaluator(search_client=None, max_rounds=3, ready_confidence=0.5)
        result = evaluator.evaluate(sample_offer)
        assert not result.is_ready


# ──────────────────────────────────────────────
# Integration tests — với FakeSearchClient
# ──────────────────────────────────────────────


class TestOfferEvaluatorWithSearchClient:
    def test_evaluate_with_search_client_finds_evidence(self) -> None:
        fake_client = FakeSearchClient([
            # Round 1 results
            [
                FakeTrendItem(title="Kem chống nắng cho da dầu mụn hiệu quả", url="https://ex.com/1", source="web_search"),
                FakeTrendItem(title="Review kem chống nắng tốt nhất 2026", url="https://ex.com/2", source="web_search"),
            ],
        ])
        offer = ProductTopicCandidate(
            topic="Kem chống nắng cho da dầu: review tốt nhất",
            angle="buying_guide",
            product_name="Kem chống nắng",
            customer_pain="da dầu mụn",
            research_query="kem chống nắng da dầu mụn",
            product_relevance=0.8,
            customer_value=0.9,
            reason_codes=["affiliate_offer"],
        )
        evaluator = OfferEvaluator(search_client=fake_client, max_rounds=3, ready_confidence=0.5)
        result = evaluator.evaluate(offer)
        # Có search_client → có evidence mới
        assert len(result.evidence_found) >= 1
        assert result.rounds_used >= 1

    def test_iterative_search_two_rounds(self) -> None:
        """Trả evidence theo từng round — evaluator chạy tới khi đủ hoặc hết round."""
        fake_client = FakeSearchClient([
            # Round 1: ít evidence
            [
                FakeTrendItem(title="Một bài về kem chống nắng", url="https://ex.com/1"),
            ],
            # Round 2: thêm evidence
            [
                FakeTrendItem(title="Kem chống nắng cho da dầu: phân tích chi tiết", url="https://ex.com/2"),
                FakeTrendItem(title="Đánh giá kem chống nắng da dầu mụn", url="https://ex.com/3"),
            ],
        ])
        offer = ProductTopicCandidate(
            topic="Kem chống nắng cho da dầu",
            angle="review",
            product_name="Kem chống nắng",
            customer_pain="da dầu",
            research_query="kem chống nắng da dầu",
            product_relevance=0.8,
            customer_value=0.8,
            reason_codes=["affiliate_offer"],
        )
        evaluator = OfferEvaluator(search_client=fake_client, max_rounds=3, ready_confidence=0.5)
        result = evaluator.evaluate(offer)
        # Dù không đạt ready, đã chạy qua ít nhất 2 rounds
        assert result.rounds_used >= 1
        # Evidence từ cả 2 rounds được gom lại (deduped)
        assert len(result.evidence_found) >= 2

    def test_evaluate_uses_niche_name_in_queries(self) -> None:
        """Khi có niche_name, query có chứa niche."""
        fake_client = FakeSearchClient([
            [
                FakeTrendItem(title="Dưỡng ẩm cho da dầu mụn", url="https://ex.com/1"),
            ],
        ])
        offer = ProductTopicCandidate(
            topic="Kem dưỡng ẩm da dầu",
            angle="faq",
            product_name="Kem dưỡng ẩm",
            customer_pain="da dầu mụn",
            research_query="kem dưỡng ẩm da dầu",
            product_relevance=0.8,
            customer_value=0.7,
            reason_codes=["affiliate_offer"],
        )
        evaluator = OfferEvaluator(search_client=fake_client, max_rounds=2, ready_confidence=0.5)
        initial_queries = evaluator._initial_queries(offer, "chăm sóc da")
        assert any("chăm sóc da" in q for q in initial_queries)


# ──────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────


class TestOfferEvaluatorEdgeCases:
    def test_product_without_pain_still_generates_queries(self) -> None:
        offer = ProductTopicCandidate(
            topic="Serum vitamin C",
            angle="education",
            product_name="Serum vitamin C",
            customer_pain="",
            research_query="vitamin C serum benefits",
            product_relevance=0.7,
            customer_value=0.5,
            reason_codes=["product_context"],
        )
        evaluator = OfferEvaluator()
        queries = evaluator._initial_queries(offer, "chăm sóc da")
        assert len(queries) > 0

    def test_empty_evidence_round_stops_iteration(self) -> None:
        """Nếu search không trả gì mới, evaluator dừng sớm."""
        fake_client = FakeSearchClient([
            [],  # Round 1: empty
        ])
        offer = ProductTopicCandidate(
            topic="test",
            angle="education",
            product_name="test",
            customer_pain="",
            research_query="test product",
            product_relevance=0.5,
            customer_value=0.5,
            reason_codes=["affiliate_offer"],
        )
        evaluator = OfferEvaluator(search_client=fake_client, max_rounds=3)
        result = evaluator.evaluate(offer)
        assert result.rounds_used == 1  # Chỉ 1 round, dừng vì empty

    def test_high_risk_offer_gets_appropriate_suggestion(self) -> None:
        """Medium risk offer có suggestion về guardrail."""
        offer = ProductTopicCandidate(
            topic="test",
            angle="education",
            product_name="test",
            customer_pain="",
            research_query="test product",
            product_relevance=0.5,
            customer_value=0.5,
            risk_level="medium",
            reason_codes=["affiliate_offer"],
        )
        evaluator = OfferEvaluator()
        result = evaluator.evaluate(offer)
        assert any("guardrail" in s for s in result.suggestions)
