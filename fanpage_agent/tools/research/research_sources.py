from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fanpage_agent.models import ResearchSource, SourceDocument


class SourceRegistry:
    """Load trusted research sources from a local JSON registry."""

    def __init__(self, sources: list[ResearchSource] | None = None):
        self.sources = sources or []

    @classmethod
    def from_file(cls, path: str | Path | None) -> "SourceRegistry":
        if not path:
            return cls()
        file_path = Path(path)
        if not file_path.exists():
            return cls()
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        rows = payload.get("sources", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("source registry must be a list or an object with a sources list")
        return cls([ResearchSource.model_validate(row) for row in rows])

    def select(
        self,
        page_id: str = "",
        topics: list[str] | None = None,
        enabled_only: bool = True,
    ) -> list[ResearchSource]:
        topics_lower = {topic.lower() for topic in (topics or []) if topic}
        selected: list[ResearchSource] = []
        for source in self.sources:
            if enabled_only and not source.enabled:
                continue
            if source.allowed_pages and page_id and page_id not in source.allowed_pages:
                continue
            if topics_lower and source.topics:
                source_topics = {topic.lower() for topic in source.topics}
                if not self._topics_overlap(topics_lower, source_topics):
                    continue
            selected.append(source)
        return sorted(selected, key=lambda item: item.trust_score, reverse=True)

    @staticmethod
    def _topics_overlap(requested: set[str], source_topics: set[str]) -> bool:
        for requested_topic in requested:
            for source_topic in source_topics:
                if requested_topic == source_topic:
                    return True
                if source_topic in requested_topic or requested_topic in source_topic:
                    return True
        return False

    def to_documents(self, page_id: str = "", topics: list[str] | None = None) -> list[SourceDocument]:
        documents: list[SourceDocument] = []
        for source in self.select(page_id=page_id, topics=topics):
            documents.append(
                SourceDocument(
                    source_id=source.source_id,
                    source_name=source.name,
                    source_type=source.source_type,
                    url=source.url,
                    title=source.name,
                    content=source.notes,
                    trust_score=source.trust_score,
                    freshness_score=1.0,
                    metadata={"topics": source.topics, "allowed_pages": source.allowed_pages},
                )
            )
        return documents


def documents_from_raw(items: list[dict[str, Any]]) -> list[SourceDocument]:
    return [SourceDocument.model_validate(item) for item in items]
