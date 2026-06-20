from __future__ import annotations

from hashlib import sha1
from typing import Protocol
from urllib.parse import urlparse

from fanpage_agent.models import SourceCandidate
from fanpage_agent.scraping.web_search import SearchResult, WebSearchClient


class SourceSearchClient(Protocol):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


class WebSourceDiscovery:
    """Discover candidate research sources from web search without trusting them by default."""

    def __init__(
        self,
        search_client: SourceSearchClient | None = None,
        blocked_domains: set[str] | None = None,
    ):
        self.search_client = search_client or WebSearchClient()
        self.blocked_domains = blocked_domains or set()

    def discover(self, queries: list[str], max_candidates: int = 5) -> list[SourceCandidate]:
        seen: set[str] = set()
        candidates: list[SourceCandidate] = []
        for query in queries:
            for result in self.search_client.search(query, max_results=max_candidates):
                if not result.url or result.url in seen:
                    continue
                seen.add(result.url)
                candidate = self._candidate_from_result(result, query)
                if candidate.status == "blocked":
                    continue
                candidates.append(candidate)
                if len(candidates) >= max_candidates:
                    return sorted(candidates, key=lambda item: item.relevance_score, reverse=True)
        return sorted(candidates, key=lambda item: item.relevance_score, reverse=True)

    def _candidate_from_result(self, result: SearchResult, query: str) -> SourceCandidate:
        domain = urlparse(result.url).netloc.lower()
        query_terms = {item.lower() for item in query.split() if len(item) > 2}
        result_text = f"{result.title} {result.snippet}".lower()
        matched_terms = {term for term in query_terms if term in result_text}
        relevance_score = min(1.0, 0.25 + len(matched_terms) / max(len(query_terms), 1))
        reason_codes = ["web_search_candidate"]
        status = "candidate"
        if domain in self.blocked_domains:
            status = "blocked"
            reason_codes.append("blocked_domain")
        if relevance_score < 0.45:
            reason_codes.append("low_relevance")
        source_id = f"disc-{sha1(result.url.encode('utf-8')).hexdigest()[:12]}"
        return SourceCandidate(
            source_id=source_id,
            title=result.title,
            url=result.url,
            snippet=result.snippet,
            discovery_query=query,
            relevance_score=round(relevance_score, 3),
            trust_score=0.45,
            status=status,
            reason_codes=reason_codes,
        )
