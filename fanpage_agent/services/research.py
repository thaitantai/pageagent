from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from pathlib import Path

from fanpage_agent.models import CommentInboxEntry, ResearchBrief, TrendItem
from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer

logger = logging.getLogger(__name__)


class ResearchService:
    def __init__(self, trend_scraper: TrendScraper | None = None, trend_analyzer: TrendAnalyzer | None = None):
        self._trend_scraper = trend_scraper
        self._trend_analyzer = trend_analyzer

    def build_brief(self, store: object, comment_csv: str | Path | None = None, campaign_notes_file: str | Path | None = None, fetch_external_trends: bool = True) -> ResearchBrief:
        history = store.read_post_history(limit=90)
        metrics = store.read_post_metrics()
        comments = self._read_comments(comment_csv)
        campaign_notes = self._read_campaign_notes(campaign_notes_file)

        topic_counts = Counter(item.topic for item in history if item.topic)
        overused_topics = [topic for topic, count in topic_counts.items() if count >= 2]

        top_performing_topics = [item.topic for item in sorted(metrics, key=lambda x: (x.leads, x.engagement_rate, x.reach), reverse=True)[:3] if item.topic]

        recommended_pillars = [item.pillar for item in sorted(metrics, key=lambda x: (x.leads, x.engagement_rate, x.reach), reverse=True) if item.pillar]
        recommended_pillars = self._dedupe(recommended_pillars)

        recommended_objectives: list[str] = []
        priority_objective = campaign_notes.get("priority_objective")
        if priority_objective:
            recommended_objectives.append(priority_objective)
        metric_objectives = [item.objective for item in sorted(metrics, key=lambda x: (x.leads, x.engagement_rate, x.reach), reverse=True) if item.objective]
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
                external_trends = self._trend_scraper.fetch_all()
                if external_trends:
                    recommendations.append(f"Có {len(external_trends)} trend ngoài — xem external_trends để tham khảo.")
                # Enrich with TrendAnalyzer
                if external_trends and self._trend_analyzer:
                    self._trend_analyzer = TrendAnalyzer(external_trends)
                    report = self._trend_analyzer.generate_report()
                    trend_keywords = [kw["word"] for kw in report["top_keywords"][:15]]
                    trend_clusters = report["clusters"]
                    recommendations.append(f"Top keyword từ trend: {', '.join(trend_keywords[:5])}.")
                    recommendations.append(f"Cluster nổi bật: {', '.join(list(trend_clusters.keys())[:3])}.")
            except Exception as exc:
                logger.warning("TrendScraper/TrendAnalyzer thất bại: %s", exc)

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
        )

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
