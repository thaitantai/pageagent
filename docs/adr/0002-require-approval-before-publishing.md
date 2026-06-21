# ADR 0002: Require Approval Before Publishing

## Status

Accepted

## Date

2026-06-21

## Context

The repository already contains approval-oriented behavior such as approval
audit reporting, rejection flows, and publisher logic that distinguishes content
state from final publishing. This indicates that human review is part of the
operating model rather than an optional convenience.

Publishing content to live pages has a higher risk profile than generating or
staging content. An incorrect caption, wrong product link, or mis-targeted page
publish can create brand damage that is hard to roll back. The cost of a review
step is lower than the cost of an unintended live post.

Without an explicit boundary, future work can accidentally bypass approval in
the name of convenience, especially when new CLI commands or automation paths
are introduced.

## Decision

Publishing to a live destination requires an explicit approval state transition
before the publish action is allowed to proceed.

Content generation, enrichment, and staging may be automated. Live publishing
must consume approved content or an explicitly approved publish request. Any
workflow that can reject or audit content must treat approval status as a first-
class input, not as an optional annotation.

Direct publish shortcuts are not the default architecture. If a future workflow
requires bypass behavior, it must be explicit, narrow in scope, and documented
with a new ADR or a clear amendment to this one.

## Options Considered

### Option A: Full autopilot publishing by default

This minimizes operational delay, but it increases the risk of publishing low-
quality, incorrect, or unsafe content without a clear human checkpoint.

### Option B: Approval only for selected high-risk content

This can work in mature systems with strong content classification and trust
signals, but it creates ambiguity early in the project and encourages exception
paths before the core workflow is stable.

### Option C: Approval required before live publishing

This adds a deliberate gate, but it gives the project a clear safety boundary
that matches the existing audit and rejection features.

## Consequences

Positive consequences:

- The system has a clear safety boundary before irreversible external actions.
- Approval, rejection, and audit tooling remain coherent.
- Operators can reason about pending versus approved versus rejected content.

Negative consequences:

- Publishing latency increases because a review step is required.
- Automation flows must manage approval states and stale pending items.
- Test coverage must include approval status handling, not only publish success.

## Follow-up

- Keep publish commands and publisher logic aligned with approval state checks.
- Extend tests whenever a new publish path or approval state is introduced.
- Document any future exception path explicitly instead of hiding it in a flag
  or side effect.
