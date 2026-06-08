from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from fanpage_agent.models import ResearchEvidence
from fanpage_agent.tools.research.product_topic_discovery import ProductTopicCandidate

logger = logging.getLogger(__name__)

# Round threshold — after this many rounds, stop trying to find evidence
_MAX_EVALUATION_ROUNDS = 3

# Minimum confidence needed to consider an offer "ready"
_READY_CONFIDENCE = 0.5

# Boost confidence per corroborating source found across rounds
_CORROBORATION_BOOST = 0.08

# How many new queries to generate per round
_QUERIES_PER_ROUND = 3

# Max articles to fetch per round per offer
_MAX_ARTICLES_PER_ROUND = 5


@dataclass(frozen=True)
class EvaluationCriterion:
    """Một tiêu chí đánh giá với trọng số và giải thích."""

    name: str
    weight: float
    score: float  # 0.0 to 1.0
    rationale: str = ""


@dataclass(frozen=True)
class OfferEvaluationResult:
    """Kết quả đánh giá một offer qua một hoặc nhiều vòng tìm evidence."""

    offer_name: str
    total_score: float
    criteria: list[EvaluationCriterion]
    evidence_found: list[ResearchEvidence] = field(default_factory=list)
    rounds_used: int = 1
    remaining_queries: list[str] = field(default_factory=list)
    is_ready: bool = False
    suggestions: list[str] = field(default_factory=list)

    def as_topic_score_metadata(self) -> dict[str, Any]:
        """Serialize thành metadata để gắn vào ResearchTopicScore."""
        return {
            "offer_evaluation_total": round(self.total_score, 3),
            "offer_evaluation_rounds": self.rounds_used,
            "offer_ready": self.is_ready,
            "offer_evidence_count": len(self.evidence_found),
            "offer_suggestions": self.suggestions,
        }


class SearchClient(Protocol):
    """Protocol cho search client mà OfferEvaluator cần."""

    def search_trends(
        self,
        queries: list[str],
        max_articles: int = 10,
    ) -> list[Any]: ...


