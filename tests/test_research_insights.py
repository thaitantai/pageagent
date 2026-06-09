import unittest

from fanpage_agent.models import SourceDocument
from fanpage_agent.tools.research.research_insights import EvidenceExtractor, ResearchQualityGate


class ResearchInsightsTest(unittest.TestCase):
    def test_extracts_focused_claims_from_source_documents(self) -> None:
        document = SourceDocument(
            source_id="derm-01",
            source_name="Derm Clinic Blog",
            url="https://example.com/skin-analysis",
            title="Skin analysis",
            content=(
                "Generic intro. "
                "Soi da định kỳ giúp phát hiện sớm tình trạng mất nước và tăng sắc tố trước khi chọn treatment. "
                "Một câu rất ngắn. "
                "Khách hàng treatment cần được tư vấn phục hồi hàng rào bảo vệ da sau liệu trình."
            ),
            trust_score=0.95,
            freshness_score=0.8,
        )

        evidence = EvidenceExtractor().extract(
            source_documents=[document],
            campaign_focus=["soi da", "treatment"],
        )

        source_claims = [item for item in evidence if item.evidence_type == "source_claim"]
        self.assertGreaterEqual(len(source_claims), 1)
        self.assertEqual(source_claims[0].source_id, "derm-01")
        self.assertIn("Soi da", source_claims[0].claim)
        self.assertGreater(source_claims[0].confidence, 0.7)

    def test_quality_gate_warns_on_single_source_and_failed_fetch(self) -> None:
        document = SourceDocument(
            source_id="derm-01",
            source_name="Derm Clinic Blog",
            url="https://example.com/skin-analysis",
            content="Soi da định kỳ giúp chọn treatment phù hợp cho khách hàng.",
            trust_score=0.9,
            metadata={"fetch_status": "error"},
        )
        evidence = EvidenceExtractor().extract(source_documents=[document], campaign_focus=["soi da"])

        report = ResearchQualityGate().evaluate(evidence=evidence, source_documents=[document])

        self.assertLess(report.confidence_score, evidence[0].confidence)
        self.assertTrue(any("nguồn độc lập" in item for item in report.warnings))
        self.assertTrue(any("fetch thất bại" in item for item in report.warnings))

    def test_marks_claims_corroborated_by_independent_sources(self) -> None:
        documents = [
            SourceDocument(
                source_id="derm-01",
                source_name="Derm Clinic Blog",
                url="https://example.com/skin-analysis",
                content="Soi da định kỳ giúp phát hiện mất nước trước khi chọn treatment phục hồi.",
                trust_score=0.9,
                freshness_score=0.8,
            ),
            SourceDocument(
                source_id="journal-01",
                source_name="Derm Journal",
                url="https://journal.example/skin-analysis",
                content="Quy trình soi da giúp bác sĩ nhận diện mất nước và chọn treatment phù hợp hơn.",
                trust_score=0.95,
                freshness_score=0.7,
            ),
        ]

        evidence = EvidenceExtractor().extract(
            source_documents=documents,
            campaign_focus=["soi da", "treatment"],
        )

        source_claims = [item for item in evidence if item.evidence_type == "source_claim"]
        self.assertTrue(any(item.support_count >= 2 for item in source_claims))
        self.assertTrue(any("Derm Journal" in item.corroborating_sources for item in source_claims))

        report = ResearchQualityGate().evaluate(evidence=evidence, source_documents=documents)

        self.assertFalse(any("corroborate" in item for item in report.warnings))


if __name__ == "__main__":
    unittest.main()
