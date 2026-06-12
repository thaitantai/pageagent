"""Research tools: topic discovery, competitor analysis, offer evaluation, self-learning."""

from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.tools.research.research_packet import build_research_packet
from fanpage_agent.tools.research.research_insights import EvidenceExtractor, ResearchQualityGate
from fanpage_agent.tools.research.research_sources import SourceRegistry
from fanpage_agent.tools.research.source_discovery import WebSourceDiscovery
from fanpage_agent.tools.research.search_query_builder import build_search_queries
from fanpage_agent.tools.research.product_topic_discovery import ProductAwareTopicDiscovery
from fanpage_agent.tools.research.competitor_page_discovery import CompetitorPageDiscoveryTool
from fanpage_agent.tools.research.competitor_learning_engine import CompetitorLearningEngine
from fanpage_agent.tools.research.offer_discovery import OfferDiscoveryTool
from fanpage_agent.tools.research.offer_evaluator import OfferEvaluator
from fanpage_agent.tools.research.variant_scorer import VariantScorer
from fanpage_agent.tools.research.topic_performance import TopicPerformanceStore

__all__ = [
    "ResearchTool",
    "build_research_packet",
    "EvidenceExtractor",
    "ResearchQualityGate",
    "SourceRegistry",
    "WebSourceDiscovery",
    "build_search_queries",
    "ProductAwareTopicDiscovery",
    "CompetitorPageDiscoveryTool",
    "CompetitorLearningEngine",
    "OfferDiscoveryTool",
    "OfferEvaluator",
    "VariantScorer",
    "TopicPerformanceStore",
]
