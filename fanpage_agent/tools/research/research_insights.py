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

    def __init__(self, min_corroboration_overlap: int = 2):
        self._min_corroboration_overlap = min_corroboration_overlap

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
        return self._with_corroboration(evidence)

    def _with_corroboration(self, evidence: list[ResearchEvidence]) -> list[ResearchEvidence]:
        enriched: list[ResearchEvidence] = []
        for item in evidence:
            supporting_sources = self._supporting_sources(item, evidence)
            support_count = max(1, len(supporting_sources) + 1)
            confidence = item.confidence
            if supporting_sources:
                confidence = min(1.0, confidence + min(0.12, 0.04 * len(supporting_sources)))
            enriched.append(
                item.model_copy(
                    update={
                        "confidence": round(confidence, 3),
                        "support_count": support_count,
                        "corroborating_sources": supporting_sources,
                    }
                )
            )
        return enriched

    def _supporting_sources(
        self,
        target: ResearchEvidence,
        evidence: list[ResearchEvidence],
    ) -> list[str]:
        target_terms = self._focus_terms([target.claim])
        if not target_terms:
            return []

        sources: list[str] = []
        for candidate in evidence:
            if candidate.source == target.source:
                continue
            candidate_terms = self._focus_terms([candidate.claim])
            if len(target_terms & candidate_terms) >= self._min_corroboration_overlap:
                sources.append(candidate.source)
        return sorted(set(sources))

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
        corroborated_claims = [item for item in sourced_claims if item.support_count >= 2]
        failed_fetches = [doc for doc in source_documents if doc.metadata.get("fetch_status") == "error"]
        dominant_source = self._dominant_source(evidence)
        diverse_source_names = {item.source for item in evidence if item.evidence_type in {"source_claim", "external_source"}}

        if not external_trends and not source_documents:
            warnings.append("Không có external_trends hoặc source_documents; Research chỉ dựa vào dữ liệu nội bộ/operator.")
        if len(diverse_source_names) < 2:
            warnings.append("Chưa đủ nguồn độc lập; cần ít nhất 2 nguồn ngoài cho evidence claim.")
        if len(sourced_claims) < 2:
            warnings.append("Chưa có đủ claim cụ thể từ nguồn đã thu thập.")
        if diverse_source_names and not corroborated_claims:
            warnings.append("Chưa có claim nào được corroborate bởi nguồn độc lập khác.")
        if url_count < 2:
            warnings.append("Cần ít nhất 2 URL nguồn để Writer trích dẫn hoặc kiểm chứng.")
        if failed_fetches:
            warnings.append(f"Có {len(failed_fetches)} nguồn fetch thất bại; đang dùng fallback metadata.")
        if dominant_source:
            warnings.append(f"Evidence phụ thuộc nhiều vào một nguồn: {dominant_source}.")

        confidence = self._confidence_score(evidence)
        # Penalty: mỗi warning giảm 0.05 confidence
        if warnings:
            confidence = round(max(0.0, confidence - min(0.3, len(warnings) * 0.05)), 3)
        return ResearchQualityReport(confidence_score=confidence, warnings=warnings)

    @staticmethod
    def _confidence_score(evidence: list[ResearchEvidence]) -> float:
        if not evidence:
            return 0.0
        base_score = sum(item.confidence for item in evidence) / len(evidence)
        corroborated_count = sum(1 for item in evidence if item.support_count >= 2)
        corroboration_bonus = min(0.06, corroborated_count * 0.008)
        url_bonus = min(0.04, sum(1 for item in evidence if item.url) * 0.005)
        return round(min(0.85, base_score + corroboration_bonus + url_bonus), 3)

    @staticmethod
    def _dominant_source(evidence: list[ResearchEvidence]) -> str:
        checkable = [item.source for item in evidence if item.source and item.evidence_type in {"source_claim", "external_source"}]
        if len(checkable) < 3:
            return ""
        source, count = Counter(checkable).most_common(1)[0]
        if count / len(checkable) >= 0.6:
            return source
        return ""
