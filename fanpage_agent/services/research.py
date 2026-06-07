from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from fanpage_agent.models import (
    CommentInboxEntry,
    ResearchBrief,
    ResearchEvidence,
    ResearchTopicScore,
    SourceCandidate,
    SourceDocument,
    TrendItem,
)
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer
from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.services.product_topic_discovery import (
    ProductAwareTopicDiscovery,
    ProductTopicCandidate,
)
from fanpage_agent.services.research_insights import EvidenceExtractor, ResearchQualityGate

logger = logging.getLogger(__name__)

# Query mặc định để search trend khi không có campaign focus
FALLBACK_SEARCH_QUERIES: list[str] = [
    "xu hướng chăm sóc da 2026",
    "skincare routine mới nhất",
    "dưỡng da mùa hè Gen Z",
    "mẹo làm đẹp an toàn cho da dầu mụn",
    "thực phẩm chức năng làm đẹp da uy tín",
    "review kem chống nắng tốt nhất 2026",
    "treatment da mụn hiệu quả tại nhà",
    "serum vitamin C review tốt nhất",
    "retinoid cho người mới bắt đầu",
    "chăm sóc da ban đêm đúng cách",
]

# Số items tối đa từ web search trong research brief
MAX_SEARCH_ITEMS_IN_BRIEF = 15


