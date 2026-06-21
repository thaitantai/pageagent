# CLI Boundary Cleanup Spec

## Goal

Reduce coupling between the public CLI, the package entrypoint, and legacy compatibility shims without changing user-facing CLI behavior.

## Scope

This phase only cleans import boundaries.

- Keep `fanpage_cli/` as the public CLI entry layer.
- Keep `fanpage_agent/legacy_cli.py` as a compatibility shim.
- Stop using `fanpage_agent.main` as a bucket of shared CLI constants/helpers for `fanpage_cli/*`.
- Stop having `fanpage_agent.main` depend directly on `fanpage_agent.legacy_cli`.

This phase does not rename commands, move business logic, or remove compatibility exports.

## Design

Introduce one small shared module under `fanpage_agent/` that owns CLI-common paths, cron metadata, and parser helpers such as `add_store_backend_arg`.

Import rules after the change:

- `fanpage_cli/*` imports shared constants/helpers from the new shared module.
- `fanpage_cli/*` imports workflow/payload helpers directly from `fanpage_agent.cli_commands` where needed.
- `fanpage_agent.main` imports shared constants/helpers from the new shared module.
- `fanpage_agent.legacy_cli` remains a thin re-export shim to `fanpage_agent.cli_commands`.

Compatibility remains intact by re-exporting the shared constants/helpers from `fanpage_agent.main`.

## Testing

Add structural tests that assert:

- `fanpage_agent.main` no longer imports `fanpage_agent.legacy_cli`.
- targeted `fanpage_cli/*` modules no longer import shared constants/helpers from `fanpage_agent.main`.

Then run focused pytest coverage for the new boundary tests and smoke tests for the CLI entrypoints already used in this repo.
