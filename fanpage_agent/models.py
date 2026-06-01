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
    created_at: str
    source: str
    message: str


class ResearchBrief(BaseModel):
    top_performing_topics: List[str] = Field(default_factory=list)
    overused_topics: List[str] = Field(default_factory=list)
    frequent_questions: List[str] = Field(default_factory=list)
    campaign_focus: List[str] = Field(default_factory=list)
    recommended_pillars: List[str] = Field(default_factory=list)
    recommended_objectives: List[str] = Field(default_factory=list)
    next_angles: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class AnalyticsSummary(BaseModel):
    total_posts: int
    total_reach: int
    total_engagements: int
    total_leads: int
    avg_engagement_rate: float


class AnalyticsReport(BaseModel):
    summary: AnalyticsSummary
    top_post: PostMetric | None = None
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
