# ADR 0004: Keep Root Compatibility Surfaces Thin

## Status

Accepted

## Date

2026-06-21

## Context

The repository contains both package-based application code and root-level
compatibility surfaces such as legacy import paths or broad entry modules.
Those compatibility surfaces help preserve existing invocation paths, but they
also create a risk: new logic may accumulate in the most visible entry points
instead of in focused package modules.

This risk is especially visible when root modules are imported by CLI commands
or compatibility entry points. A broad import surface can make unrelated
commands fail earlier than expected if root-level dependencies drift or become
too coupled.

The codebase needs a clear rule for what belongs in compatibility surfaces and
what belongs in package modules.

## Decision

Root-level compatibility surfaces will be kept thin. Their role is limited to
backward-compatible exports, command dispatch, or shallow wiring into package
modules.

New domain logic, orchestration, provider-specific behavior, and storage logic
must live in focused modules under the main package structure rather than in
root compatibility modules. Root surfaces may adapt old import paths to the new
structure, but they should not become the primary home of new behavior.

## Options Considered

### Option A: Continue placing new logic in whichever entry point is most
convenient

This is fast in the moment, but it increases coupling and makes import-time
failures more likely. It also weakens package boundaries over time.

### Option B: Remove compatibility surfaces immediately

This would simplify the long-term shape of the codebase, but it risks breaking
existing commands, scripts, or integrations before the migration is complete.

### Option C: Keep compatibility surfaces, but keep them thin

This preserves current entry points while still moving the real design center
into package modules where responsibilities are easier to test and evolve.

## Consequences

Positive consequences:

- Package structure remains the primary place for real application behavior.
- Compatibility entry points stay easier to review and maintain.
- Import-time regressions become easier to localize.

Negative consequences:

- Engineers need discipline to avoid taking shortcuts in root modules.
- Some refactoring work may be required when existing root modules still contain
  too much logic.
- Compatibility layers remain as a temporary maintenance cost until migration
  pressure drops.

## Follow-up

- Treat root modules as adapters into package code, not as feature homes.
- When touching broad entry modules, prefer extracting new logic into focused
  package modules first.
- Add or update tests when compatibility surfaces are changed so existing entry
  paths remain stable.
