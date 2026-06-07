from fanpage_agent.models import ResearchEvidence
from fanpage_agent.services.product_topic_discovery import ProductAwareTopicDiscovery
from fanpage_agent.services.research import ResearchService


class EmptyStore:
    def read_post_history(self, limit=90):
        return []

    def read_post_metrics(self):
        return []


def _product_context():
    return {
        "products_services": [{
            "name": "Serum phục hồi da",
            "benefits": ["giảm kích ứng"],
            "do_not_claim": ["trị khỏi viêm da"],
        }],
        "customer_pain_points": ["da nhạy cảm sau treatment"],
    }


def test_product_topic_discovery_generates_guarded_candidates():
    discovery = ProductAwareTopicDiscovery()

    candidates = discovery.discover(_product_context(), max_topics=2)

    assert len(candidates) == 2
    assert candidates[0].product_name == "Serum phục hồi da"
    assert candidates[0].customer_pain == "da nhạy cảm sau treatment"
    assert candidates[0].risk_level == "medium"
    assert "claim_guard_required" in candidates[0].reason_codes
    assert "Serum phục hồi da" in candidates[0].research_query


def test_research_service_can_prioritize_product_aware_topics():
    service = ResearchService()

    brief = service.build_brief(
        EmptyStore(),
        source_documents=[],
        page_context=_product_context(),
        discover_product_topics=True,
        max_product_topics=3,
        fetch_external_trends=False,
    )

    assert brief.next_angles
    assert brief.topic_scores
    top_score = brief.topic_scores[0]
    assert "Serum phục hồi da" in top_score.topic
    assert top_score.product_relevance > 0
    assert top_score.customer_value > 0
    assert top_score.risk_level in {"low", "medium"}
    assert any("sản phẩm/vấn đề khách hàng" in item for item in brief.recommendations)


def test_product_topic_scores_use_evidence_confidence_when_available():
    service = ResearchService()
    product_topics = service._topic_discovery.discover(_product_context(), max_topics=1)
    evidence = [ResearchEvidence(
        claim="Serum phục hồi da hỗ trợ da nhạy cảm sau treatment",
        source="internal",
        confidence=0.9,
    )]

    scored = service._score_topics(
        candidates=[product_topics[0].topic],
        campaign_focus=[],
        overused_topics=[],
        frequent_questions=[],
        evidence=evidence,
        product_topics=product_topics,
    )

    assert scored[0].source_confidence > 0
