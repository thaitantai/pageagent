from fanpage_agent.scraping.multi_source_search import (
    DDGBackend,
    MultiSourceSearchClient,
    SearchBackend,
    SearchResult,
    SearXNGBackend,
    VNCrawlerBackend,
)
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer
from fanpage_agent.scraping.trend_scraper import DEFAULT_TREND_SOURCES, TrendScraper
from fanpage_agent.scraping.web_search import WebSearchClient

__all__ = [
    "MultiSourceSearchClient",
    "SearchBackend",
    "VNCrawlerBackend",
    "SearXNGBackend",
    "DDGBackend",
    "TrendAnalyzer",
    "TrendScraper",
    "DEFAULT_TREND_SOURCES",
    "WebSearchClient",
    "SearchResult",
]
