# ADR 0001: Use Adapter Layer For External Providers

## Status

Accepted

## Date

2026-06-21

## Context

`fanpage-agent` integrates with external systems that differ in authentication,
API shape, pagination, retries, and error behavior. The repository already
shows this pressure through modules such as `fanpage_agent/adapters/`,
affiliate provider implementations, and agent workflows that consume provider
results.

If agents or domain services call provider-specific clients directly, the code
base becomes coupled to vendor-specific request and response details. That makes
tests less deterministic, provider replacement more expensive, and approval or
audit flows harder to enforce consistently across integrations.

The project also needs to support a mock or local provider path for tests and
safe local development. That is easier when integration boundaries are explicit.

## Decision

All external providers and service integrations must be accessed through an
adapter layer with a narrow, domain-oriented interface.

New business logic should depend on adapter interfaces or adapter-facing
services, not on raw provider SDK calls or vendor-specific HTTP details.
Provider-specific authentication, payload translation, retries, and response
normalization belong inside adapters.

Tests should prefer mock, fake, or local adapter implementations over live
provider calls unless a test is explicitly scoped as an integration test.

## Options Considered

### Option A: Call providers directly from agents and domain workflows

This keeps the first implementation short, but it spreads provider knowledge
throughout the codebase. It increases the cost of changing vendors and makes
tests depend on vendor behavior or fragile mocks around low-level clients.

### Option B: Use a generic service layer without explicit adapter boundaries

This reduces some duplication, but it still tends to leak vendor-specific
details into calling code unless the boundary is defined carefully. In practice,
it often becomes a thin pass-through rather than a stable integration contract.

### Option C: Standardize on explicit adapters for external providers

This adds a small amount of abstraction and mapping code, but it creates a
clear seam for test doubles, provider swaps, multi-provider support, and
consistent error handling.

## Consequences

Positive consequences:

- Domain logic stays closer to project concepts than vendor concepts.
- Provider swaps or additions become more localized.
- Mock and local provider paths are easier to maintain.
- Error handling and audit behavior can be standardized at integration
  boundaries.

Negative consequences:

- New integrations require extra wrapper code and interface design.
- Some provider features may need explicit translation before they are usable.
- Poorly designed adapters can become over-generalized if they try to hide too
  much provider behavior.

## Follow-up

- Keep new external integrations under `fanpage_agent/adapters/` or another
  clearly bounded adapter package.
- Prefer adapter-focused tests that validate translation and failure behavior.
- Avoid adding vendor-specific logic to agents, root modules, or CLI entry
  points.
