"""Shared data types — lightweight dataclasses for inter-agent communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    RESEARCHER = "researcher"
    STRATEGIST = "strategist"
    WRITER = "writer"
    DESIGNER = "designer"
    PUBLISHER = "publisher"
    COMMUNITY = "community"
    ANALYST = "analyst"


class ActionPriority(int, Enum):
    CRITICAL = 0  # publishing due
    HIGH = 1     # calendar gaps, urgent comments
    MEDIUM = 2   # content prep, triage
    LOW = 3      # analytics, learning


@dataclass
class AgentTask:
    """A task assigned to an agent by the orchestrator."""
    id: str
    target: AgentRole
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    priority: ActionPriority = ActionPriority.MEDIUM
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AgentResult:
    """Result returned by an agent after processing a task."""
    task_id: str
    success: bool
    data: Any = None  # dict | ContentPackage | list | str
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PipelineState:
    """Snapshot of the entire pipeline state — what the orchestrator sees."""
    # Calendar
    pending_approval: int = 0
    approved_ready: int = 0
    published_today: int = 0
    calendar_gap_days: list[str] = field(default_factory=list)
    next_publish_due: str | None = None

    # Community
    pending_triage: int = 0
    new_comments_24h: int = 0

    # Performance
    weekly_post_count: int = 0
    avg_reach_7d: float = 0.0
    avg_engagement_7d: float = 0.0
    top_pillar_last_7d: str | None = None

    # System
    last_tick_status: str = "unknown"
    errors_24h: int = 0
    uptime_hours: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "calendar": {
                "pending_approval": self.pending_approval,
                "approved_ready": self.approved_ready,
                "published_today": self.published_today,
                "gaps": self.calendar_gap_days,
                "next_due": self.next_publish_due,
            },
            "community": {
                "pending_triage": self.pending_triage,
                "new_comments_24h": self.new_comments_24h,
            },
            "performance": {
                "weekly_posts": self.weekly_post_count,
                "avg_reach": self.avg_reach_7d,
                "avg_engagement": self.avg_engagement_7d,
                "top_pillar": self.top_pillar_last_7d,
            },
            "system": {
                "last_tick": self.last_tick_status,
                "errors_24h": self.errors_24h,
                "uptime_hours": self.uptime_hours,
            },
        }


@dataclass
class ContentVariant:
    """A single content variant with performance tracking."""
    variant_id: str
    topic: str
    pillar: str
    caption: str
    hook: str
    cta: str
    format: str
    tone_tags: list[str] = field(default_factory=list)
    visual_brief: str | None = None
    image_path: str | None = None
    hashtags: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)

    # Filled after publishing
    published: bool = False
    permalink: str | None = None
    reach: int | None = None
    engagements: int | None = None
    score: float | None = None  # calculated performance score


@dataclass
class ContentPackage:
    """A content package with multiple variants for A/B testing."""
    package_id: str
    brand_id: str
    scheduled_date: str
    scheduled_time: str | None = None
    variants: list[ContentVariant] = field(default_factory=list)
    page_id: str = ""
    page_context: dict[str, Any] = field(default_factory=dict)
    research_packet_id: str = ""
    winning_variant: ContentVariant | None = None
    status: str = "draft"  # draft | approved | published | analysed

    def best_variant(self) -> ContentVariant | None:
        """Return the variant with highest score, or first if none."""
        scored = [v for v in self.variants if v.score is not None]
        if scored:
            return max(scored, key=lambda v: v.score or 0)
        return self.variants[0] if self.variants else None


@dataclass
class PerformancePattern:
    """A learned pattern about what content performs well."""
    pattern_id: str
    pattern_type: str  # hook_style | pillar | format | time | tone
    value: str
    avg_reach: float
    avg_engagement: float
    sample_size: int
    confidence: float  # 0.0-1.0
    last_seen: str
    recommendation: str | None = None
