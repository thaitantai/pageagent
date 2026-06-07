from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class TargetAudience(BaseModel):
    segment_name: str
    pain_points: List[str] = Field(default_factory=list)
    desired_outcomes: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    preferred_content_formats: List[str] = Field(default_factory=list)


class ProductService(BaseModel):
    name: str
    category: str
    benefits: List[str] = Field(default_factory=list)
    proof_points: List[str] = Field(default_factory=list)
    do_not_claim: List[str] = Field(default_factory=list)


class ToneOfVoice(BaseModel):
    brand_traits: List[str] = Field(default_factory=list)
    writing_rules: List[str] = Field(default_factory=list)
    things_to_avoid: List[str] = Field(default_factory=list)
    sample_phrases: List[str] = Field(default_factory=list)


class ContentPillar(BaseModel):
    pillar_name: str
    goal: str
    description: str
    example_angles: List[str] = Field(default_factory=list)
    allowed_formats: List[str] = Field(default_factory=list)


class ApprovedCTA(BaseModel):
    objective: str
    cta_text: str
    notes: str | None = None


class ApprovalFlow(BaseModel):
    content_owner: str
    approver: str
    approval_sla_hours: int
    public_post_requires_human_approval: bool
    comment_reply_requires_human_approval: bool
    escalation_rules: List[str] = Field(default_factory=list)


class BrandProfile(BaseModel):
    brand_id: str
    brand_name: str
    industry: str
    business_goal: str
    fanpage_goals: List[str]
    brand_summary: str
    usp: List[str] = Field(default_factory=list)
    target_audiences: List[TargetAudience] = Field(default_factory=list)
    products_services: List[ProductService] = Field(default_factory=list)
    tone_of_voice: ToneOfVoice
    content_pillars: List[ContentPillar] = Field(default_factory=list)
    approved_cta_patterns: List[ApprovedCTA] = Field(default_factory=list)
    banned_phrases: List[str] = Field(default_factory=list)
    compliance_notes: List[str] = Field(default_factory=list)
    approval_flow: ApprovalFlow


class PlanDay(BaseModel):
    date: str
    pillar: str
    objective: str
    topic: str
    angle: str
    format: str
    hook: str
    cta: str
    visual_brief: str
    risk_notes: List[str] = Field(default_factory=list)


class WeeklyPlan(BaseModel):
    plan_title: str
    days: List[PlanDay]
    strategy_notes: List[str] = Field(default_factory=list)
    gaps_or_assumptions: List[str] = Field(default_factory=list)


class CaptionVariant(BaseModel):
    label: str
    hook: str
    caption: str
    cta: str
    tone_tags: List[str] = Field(default_factory=list)
    visual_brief: str


class CaptionPackage(BaseModel):
    topic: str
    variants: List[CaptionVariant]
    dos: List[str] = Field(default_factory=list)
    donts: List[str] = Field(default_factory=list)


class PostHistoryEntry(BaseModel):
    published_at: str
    topic: str
    hook: str
    pillar: str
    objective: str
    permalink: str = ""
    reach: int = 0
    engagement_rate: float = 0.0


class PostMetric(BaseModel):
    published_at: str
    topic: str
    pillar: str
    objective: str
    reach: int = 0
    engagements: int = 0
    leads: int = 0

    @property
    def engagement_rate(self) -> float:
        if self.reach <= 0:
            return 0.0
        return self.engagements / self.reach


class CommentInboxEntry(BaseModel):
    id: str = ""
    post_id: str = ""
    created_at: str = ""
    source: str = ""
    message: str = ""


class TrendItem(BaseModel):
    title: str
    source: str
    url: str = ""
    snippet: str = ""
    relevance: str = ""


class ResearchSource(BaseModel):
    source_id: str
    name: str
    source_type: str = "website"
    url: str = ""
    topics: List[str] = Field(default_factory=list)
    trust_score: float = 0.5
    refresh_days: int = 7
    allowed_pages: List[str] = Field(default_factory=list)
    requires_auth: bool = False
    enabled: bool = True
    notes: str = ""


