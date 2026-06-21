# Architecture Decision Records

This directory records architectural decisions that shape how `fanpage-agent`
is extended and maintained.

## Purpose

ADR files capture decisions that have long-term design impact. Each ADR explains
the context, the chosen direction, the alternatives considered, and the
consequences that follow from the decision.

## Status Values

- `Accepted`: The decision is active and should guide new work.
- `Superseded`: A newer ADR has replaced this one.
- `Deprecated`: The decision still exists in history but should not guide new work.
- `Proposed`: The decision is under discussion and not yet the repo default.

## Numbering

ADRs are numbered in the order they are accepted. Keep the existing number even
if the title or details change later.

## When To Add An ADR

Add an ADR when a change affects one or more of these boundaries:

- How the system integrates with external providers or services
- How approval, publishing, or other safety boundaries are enforced
- Where durable state lives and what counts as source of truth
- Which modules are compatibility surfaces versus domain logic entry points

## Current ADRs

- [ADR 0001: Use Adapter Layer For External Providers](./0001-use-adapter-layer-for-external-providers.md)
- [ADR 0002: Require Approval Before Publishing](./0002-require-approval-before-publishing.md)
- [ADR 0003: Define Durable State And Audit Trail Boundaries](./0003-define-durable-state-and-audit-trail-boundaries.md)
- [ADR 0004: Keep Root Compatibility Surfaces Thin](./0004-keep-root-compatibility-surfaces-thin.md)