class OfferEvaluator:
    """Đánh giá offer candidates theo đa tiêu chí, tự động tìm evidence lặp nếu chưa đủ.

    Dùng TrendScraper (hoặc bất kỳ SearchClient nào) để tìm evidence mới khi
    offer chưa đạt confidence threshold. Có thể chạy tối đa _MAX_EVALUATION_ROUNDS
    vòng, mỗi vòng sinh thêm research query dựa trên kết quả vòng trước.
    """

    def __init__(
        self,
        search_client: SearchClient | None = None,
        max_rounds: int = _MAX_EVALUATION_ROUNDS,
        ready_confidence: float = _READY_CONFIDENCE,
    ):
        self._search_client = search_client
        self._max_rounds = max_rounds
        self._ready_confidence = ready_confidence

    def evaluate(
        self,
        topic: ProductTopicCandidate,
        existing_evidence: list[ResearchEvidence] | None = None,
        niche_name: str | None = None,
    ) -> OfferEvaluationResult:
        """Evaluate một offer và tìm evidence lặp nếu chưa đủ.

        Parameters
        ----------
        topic : ProductTopicCandidate
            Offer candidate cần đánh giá.
        existing_evidence : list[ResearchEvidence] | None
            Evidence đã có từ research brief hiện tại.
        niche_name : str | None
            Tên niche page (ví dụ \"chăm sóc da\") để sinh query tốt hơn.

        Returns
        -------
        OfferEvaluationResult
            Kết quả đánh giá sau 1 hoặc nhiều vòng search.
        """
        all_evidence = list(existing_evidence or [])
        queries_to_try = self._initial_queries(topic, niche_name)
        rounds_used = 0

        for round_index in range(self._max_rounds):
            if not queries_to_try:
                break

            rounds_used = round_index + 1

            # Kiểm tra score với evidence hiện tại
            current_score = self._compute_score(topic, all_evidence)
            if current_score >= self._ready_confidence:
                return self._finalize(
                    topic=topic,
                    evidence=all_evidence,
                    rounds=rounds_used,
                    score=current_score,
                    score_breakdown=self._compute_all_criteria(topic, all_evidence),
                )

            # Nếu chưa đủ → search thêm
            if self._search_client is None or round_index >= self._max_rounds - 1:
                break

            fresh = self._search_round(queries_to_try, topic)
            if not fresh:
                break

            # Dedup với evidence cũ
            seen_claims = {e.claim for e in all_evidence}
            new_items = [e for e in fresh if e.claim not in seen_claims]
            if not new_items:
                break

            all_evidence.extend(new_items)
            seen_claims.update(e.claim for e in new_items)

            # Sinh queries mới dựa trên nội dung vừa tìm được
            if round_index < self._max_rounds - 2:
                queries_to_try = self._next_queries(topic, new_items, niche_name)
            else:
                queries_to_try = []

        final_score = self._compute_score(topic, all_evidence)
        final_criteria = self._compute_all_criteria(topic, all_evidence)
        return self._finalize(
            topic=topic,
            evidence=all_evidence,
            rounds=rounds_used,
            score=final_score,
            score_breakdown=final_criteria,
        )

    def _initial_queries(
        self,
        topic: ProductTopicCandidate,
        niche_name: str | None,
    ) -> list[str]:
        base = topic.research_query
        queries = [base]
        if topic.customer_pain:
            queries.append(f"{topic.product_name} {topic.customer_pain}")
        if niche_name:
            queries.append(f"{topic.product_name} {niche_name}")
        if topic.angle in {"comparison", "buying_guide"}:
            queries.append(f"{topic.product_name} review 2026")
        return list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:_QUERIES_PER_ROUND]

    def _search_round(
        self,
        queries: list[str],
        topic: ProductTopicCandidate,
    ) -> list[ResearchEvidence]:
        """Search + chuyển kết quả thành ResearchEvidence."""
        if self._search_client is None:
            return []
        try:
            results = self._search_client.search_trends(
                queries=queries,
                max_articles=_MAX_ARTICLES_PER_ROUND,
            )
        except Exception as exc:
            logger.warning("OfferEvaluator search round failed for %s: %s", topic.product_name, exc)
            return []

        evidence: list[ResearchEvidence] = []
        for item in results:
            title = getattr(item, "title", "") or ""
            url = getattr(item, "url", "") or ""
            if not title:
                continue
            evidence.append(
                ResearchEvidence(
                    claim=title,
                    source=f"offer_search:{topic.product_name}",
                    url=url,
                    evidence_type="offer_search",
                    source_type="web",
                    confidence=0.5,
                )
            )
        return evidence

    def _next_queries(
        self,
        topic: ProductTopicCandidate,
        new_evidence: list[ResearchEvidence],
        niche_name: str | None,
    ) -> list[str]:
        """Sinh query mới dựa trên evidence vừa tìm được nếu còn round."""
        queries: list[str] = []
        for item in new_evidence:
            words = item.claim.split()
            if len(words) >= 4:
                queries.append(f"{topic.product_name} {' '.join(words[:4])} evidence")
        if niche_name:
            queries.append(f"{topic.product_name} {niche_name} nghiên cứu")
        queries.append(f"{topic.product_name} công dụng bằng chứng")
        return list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:_QUERIES_PER_ROUND]

    def _compute_score(
        self,
        topic: ProductTopicCandidate,
        evidence: list[ResearchEvidence],
    ) -> float:
        """Tổng điểm weighted average từ các criteria."""
        criteria = self._compute_all_criteria(topic, evidence)
        total_weight = sum(c.weight for c in criteria)
        if total_weight == 0:
            return 0.0
        return sum(c.score * c.weight for c in criteria) / total_weight

    def _compute_all_criteria(
        self,
        topic: ProductTopicCandidate,
        evidence: list[ResearchEvidence],
    ) -> list[EvaluationCriterion]:
        """Trả về toàn bộ criteria kèm score + rationale."""
        offer_evidence = [e for e in evidence if "offer_search" in e.source or e.evidence_type == "external_source"]
        all_evidence_with_url = [e for e in evidence if e.url]
        external_count = len(offer_evidence)
        url_count = len({e.url for e in all_evidence_with_url})

        # 1. Niche relevance — sản phẩm có phù hợp niche không?
        niche_relevance = EvaluationCriterion(
            name="niche_relevance",
            weight=0.25,
            score=min(1.0, topic.product_relevance + 0.1),
            rationale=f"product_relevance={topic.product_relevance:.2f} + base 0.1",
        )

        # 2. Evidence density — có bao nhiêu nguồn tìm được
        density_score = min(1.0, external_count / 6)
        evidence_density = EvaluationCriterion(
            name="evidence_density",
            weight=0.25,
            score=density_score,
            rationale=f"{external_count} external sources found",
        )

        # 3. Corroboration — có nhiều nguồn khác nhau không?
        source_names = {e.source for e in offer_evidence if e.source}
        corrob_score = min(1.0, len(source_names) / 4) if source_names else 0.0
        corroboration = EvaluationCriterion(
            name="corroboration",
            weight=0.20,
            score=corrob_score,
            rationale=f"{len(source_names)} unique sources: {', '.join(sorted(source_names)[:3])}",
        )

        # 4. URL vérifiabilité — có URL để kiểm chứng không?
        url_density = min(1.0, url_count / 5)
        verifiability = EvaluationCriterion(
            name="verifiability",
            weight=0.15,
            score=url_density,
            rationale=f"{url_count} unique URLs found",
        )

        # 5. Customer value — pain point có rõ không?
        pain_score = 0.7 if topic.customer_pain else 0.3
        customer_value = EvaluationCriterion(
            name="customer_value",
            weight=0.15,
            score=min(1.0, topic.customer_value + pain_score * 0.1),
            rationale=f"customer_pain={bool(topic.customer_pain)}, customer_value={topic.customer_value:.2f}",
        )

        return [niche_relevance, evidence_density, corroboration, verifiability, customer_value]

    @staticmethod
    def _finalize(
        topic: ProductTopicCandidate,
        evidence: list[ResearchEvidence],
        rounds: int,
        score: float,
        score_breakdown: list[EvaluationCriterion],
    ) -> OfferEvaluationResult:
        """Đóng gói kết quả cuối cùng."""
        is_ready = score >= _READY_CONFIDENCE
        suggestions: list[str] = []
        if not is_ready:
            if score < 0.3:
                suggestions.append("Cần tìm thêm nguồn tham khảo độc lập về sản phẩm này trước khi đưa vào nội dung.")
            elif score < 0.4:
                suggestions.append("Đã có một số thông tin, cần kiểm chứng thêm từ nguồn y tế/uy tín.")
            else:
                suggestions.append("Evidence gần đủ, nên tham khảo thêm 1-2 nguồn nữa để tăng độ tin cậy.")
        if topic.risk_level == "medium":
            suggestions.append("Sản phẩm có claim cần guardrail — không đưa ra khuyến nghị tuyệt đối.")
        if topic.is_affiliate_offer and is_ready:
            suggestions.append("Đã đủ evidence để đưa vào brief — vẫn cần affiliate disclosure.")

        offer_evidence = [e for e in evidence if e.source and "offer_search" in e.source]

        return OfferEvaluationResult(
            offer_name=topic.product_name,
            total_score=round(score, 3),
            criteria=score_breakdown,
            evidence_found=offer_evidence,
            rounds_used=rounds,
            is_ready=is_ready,
            suggestions=suggestions,
        )
