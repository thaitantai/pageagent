"""
fanpage_agent.tools — tool implementations for the agent pipeline.

Organized by domain:
  research/    — research pipeline, sources, offers, variants
  content/     — writing, media, verification, hashtags
  publishing/  — scheduling, delivery, calendar, community triage
  data/        — data fetching, metrics
  analytics/   — analytics, dashboard, evaluation
"""

# ── research group ────────────────────────────────────────────
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.tools.research.research_insights import EvidenceExtractor, ResearchQualityGate
from fanpage_agent.tools.research.research_packet import build_research_packet, research_handoff_policy, save_research_packet
from fanpage_agent.tools.research.research_sources import SourceRegistry
from fanpage_agent.tools.research.source_discovery import WebSourceDiscovery
from fanpage_agent.tools.research.product_topic_discovery import ProductAwareTopicDiscovery, ProductTopicCandidate
from fanpage_agent.tools.research.competitor_page_discovery import CompetitorPageDiscoveryTool
from fanpage_agent.tools.research.offer_discovery import OfferDiscoveryTool
from fanpage_agent.tools.research.offer_evaluator import OfferEvaluator, SearchClient
from fanpage_agent.tools.research.variant_scorer import VariantScorer

# ── content group ─────────────────────────────────────────────
from fanpage_agent.tools.content.writer import WriterTool
from fanpage_agent.tools.content.auto_content import AutoContentOrchestrator
from fanpage_agent.tools.content.auto_approval import AutoApprovalConfig, AutoApprovalEngine
from fanpage_agent.tools.content.verifier import VerifierTool
from fanpage_agent.tools.content.hashtag import HashtagTool
from fanpage_agent.tools.content.content_stats import compute_content_stats
from fanpage_agent.tools.content.image_gen import build_image_service

# ── publishing group ──────────────────────────────────────────
from fanpage_agent.tools.publishing.scheduled_publish import ScheduledPublishResult, ScheduledPublishTool
from fanpage_agent.tools.publishing.delivery import DeliveryTool
from fanpage_agent.tools.publishing.telegram_formatter import TelegramFormatterTool
from fanpage_agent.tools.publishing.daily_ops import DailyOpsTool
from fanpage_agent.tools.publishing.planner import PlannerTool
from fanpage_agent.tools.publishing.calendar_gap_service import CalendarGapTool
from fanpage_agent.tools.publishing.community_triage import CommunityTriageTool

# ── data group ────────────────────────────────────────────────
from fanpage_agent.tools.data.data_fetch import DataFetchTool
from fanpage_agent.tools.data.metrics_auto_fetch import MetricsAutoFetchTool

# ── analytics group ───────────────────────────────────────────
from fanpage_agent.tools.analytics.analytics import AnalyticsTool
from fanpage_agent.tools.analytics.analytics_dashboard import AnalyticsDashboardTool
from fanpage_agent.tools.analytics.analytics_reviewer import AnalyticsReviewer, _parse_fb_datetime, _parse_int
from fanpage_agent.tools.analytics.evals import EvalTool

__all__ = [
    # research
    "ResearchTool",
    "EvidenceExtractor",
    "ResearchQualityGate",
    "build_research_packet",
    "research_handoff_policy",
    "save_research_packet",
    "SourceRegistry",
    "WebSourceDiscovery",
    "ProductAwareTopicDiscovery",
    "ProductTopicCandidate",
    "CompetitorPageDiscoveryTool",
    "OfferDiscoveryTool",
    "OfferEvaluator",
    "SearchClient",
    "VariantScorer",
    # content
    "WriterTool",
    "AutoContentOrchestrator",
    "AutoApprovalConfig",
    "AutoApprovalEngine",
    "VerifierTool",
    "HashtagTool",
    "compute_content_stats",
    "build_image_service",
    # publishing
    "ScheduledPublishResult",
    "ScheduledPublishTool",
    "DeliveryTool",
    "TelegramFormatterTool",
    "DailyOpsTool",
    "PlannerTool",
    "CalendarGapTool",
    "CommunityTriageTool",
    # data
    "DataFetchTool",
    "MetricsAutoFetchTool",
    # analytics
    "AnalyticsTool",
    "AnalyticsDashboardTool",
    "AnalyticsReviewer",
    "_parse_fb_datetime",
    "_parse_int",
    "EvalTool",
]
