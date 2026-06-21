from fanpage_agent.research_handoff import normalize_research_handoff


def test_normalize_ready_packet_exposes_shared_fields() -> None:
    packet = {
        "packet_id": "rpkt-1",
        "status": "ready",
        "handoff_policy": {"max_safe_use": "public_draft"},
        "page_context": {"page_id": "main", "topic_focus": "soi da"},
        "brief": {
            "confidence_score": 0.82,
            "topic_scores": [{"topic": "Khi nào nên soi da?", "total_score": 0.91}],
            "evidence": [
                {
                    "claim": "Nên soi da khi routine không còn hiệu quả",
                    "source": "FAQ",
                    "url": "https://example.com/a",
                    "confidence": 0.8,
                }
            ],
        },
    }

    result = normalize_research_handoff(packet)

    assert result["packet_id"] == "rpkt-1"
    assert result["status"] == "ready"
    assert result["safe_use"] == "public_draft"
    assert result["page_context"]["page_id"] == "main"
    assert result["priority_topics"][0]["topic"] == "Khi nào nên soi da?"
    assert result["evidence_refs"][0]["source"] == "FAQ"


def test_normalize_blocked_legacy_brief_stays_conservative() -> None:
    brief = {
        "status": "blocked",
        "handoff_policy": {"max_safe_use": "draft_questions_only"},
        "gate_reasons": ["chưa có source_documents đã kiểm chứng"],
        "topic_scores": [{"topic": "Review serum đang hot", "total_score": 0.7}],
        "evidence": [{"claim": "A", "source": "B"}],
    }

    result = normalize_research_handoff(brief)

    assert result["status"] == "blocked"
    assert result["safe_use"] == "draft_questions_only"
    assert result["priority_topics"] == []
    assert result["blocked_topics"][0]["topic"] == "Review serum đang hot"
    assert result["gate_reasons"] == ["chưa có source_documents đã kiểm chứng"]
