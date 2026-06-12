# Strategist Agent Upgrade Roadmap

## Goal

Upgrade Strategist Agent from a simple content planner into an evidence-aware editor-in-chief.
It must decide what should be written, what should be paused, and how Writer should safely use ResearchPacket output.

## Operating Rule

Each phase must pass targeted tests and the full suite before commit and push. If tests fail, pause the roadmap, fix the failure, rerun tests, then continue.

## Phase 1: Evidence-Aware Strategy Brief

Outcome: Strategist understands ResearchPacket and Evidence Gate before choosing a topic.

Scope:
- Read handoff policy from ResearchPacket.
- Avoid blocked topics as public post candidates.
- Mark needs-review topics as human-review only.
- Add explicit evidence status, risk level, and safe-use instruction to StrategyBrief.
- Produce research follow-up questions when evidence is weak.

Acceptance tests:
- Ready affiliate topic can become a content brief.
- Blocked affiliate topic cannot become a public writing brief.
- Needs-review topic remains usable only with human review.
- Non-affiliate educational topic is not over-blocked.

## Phase 2: Angle Selection

Outcome: Strategist chooses the safest and most useful angle, not just the highest score.

Scope:
- Classify content angle: education, checklist, buying guide, comparison, myth-busting, cautionary post.
- Prefer education/checklist when evidence is moderate.
- Allow buying-guide/recommendation only when evidence is strong.
- Add audience pain point and promise boundaries.

Acceptance tests:
- Low evidence produces checklist/research angle, not recommendation.
- Affiliate offer with good evidence produces guarded buying guide.
- Repeated topic is redirected to a fresher angle.

## Phase 3: Variant Scoring

Outcome: Strategist proposes multiple brief variants and picks the best one before Writer drafts.

Scope:
- Generate 2-3 strategy variants.
- Score variants by evidence strength, page fit, novelty, risk, and CTA safety.
- Output selected variant plus rejected reasons.

Acceptance tests:
- Risky sales-heavy variant loses to safer education/checklist variant.
- High evidence and clear disclosure can support stronger CTA.
- Strategy output remains deterministic in tests.

## Phase 4: Feedback-Aware Strategy

Outcome: Strategist starts using Analyst/feedback signals once enough data exists.

Scope:
- Read post performance summary, comments, frequent questions, and campaign notes.
- Prefer topics with proven engagement and unresolved customer questions.
- Avoid formats that underperform repeatedly.

Acceptance tests:
- Frequent customer question increases priority.
- Poor historical format lowers priority.
- Missing feedback data falls back safely to ResearchPacket only.

## Phase 5: Approval-Ready Strategy Packet

Outcome: Human approver sees why a post is being proposed before approving Writer output.

Scope:
- Include why-this-topic, evidence summary, safe claims, forbidden claims, CTA policy, and review notes.
- Make Telegram preview clearer: approve, revise, add sources, or skip.
- Keep human approval mandatory.

Acceptance tests:
- Approval packet exposes evidence/risk clearly.
- Blocked strategy never offers direct approve action.
- Revision path preserves evidence warnings.

## First Implementation Target

Start with Phase 1 because Evidence Gate already exists and the next gap is Strategist using it before Writer receives a brief.
