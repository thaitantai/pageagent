from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from scrapling.fetchers import Fetcher

from fanpage_agent.models import ResearchSource, SourceDocument

logger = logging.getLogger(__name__)


class ScraplingFetcher(Protocol):
    @staticmethod
    def get(url: str, timeout: int = 15) -> Any: ...


class ScraplingSourceCollector:
    """Fetch trusted registry sources with Scrapling and normalize them to SourceDocument."""

    def __init__(
        self,
        timeout: int = 15,
        cache_dir: str | Path | None = None,
        fetcher: ScraplingFetcher | None = None,
    ):
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.fetcher = fetcher or Fetcher

    def collect(self, sources: list[ResearchSource], max_sources: int = 10) -> list[SourceDocument]:
        documents: list[SourceDocument] = []
        for source in sources[:max_sources]:
            if not source.url:
                documents.append(self._fallback_document(source, "missing_url"))
                continue
            cached = self._read_cache(source)
            if cached:
                documents.append(cached)
                continue
            try:
                document = self._fetch_source(source)
                documents.append(document)
                self._write_cache(document)
            except Exception as exc:
                logger.warning("SourceCollector: skip %s — %s", source.source_id, exc)
                documents.append(self._fallback_document(source, f"fetch_failed:{type(exc).__name__}"))
        return documents

    def _fetch_source(self, source: ResearchSource) -> SourceDocument:
        page = self.fetcher.get(source.url, timeout=self.timeout)
        status = getattr(page, "status", 0)
        if status and status != 200:
            raise RuntimeError(f"HTTP {status}")
        text = self._page_text(page)
        return SourceDocument(
            source_id=source.source_id,
            source_name=source.name,
            source_type=source.source_type,
            url=source.url,
            title=self._page_title(page) or source.name,
            content=text[:5000],
            fetched_at=datetime.now(timezone.utc).isoformat(),
            trust_score=source.trust_score,
            freshness_score=1.0 if text else 0.0,
            metadata={"topics": source.topics, "allowed_pages": source.allowed_pages, "fetch_status": "ok"},
        )

    def _fallback_document(self, source: ResearchSource, reason: str) -> SourceDocument:
        return SourceDocument(
            source_id=source.source_id,
            source_name=source.name,
            source_type=source.source_type,
            url=source.url,
            title=source.name,
            content=source.notes,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            trust_score=source.trust_score,
            freshness_score=0.0,
            metadata={"topics": source.topics, "allowed_pages": source.allowed_pages, "fetch_status": reason},
        )

    def _page_text(self, page) -> str:
        if hasattr(page, "get_all_text"):
            return str(page.get_all_text() or "").strip()
        return str(page or "").strip()

    def _page_title(self, page) -> str:
        try:
            title = page.css("title::text").get()
            return str(title or "").strip()
        except Exception:
            return ""

    def _cache_path(self, source: ResearchSource) -> Path | None:
        if not self.cache_dir:
            return None
        digest = hashlib.sha256(source.url.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{source.source_id}-{digest}.json"

    def _read_cache(self, source: ResearchSource) -> SourceDocument | None:
        cache_path = self._cache_path(source)
        if not cache_path or not cache_path.exists():
            return None
        try:
            return SourceDocument.model_validate(json.loads(cache_path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.debug("SourceCollector: ignore invalid cache %s — %s", cache_path, exc)
            return None

    def _write_cache(self, document: SourceDocument) -> None:
        if not self.cache_dir:
            return
        cache_path = self._cache_path(
            ResearchSource(source_id=document.source_id, name=document.source_name, url=document.url)
        )
        if not cache_path:
            return
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
