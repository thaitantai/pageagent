from fanpage_agent.models import ResearchEvidence, SourceDocument
from fanpage_agent.tools.research.product_topic_discovery import ProductAwareTopicDiscovery
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.tools.research.research_packet import research_handoff_policy


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


def _affiliate_context():
    return {
        "industry_focus": "đồ gia dụng thông minh",
        "community_value": "giúp người mua chọn đúng theo nhu cầu thật",
        "customer_pain_points": ["phòng ngủ nhiều bụi nhưng ngân sách hạn chế"],
        "affiliate_offers": [{
            "name": "Máy lọc không khí phổ thông",
            "category": "máy lọc không khí",
            "benefits": ["phù hợp phòng nhỏ"],
            "competitors": ["Mẫu A", "Mẫu B"],
            "do_not_claim": ["chữa bệnh hô hấp"],
        }],
        "content_policy": {
            "affiliate_disclosure_required": True,
            "require_pros_cons": True,
        },
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


def test_affiliate_topic_discovery_prefers_community_buying_angles():
    discovery = ProductAwareTopicDiscovery()

    candidates = discovery.discover(_affiliate_context(), max_topics=4)

    assert len(candidates) == 4
    assert candidates[0].angle == "buying_guide"
    assert "máy lọc không khí" in candidates[0].topic
    assert "community_first" in candidates[0].reason_codes
    assert "affiliate_disclosure_required" in candidates[0].reason_codes
    assert "claim_guard_required" in candidates[0].reason_codes
    assert any(candidate.angle == "comparison" for candidate in candidates)


def test_research_service_can_prioritize_product_aware_topics():
    service = ResearchTool()

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
    service = ResearchTool()
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


def test_affiliate_topics_without_evidence_are_blocked_from_recommendation():
    service = ResearchTool()

    brief = service.build_brief(
        EmptyStore(),
        source_documents=[],
        page_context=_affiliate_context(),
        discover_product_topics=True,
        max_product_topics=2,
        fetch_external_trends=False,
    )

    assert any("Affiliate topic" in warning for warning in brief.quality_warnings)
    assert brief.topic_scores
    assert brief.topic_scores[0].risk_level == "high"
    assert brief.topic_scores[0].total_score <= 0.49
    assert "chưa đủ evidence" in brief.topic_scores[0].rationale


def test_affiliate_topics_can_score_when_source_evidence_matches():
    service = ResearchTool()

    brief = service.build_brief(
        EmptyStore(),
        source_documents=[SourceDocument(
            source_id="air-filter-guide",
            source_name="Consumer Guide",
            url="https://example.com/air-filter-guide",
            title="Máy lọc không khí phổ thông cho phòng ngủ nhiều bụi",
            content="Tiêu chí chọn máy lọc không khí phổ thông cho phòng ngủ nhiều bụi.",
            trust_score=0.9,
            freshness_score=0.8,
        )],
        page_context=_affiliate_context(),
        discover_product_topics=True,
        max_product_topics=1,
        fetch_external_trends=False,
    )

    assert not any("chưa có evidence đủ mạnh" in warning for warning in brief.quality_warnings)
    assert brief.topic_scores[0].source_confidence >= 0.45
    assert brief.topic_scores[0].risk_level != "high"


def test_handoff_policy_blocks_affiliate_topics_without_evidence():
    service = ResearchTool()

    brief = service.build_brief(
        EmptyStore(),
        source_documents=[],
        page_context=_affiliate_context(),
        discover_product_topics=True,
        max_product_topics=2,
        fetch_external_trends=False,
    )

    status, reasons, policy = research_handoff_policy(brief)

    assert status == "blocked"
    assert any("high-risk" in reason for reason in reasons)
    assert policy["allow_writer_claims"] is False
    assert policy["allow_affiliate_recommendations"] is False
    assert policy["max_safe_use"] == "draft_questions_only"