class ResearchService:
    def __init__(
        self,
        trend_scraper: TrendScraper | None = None,
        trend_analyzer: TrendAnalyzer | None = None,
        evidence_extractor: EvidenceExtractor | None = None,
        quality_gate: ResearchQualityGate | None = None,
        topic_discovery: ProductAwareTopicDiscovery | None = None,
    ):
        self._trend_scraper = trend_scraper
        self._trend_analyzer = trend_analyzer
        self._evidence_extractor = evidence_extractor or EvidenceExtractor()
        self._quality_gate = quality_gate or ResearchQualityGate()
        self._topic_discovery = topic_discovery or ProductAwareTopicDiscovery()

    def build_brief(
        self,
        store: object,
        comment_csv: str | Path | None = None,
        campaign_notes_file: str | Path | None = None,
        fetch_external_trends: bool = True,
        web_search_queries: list[str] | None = None,
        source_documents: list[SourceDocument] | None = None,
        source_candidates: list[SourceCandidate] | None = None,
        page_context: dict[str, Any] | None = None,
        discover_product_topics: bool = False,
        max_product_topics: int = 8,
    ) -> ResearchBrief:
        """Build research brief with optional web search + scrape.

        Parameters
        ----------
        store : object
            Data store (LocalSheetStore) với read_post_history/read_post_metrics.
        comment_csv : str | Path | None
            CSV file chứa comment/inbox.
        campaign_notes_file : str | Path | None
            JSON file chứa campaign notes.
        fetch_external_trends : bool
            Có fetch external trends từ TrendScraper không.
        web_search_queries : list[str] | None
            Override query tìm kiếm. Nếu None và fetch_external_trends=True,
            tự sinh từ campaign focus + fallback queries.
        """
        history = store.read_post_history(limit=90)
        metrics = store.read_post_metrics()
        comments = self._read_comments(comment_csv)
        campaign_notes = self._read_campaign_notes(campaign_notes_file)

        topic_counts = Counter(item.topic for item in history if item.topic)
        overused_topics = [topic for topic, count in topic_counts.items() if count >= 2]

        top_performing_topics = [
            item.topic
            for item in sorted(metrics, key=lambda x: (x.leads, x.engagement_rate, x.reach), reverse=True)[:3]
            if item.topic
        ]

        recommended_pillars = [
            item.pillar
            for item in sorted(metrics, key=lambda x: (x.leads, x.engagement_rate, x.reach), reverse=True)
            if item.pillar
        ]
        recommended_pillars = self._dedupe(recommended_pillars)

        recommended_objectives: list[str] = []
        priority_objective = campaign_notes.get("priority_objective")
        if priority_objective:
            recommended_objectives.append(priority_objective)
        metric_objectives = [
            item.objective
            for item in sorted(metrics, key=lambda x: (x.leads, x.engagement_rate, x.reach), reverse=True)
            if item.objective
        ]
        recommended_objectives.extend(metric_objectives)
        recommended_objectives = self._dedupe(recommended_objectives)

        frequent_questions = [item.message for item in comments[:5]]
        campaign_focus = [item for item in campaign_notes.get("campaign_focus", []) if item]

        product_topics: list[ProductTopicCandidate] = []
        if discover_product_topics:
            product_topics = self._topic_discovery.discover(page_context or {}, max_topics=max_product_topics)
        product_topic_titles = [item.topic for item in product_topics]
        next_angles = self._dedupe(product_topic_titles + campaign_focus + frequent_questions + top_performing_topics)[:5]

        recommendations: list[str] = []
        if recommended_objectives:
            recommendations.append(f"Ưu tiên objective {recommended_objectives[0]} trong vòng nội dung kế tiếp.")
        if recommended_pillars:
            recommendations.append(f"Ưu tiên pillar {recommended_pillars[0]} vì đang có tín hiệu tốt từ dữ liệu hiệu suất.")
        if overused_topics:
            recommendations.append(f"Giảm lặp lại topic: {overused_topics[0]}.")
        if campaign_focus:
            recommendations.append(f"Bám campaign focus: {campaign_focus[0]}.")
        if frequent_questions:
            recommendations.append(f"Khai thác câu hỏi khách hàng thật: {frequent_questions[0]}")

        external_trends: list[TrendItem] = []
        trend_keywords: list[str] = []
        trend_clusters: dict[str, list[str]] = {}
        source_documents = source_documents or []
        source_candidates = source_candidates or []

        if fetch_external_trends and self._trend_scraper:
            try:
                # --- Bước 1: Web Search (nếu có WebSearchClient) ---
                search_queries = self._build_search_queries(
                    campaign_focus, top_performing_topics, web_search_queries
                )
                web_trends = self._trend_scraper.search_trends(
                    queries=search_queries,
                    max_articles=MAX_SEARCH_ITEMS_IN_BRIEF,
                )
                if web_trends:
                    external_trends.extend(web_trends)
                    recommendations.append(
                        f"Tìm thấy {len(web_trends)} nội dung qua web search — xem external_trends."
                    )

                # --- Bước 2: Fixed URL scrape (như cũ) ---
                fixed_trends = self._trend_scraper.fetch_all()
                if fixed_trends:
                    external_trends.extend(fixed_trends)
                    recommendations.append(
                        f"Có {len(fixed_trends)} trend từ nguồn cố định — xem external_trends để tham khảo."
                    )

                # --- Bước 3: TrendAnalyzer ---
                if external_trends and self._trend_analyzer:
                    self._trend_analyzer = TrendAnalyzer(external_trends)
                    report = self._trend_analyzer.generate_report()
                    trend_keywords = [kw["word"] for kw in report["top_keywords"][:15]]
                    trend_clusters = report["clusters"]
                    recommendations.append(f"Top keyword từ trend: {', '.join(trend_keywords[:5])}.")
                    recommendations.append(f"Cluster nổi bật: {', '.join(list(trend_clusters.keys())[:3])}.")

            except Exception as exc:
                logger.warning("TrendScraper/web search thất bại: %s", exc)

        evidence = self._evidence_extractor.extract(
            external_trends=external_trends,
            top_performing_topics=top_performing_topics,
            frequent_questions=frequent_questions,
            campaign_focus=campaign_focus,
            source_documents=source_documents,
        )
        quality_report = self._quality_gate.evaluate(
            evidence=evidence,
            source_documents=source_documents,
            external_trends=external_trends,
        )
        confidence_score = quality_report.confidence_score
        quality_warnings = quality_report.warnings
        quality_warnings.extend(self._affiliate_evidence_warnings(product_topics, evidence))
        topic_scores = self._score_topics(
            candidates=self._dedupe(next_angles + top_performing_topics),
            campaign_focus=campaign_focus,
            overused_topics=overused_topics,
            frequent_questions=frequent_questions,
            evidence=evidence,
            product_topics=product_topics,
        )
        if product_topics:
            recommendations.append(f"Đã đề xuất {len(product_topics)} topic dựa trên sản phẩm/vấn đề khách hàng.")
        if topic_scores:
            recommendations.append(f"Ưu tiên topic có điểm cao nhất: {topic_scores[0].topic}.")
        if quality_warnings:
            recommendations.append("Cần bổ sung nguồn trước khi Writer dùng các claim quan trọng.")
        if source_candidates:
            recommendations.append(f"Tìm thấy {len(source_candidates)} nguồn ứng viên mới cần operator duyệt trước khi tin dùng.")

        return ResearchBrief(
            top_performing_topics=top_performing_topics,
            overused_topics=overused_topics,
            frequent_questions=frequent_questions,
            campaign_focus=campaign_focus,
            recommended_pillars=recommended_pillars,
            recommended_objectives=recommended_objectives,
            next_angles=next_angles,
            recommendations=recommendations,
            external_trends=external_trends,
            trend_keywords=trend_keywords,
            trend_clusters=trend_clusters,
            evidence=evidence,
            confidence_score=confidence_score,
            quality_warnings=quality_warnings,
            topic_scores=topic_scores,
            source_documents=source_documents,
            source_candidates=source_candidates,
        )

    def _build_search_queries(
        self,
        campaign_focus: list[str],
        top_performing_topics: list[str],
        override_queries: list[str] | None,
    ) -> list[str]:
        """Tự sinh search queries từ campaign focus + performance data.

        Ưu tiên: override → campaign → top topics → fallback.
        """
        if override_queries:
            return override_queries

        queries: list[str] = []
        # Từ campaign focus
        for cf in campaign_focus:
            queries.append(f"xu hướng {cf} 2026")
            queries.append(f"{cf} skincare review")
            queries.append(f"{cf} mẹo làm đẹp")

        # Từ top performing topics
        for topic in top_performing_topics:
            queries.append(f"{topic} mới nhất")
            queries.append(f"{topic} xu hướng")

        # Dedup + fallback nếu thiếu
        seen: set[str] = set()
        deduped: list[str] = []
        for q in queries:
            ql = q.lower().strip()
            if ql not in seen:
                seen.add(ql)
                deduped.append(q)

        # Thêm fallback nếu chưa đủ query
        if len(deduped) < 3:
            for fq in FALLBACK_SEARCH_QUERIES:
                if fq.lower() not in seen:
                    deduped.append(fq)
                    seen.add(fq.lower())
                if len(deduped) >= 5:
                    break

        # Giới hạn tối đa 8 queries mỗi lần build brief
        return deduped[:8]

    def _build_evidence(
        self,
        external_trends: list[TrendItem],
        top_performing_topics: list[str],
        frequent_questions: list[str],
        campaign_focus: list[str],
        source_documents: list[SourceDocument] | None = None,
    ) -> list[ResearchEvidence]:
        evidence: list[ResearchEvidence] = []
        for document in (source_documents or [])[:10]:
            confidence = min(1.0, max(0.0, document.trust_score * 0.7 + document.freshness_score * 0.3))
            evidence.append(ResearchEvidence(
                claim=document.title or document.content[:120] or document.source_name,
                source=document.source_name,
                url=document.url,
                evidence_type="registered_source",
                confidence=round(confidence, 3),
                source_id=document.source_id,
                source_type=document.source_type,
            ))
        for item in external_trends[:10]:
            confidence = 0.75 if item.url else 0.55
            evidence.append(ResearchEvidence(
                claim=item.title,
                source=item.source or "external_trend",
                url=item.url,
                evidence_type="external_source",
                confidence=confidence,
            ))
        for topic in top_performing_topics[:5]:
            evidence.append(ResearchEvidence(
                claim=f"Topic '{topic}' đang có tín hiệu tốt từ dữ liệu hiệu suất nội bộ.",
                source="post_metrics",
                evidence_type="internal_performance",
                confidence=0.7,
            ))
        for question in frequent_questions[:5]:
            evidence.append(ResearchEvidence(
                claim=f"Khách hàng đang hỏi: {question}",
                source="comment_inbox",
                evidence_type="customer_voice",
                confidence=0.65,
            ))
        for focus in campaign_focus[:3]:
            evidence.append(ResearchEvidence(
                claim=f"Campaign focus hiện tại: {focus}",
                source="campaign_notes",
                evidence_type="operator_input",
                confidence=0.6,
            ))
        return evidence

    def _affiliate_evidence_warnings(
        self,
        product_topics: list[ProductTopicCandidate],
        evidence: list[ResearchEvidence],
    ) -> list[str]:
        warnings: list[str] = []
        for topic in product_topics:
            if not topic.is_affiliate_offer:
                continue
            confidence = self._topic_source_confidence(topic.topic, evidence)
            if confidence < 0.45:
                warnings.append(
                    f"Affiliate topic '{topic.topic}' chưa có evidence đủ mạnh; chỉ dùng làm câu hỏi nghiên cứu, không dùng làm khuyến nghị mua."
                )
        return warnings

    def _score_topics(
        self,
        candidates: list[str],
        campaign_focus: list[str],
        overused_topics: list[str],
        frequent_questions: list[str],
        evidence: list[ResearchEvidence],
        product_topics: list[ProductTopicCandidate] | None = None,
    ) -> list[ResearchTopicScore]:
        scores: list[ResearchTopicScore] = []
        product_topic_map = {item.topic: item for item in (product_topics or [])}
        for topic in candidates[:12]:
            product_topic = product_topic_map.get(topic)
            brand_relevance = max(
                self._keyword_overlap_score(topic, campaign_focus),
                product_topic.product_relevance if product_topic else 0.0,
            )
            question_overlap = self._keyword_overlap_score(topic, frequent_questions)
            source_confidence = self._topic_source_confidence(topic, evidence)
            duplication_risk = 0.85 if topic in overused_topics else 0.15
            novelty = 1.0 - duplication_risk
            customer_value = product_topic.customer_value if product_topic else question_overlap
            content_potential = min(1.0, 0.30 + customer_value * 0.35 + source_confidence * 0.3)
            fanpage_fit = min(1.0, 0.40 + brand_relevance * 0.35 + customer_value * 0.2)
            affiliate_without_evidence = bool(
                product_topic and product_topic.is_affiliate_offer and source_confidence < 0.45
            )
            risk_penalty = 0.08 if product_topic and product_topic.risk_level == "medium" else 0.0
            if affiliate_without_evidence:
                risk_penalty += 0.18
                content_potential = min(content_potential, 0.45)
            total = max(0.0, (
                brand_relevance * 0.25
                + novelty * 0.16
                + content_potential * 0.18
                + source_confidence * 0.14
                + fanpage_fit * 0.14
                + customer_value * 0.10
                + (1.0 - duplication_risk) * 0.03
                - risk_penalty
            ))
            if affiliate_without_evidence:
                total = min(total, 0.49)
            rationale = self._topic_score_rationale(
                topic=topic,
                brand_relevance=brand_relevance,
                novelty=novelty,
                source_confidence=source_confidence,
                duplication_risk=duplication_risk,
                product_topic=product_topic,
            )
            scores.append(ResearchTopicScore(
                topic=topic,
                total_score=round(total, 3),
                brand_relevance=round(brand_relevance, 3),
                novelty=round(novelty, 3),
                content_potential=round(content_potential, 3),
                source_confidence=round(source_confidence, 3),
                fanpage_fit=round(fanpage_fit, 3),
                duplication_risk=round(duplication_risk, 3),
                product_relevance=round(product_topic.product_relevance, 3) if product_topic else 0.0,
                customer_value=round(customer_value, 3),
                risk_level="high" if affiliate_without_evidence else (product_topic.risk_level if product_topic else ""),
                rationale=rationale,
            ))
        return sorted(scores, key=lambda item: item.total_score, reverse=True)

    @staticmethod
    def _keyword_overlap_score(topic: str, references: list[str]) -> float:
        topic_words = {word for word in topic.lower().split() if len(word) >= 3}
        if not topic_words or not references:
            return 0.0
        best = 0.0
        for reference in references:
            ref_words = {word for word in reference.lower().split() if len(word) >= 3}
            if ref_words:
                best = max(best, len(topic_words & ref_words) / len(topic_words))
        return min(1.0, best)

    def _topic_source_confidence(self, topic: str, evidence: list[ResearchEvidence]) -> float:
        topic_words = {word for word in topic.lower().split() if len(word) >= 3}
        if not topic_words:
            return 0.0
        matches = []
        for item in evidence:
            claim_words = {word for word in item.claim.lower().split() if len(word) >= 3}
            if topic_words & claim_words:
                matches.append(item.confidence)
        if not matches:
            return 0.0
        return min(1.0, sum(matches) / len(matches))

    @staticmethod
    def _topic_score_rationale(
        topic: str,
        brand_relevance: float,
        novelty: float,
        source_confidence: float,
        duplication_risk: float,
        product_topic: ProductTopicCandidate | None = None,
    ) -> str:
        signals: list[str] = []
        if product_topic:
            signals.append(f"gắn với sản phẩm {product_topic.product_name}")
            if product_topic.customer_pain:
                signals.append(f"giải quyết pain point {product_topic.customer_pain}")
            if product_topic.risk_level == "medium":
                signals.append("cần guardrail claim")
            if product_topic.is_affiliate_offer and source_confidence < 0.45:
                signals.append("chưa đủ evidence để khuyến nghị mua")
        if brand_relevance >= 0.5:
            signals.append("sát campaign/brand")
        if novelty >= 0.7:
            signals.append("ít trùng lặp")
        if source_confidence >= 0.6:
            signals.append("có evidence hỗ trợ")
        if duplication_risk >= 0.8:
            signals.append("rủi ro lặp topic cũ")
        if not signals:
            signals.append("cần thêm dữ liệu trước khi ưu tiên")
        return f"{topic}: " + ", ".join(signals)

    @staticmethod
    def _confidence_score(evidence: list[ResearchEvidence]) -> float:
        if not evidence:
            return 0.0
        return round(sum(item.confidence for item in evidence) / len(evidence), 3)

    @staticmethod
    def _quality_warnings(evidence: list[ResearchEvidence], external_trends: list[TrendItem]) -> list[str]:
        warnings: list[str] = []
        if not external_trends:
            warnings.append("Không có external_trends; Research chỉ dựa vào dữ liệu nội bộ/operator.")
        source_count = len({item.source for item in evidence if item.source})
        if source_count < 2:
            warnings.append("Evidence chưa đủ đa nguồn; cần thêm ít nhất 2 nguồn độc lập.")
        if not any(item.url for item in evidence):
            warnings.append("Evidence chưa có URL nguồn để Writer trích dẫn hoặc kiểm chứng.")
        return warnings

    @staticmethod
    def _read_comments(path: str | Path | None) -> list[CommentInboxEntry]:
        if not path:
            return []
        file_path = Path(path)
        if not file_path.exists():
            return []
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return [
            CommentInboxEntry(
                id=row.get("id", ""),
                post_id=row.get("post_id", ""),
                created_at=row.get("created_at", ""),
                source=row.get("source", ""),
                message=row.get("message", ""),
            )
            for row in rows
            if row.get("message")
        ]

    @staticmethod
    def _read_campaign_notes(path: str | Path | None) -> dict:
        if not path:
            return {}
        file_path = Path(path)
        if not file_path.exists():
            return {}
        return json.loads(file_path.read_text(encoding="utf-8"))

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result
