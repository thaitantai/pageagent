# ADR 0003: Define Durable State And Audit Trail Boundaries

## Status

Accepted

## Date

2026-06-21

## Context

`fanpage-agent` already produces multiple classes of runtime information:
operational state, approval and publishing status, memory or performance data,
logs, and generated artifacts. These data classes do not have the same purpose
or lifecycle.

If the project treats logs, artifacts, and runtime state interchangeably, the
system becomes harder to debug and reason about. Operators may not know which
record is authoritative, and future automation may read stale files as if they
were the source of truth.

The project needs a stable distinction between durable state that drives
workflow decisions and supporting records that exist only for debugging, audit,
or human inspection.

## Decision

The project will distinguish durable workflow state from audit records, logs,
and generated artifacts.

Durable state is the data used to make workflow decisions such as approval
status, publish status, and other records that determine what the system is
allowed to do next. Audit records exist to explain what happened. Logs exist to
help debug runtime behavior. Artifacts exist as outputs for review or reporting.

Logs and artifacts are not sources of truth for workflow state. They may mirror
or summarize durable state, but they do not define it.

When new features add stateful behavior, they must identify:

- what record is authoritative,
- where that record lives,
- which fields are decision-driving,
- and which generated outputs are only observational.

## Options Considered

### Option A: Let each feature infer state from logs or artifacts

This keeps initial implementation loose, but it makes behavior fragile and
creates conflicting interpretations when data diverges.

### Option B: Use a single flat record store for everything

This reduces ambiguity about storage location, but it blurs the semantic
difference between operational state and supporting telemetry unless boundaries
are still defined clearly.

### Option C: Separate durable state from audit, logs, and artifacts

This requires more disciplined modeling, but it makes workflow decisions,
reporting, and debugging easier to understand and extend.

## Consequences

Positive consequences:

- Workflow behavior becomes easier to reason about and test.
- Audit output can evolve without changing decision logic.
- Debug logs can be rotated or reformatted without redefining application state.

Negative consequences:

- New features must explicitly model state instead of writing ad hoc files.
- Some existing commands may need clearer terminology to distinguish state from
  output.
- Data migrations become more deliberate when authoritative fields change.

## Follow-up

- Prefer naming that distinguishes state, logs, and artifacts clearly.
- Document authoritative storage locations when new workflow states are added.
- Avoid implementing control flow that depends on parsing human-oriented logs.
