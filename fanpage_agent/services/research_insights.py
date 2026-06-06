from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from fanpage_agent.models import ResearchEvidence, SourceDocument, TrendItem

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_WORD_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)


@dataclass(frozen=True)
class ResearchQualityReport:
    confidence_score: float
    warnings: list[str]


class EvidenceExtractor:
    """Turn raw source documents and internal signals into sourced evidence."""

    def extract(
        self,
        *,
        source_documents: list[SourceDocument] | None = None,
        external_trends: list[TrendItem] | None = None,
        top_performing_topics: list[str] | None = None,
        frequent_questions: list[str] | None = None,
        campaign_focus: list[str] | None = None,
    ) -> list[ResearchEvidence]:
        evidence: list[ResearchEvidence] = []
        focus_terms = self._focus_terms((campaign_focus or []) + (top_performing_topics or []))

        for document in (source_documents or [])[:10]:
            for claim in self._claims_from_document(document, focus_terms)[:2]:
                evidence.append(
                    ResearchEvidence(
                        claim=claim,
                        source=document.source_name,
                        url=document.url,
                        evidence_type="source_claim",
                        confidence=self._document_confidence(document, claim),
                        source_id=document.source_id,
                        source_type=document.source_type,
                    )
                )

        for item in (external_trends or [])[:10]:
            confidence = 0.75 if item.url else 0.55
            evidence.append(
                ResearchEvidence(
                    claim=item.title,
                    source=item.source or "external_trend",
                    url=item.url,
                    evidence_type="external_source",
                    confidence=confidence,
                )
            )
        for topic in (top_performing_topics or [])[:5]:
            evidence.append(
                ResearchEvidence(
                    claim=f"Topic '{topic}' đang có tín hiệu tốt từ dữ liệu hiệu suất nội bộ.",
                    source="post_metrics",
                    evidence_type="internal_performance",
                    confidence=0.7,
                )
            )
        for question in (frequent_questions or [])[:5]:
            evidence.append(
                ResearchEvidence(
                    claim=f"Khách hàng đang hỏi: {question}",
                    source="comment_inbox",
                    evidence_type="customer_voice",
                    confidence=0.65,
                )
            )
        for focus in (campaign_focus or [])[:3]:
            evidence.append(
                ResearchEvidence(
                    claim=f"Campaign focus hiện tại: {focus}",
                    source="campaign_notes",
                    evidence_type="operator_input",
                    confidence=0.6,
                )
            )
        return evidence

    def _claims_from_document(self, document: SourceDocument, focus_terms: set[str]) -> list[str]:
        candidates = [sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(document.content) if sentence.strip()]
        if not candidates and document.title:
            candidates = [document.title]
        ranked = sorted(
            candidates,
            key=lambda sentence: self._sentence_score(sentence, focus_terms),
            reverse=True,
        )
        claims = [self._normalize_claim(item) for item in ranked if self._is_useful_claim(item)]
        if not claims and document.title:
            claims.append(document.title)
        return claims

    def _sentence_score(self, sentence: str, focus_terms: set[str]) -> float:
        words = {word.lower() for word in _WORD_RE.findall(sentence) if len(word) >= 3}
        overlap = len(words & focus_terms)
        length_score = min(1.0, len(sentence) / 180)
        return overlap * 2 + length_score

    @staticmethod
    def _focus_terms(items: list[str]) -> set[str]:
        return {word.lower() for item in items for word in _WORD_RE.findall(item) if len(word) >= 3}

    @staticmethod
    def _is_useful_claim(sentence: str) -> bool:
        words = _WORD_RE.findall(sentence)
        return 6 <= len(words) <= 45

    @staticmethod
    def _normalize_claim(sentence: str) -> str:
        sentence = re.sub(r"\s+", " ", sentence).strip()
        return sentence[:260]

    @staticmethod
    def _document_confidence(document: SourceDocument, claim: str) -> float:
        content_score = min(1.0, len(claim) / 160)
        confidence = document.trust_score * 0.65 + document.freshness_score * 0.15 + content_score * 0.2
        if document.metadata.get("fetch_status") == "error":
            confidence -= 0.2
        return round(min(1.0, max(0.0, confidence)), 3)


class ResearchQualityGate:
    """Score whether a research brief has enough reliable, checkable evidence."""

    def evaluate(
        self,
        *,
        evidence: list[ResearchEvidence],
        source_documents: list[SourceDocument] | None = None,
        external_trends: list[TrendItem] | None = None,
    ) -> ResearchQualityReport:
        source_documents = source_documents or []
        external_trends = external_trends or []
        warnings: list[str] = []

        source_names = {item.source for item in evidence if item.source}
        url_count = sum(1 for item in evidence if item.url)
        sourced_claims = [item for item in evidence if item.evidence_type in {"source_claim", "external_source"}]
        failed_fetches = [doc for doc in source_documents if doc.metadata.get("fetch_status") == "error"]
        dominant_source = self._dominant_source(evidence)

        if not external_trends and not source_documents:
            warnings.append("Không có external_trends hoặc source_documents; Research chỉ dựa vào dữ liệu nội bộ/operator.")
        checkable_sources = {
            item.source for item in evidence if item.source and item.evidence_type in {"source_claim", "external_source"}
        }
        if len(checkable_sources or source_names) < 2:
            warnings.append("Evidence chưa đủ đa nguồn; cần thêm ít nhất 2 nguồn độc lập.")
        if url_count == 0:
            warnings.append("Evidence chưa có URL nguồn để Writer trích dẫn hoặc kiểm chứng.")
        if len(sourced_claims) < 2:
            warnings.append("Chưa có đủ claim cụ thể từ nguồn đã thu thập.")
        if failed_fetches:
            warnings.append(f"Có {len(failed_fetches)} nguồn fetch thất bại; đang dùng fallback metadata.")
        if dominant_source:
            warnings.append(f"Evidence phụ thuộc nhiều vào một nguồn: {dominant_source}.")

        confidence = self._confidence_score(evidence)
        if warnings:
            confidence = round(max(0.0, confidence - min(0.2, len(warnings) * 0.04)), 3)
        return ResearchQualityReport(confidence_score=confidence, warnings=warnings)

    @staticmethod
    def _confidence_score(evidence: list[ResearchEvidence]) -> float:
        if not evidence:
            return 0.0
        return round(sum(item.confidence for item in evidence) / len(evidence), 3)

    @staticmethod
    def _dominant_source(evidence: list[ResearchEvidence]) -> str:
        checkable = [item.source for item in evidence if item.source and item.evidence_type in {"source_claim", "external_source"}]
        if len(checkable) < 3:
            return ""
        source, count = Counter(checkable).most_common(1)[0]
        if count / len(checkable) >= 0.75:
            return source
        return ""
