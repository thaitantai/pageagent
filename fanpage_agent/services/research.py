from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from fanpage_agent.models import CommentInboxEntry, ResearchBrief, ResearchEvidence, TrendItem
from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer
from fanpage_agent.scraping.web_search import WebSearchClient

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
    ):
        self._trend_scraper = trend_scraper
        self._trend_analyzer = trend_analyzer

    def build_brief(
        self,
        store: object,
        comment_csv: str | Path | None = None,
        campaign_notes_file: str | Path | None = None,
        fetch_external_trends: bool = True,
        web_search_queries: list[str] | None = None,
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

        next_angles = self._dedupe(campaign_focus + frequent_questions + top_performing_topics)[:5]

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

        evidence = self._build_evidence(
            external_trends=external_trends,
            top_performing_topics=top_performing_topics,
            frequent_questions=frequent_questions,
            campaign_focus=campaign_focus,
        )
        confidence_score = self._confidence_score(evidence)
        quality_warnings = self._quality_warnings(evidence, external_trends)
        if quality_warnings:
            recommendations.append("Cần bổ sung nguồn trước khi Writer dùng các claim quan trọng.")

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
    ) -> list[ResearchEvidence]:
        evidence: list[ResearchEvidence] = []
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