class SourceDocument(BaseModel):
    source_id: str
    source_name: str
    source_type: str = "website"
    url: str = ""
    title: str = ""
    content: str = ""
    published_at: str = ""
    fetched_at: str = ""
    trust_score: float = 0.5
    freshness_score: float = 0.0
    metadata: dict[str, object] = Field(default_factory=dict)


class SourceCandidate(BaseModel):
    source_id: str
    title: str = ""
    url: str = ""
    snippet: str = ""
    discovery_query: str = ""
    relevance_score: float = 0.0
    trust_score: float = 0.5
    status: str = "candidate"
    reason_codes: List[str] = Field(default_factory=list)


class ResearchEvidence(BaseModel):
    claim: str
    source: str
    url: str = ""
    evidence_type: str = "source"
    confidence: float = 0.0
    source_id: str = ""
    source_type: str = ""
    support_count: int = 1
    corroborating_sources: List[str] = Field(default_factory=list)


class ResearchTopicScore(BaseModel):
    topic: str
    total_score: float = 0.0
    brand_relevance: float = 0.0
    novelty: float = 0.0
    content_potential: float = 0.0
    source_confidence: float = 0.0
    fanpage_fit: float = 0.0
    duplication_risk: float = 0.0
    product_relevance: float = 0.0
    customer_value: float = 0.0
    risk_level: str = ""
    rationale: str = ""


class ResearchBrief(BaseModel):
    top_performing_topics: List[str] = Field(default_factory=list)
    overused_topics: List[str] = Field(default_factory=list)
    frequent_questions: List[str] = Field(default_factory=list)
    campaign_focus: List[str] = Field(default_factory=list)
    recommended_pillars: List[str] = Field(default_factory=list)
    recommended_objectives: List[str] = Field(default_factory=list)
    next_angles: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    external_trends: List[TrendItem] = Field(default_factory=list)
    trend_keywords: List[str] = Field(default_factory=list, description="Top keywords từ TrendAnalyzer")
    trend_clusters: dict[str, list[str]] = Field(default_factory=dict, description="Cluster tên + các title từ TrendAnalyzer")
    evidence: List[ResearchEvidence] = Field(default_factory=list)
    confidence_score: float = 0.0
    quality_warnings: List[str] = Field(default_factory=list)
    topic_scores: List[ResearchTopicScore] = Field(default_factory=list)
    source_documents: List[SourceDocument] = Field(default_factory=list)
    source_candidates: List[SourceCandidate] = Field(default_factory=list)


class ResearchPacket(BaseModel):
    packet_id: str
    job_id: str
    agent: str = "research"
    schema_version: str = "research_packet.v1"
    created_at: str
    status: str = "ready"
    gate_reasons: List[str] = Field(default_factory=list)
    handoff_policy: dict[str, object] = Field(default_factory=dict)
    page_id: str = ""
    page_context: dict[str, object] = Field(default_factory=dict)
    source_files: dict[str, str] = Field(default_factory=dict)
    brief: ResearchBrief


class AnalyticsSummary(BaseModel):
    total_posts: int
    total_reach: int
    total_engagements: int
    total_leads: int
    avg_engagement_rate: float


class AnalyticsReport(BaseModel):
    summary: AnalyticsSummary
    top_post: PostMetric | None = None
    top_posts: List[PostMetric] = Field(default_factory=list)
    wow: dict[str, float] = Field(default_factory=dict, description="Week-over-week % change: posts, reach, engagements, engagement_rate")
    pillar_breakdown: dict[str, dict[str, int]] = Field(default_factory=dict, description="Per pillar: count, reach, engagements")
    recommendations: List[str] = Field(default_factory=list)


class CommunityTriageItem(BaseModel):
    triage_id: str = ""
    created_at: str
    source: str
    message: str
    category: str
    priority: str
    recommended_action: str
    draft_reply: str = ""
    escalation_required: bool = False
    requires_human_approval: bool = True
    matched_rules: List[str] = Field(default_factory=list)


class CommunityTriageBatch(BaseModel):
    items: List[CommunityTriageItem] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    passed: bool
    issues: List[str] = Field(default_factory=list)
