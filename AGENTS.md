# Repository Guidelines

## Project Structure & Module Organization

Application code lives in `fanpage_agent/`, organized into focused packages such as `agents/`, `core/`, `memory/`, `ops/`, and `tools/`; CLI commands belong in `cli_commands/`. `fanpage_cli/` provides the installed entry point, while root modules such as `agent.py` remain compatibility surfaces. Tests live in `tests/` and mirror features with `test_<feature>.py`. Scripts are in `scripts/`, documentation in `docs/`, local inputs in `data/` and `brand_profiles/`, and generated output in `artifacts/` or `logs/`.

## Documentation Entry Points

Before changing behavior or adding capabilities, follow the repo doc entrypoints in this order:

1. Read `docs/roadmaps/roadmap-next.md` for product-level phase priority.
2. If the work is agent-specific, read `docs/roadmaps/agents/README.md` and the relevant agent roadmap.
3. Read the matching file under `docs/specs/.../active/` for the current behavior/boundaries source of truth.
4. Read the matching file under `docs/plans/.../active/` for execution tasks, touched modules/files, and verification.
5. Use `docs/operations/doc-taxonomy.md` when deciding where new docs belong or whether a file should stay `active` or move to `archive`.

Rules:

- Do not implement directly from roadmap alone.
- Use `spec active` to decide what behavior must be true.
- Use `plan active` to decide which modules/files to change.
- If a significant capability change has no active spec/plan yet, create them first.

## Build, Test, Development Commands

Use Python 3.11 and `uv`; CI runs the following workflow:

- `uv sync --locked --dev` installs exact runtime and development dependencies.
- `uv run ruff format --check .` verifies formatting; omit `--check` to apply it.
- `uv run ruff check .` runs import and lint checks.
- `uv run python -m pytest -q --basetemp .pytest-tmp` runs the default test suite.
- `uv run fanpage-agent --help` checks the installed CLI entry point.
- `uv run python -m fanpage_agent.main roadmap-status` checks the package CLI path.

Tests marked `slow` are skipped by default. Run them with `uv run pytest -m slow` when needed.

## Coding Style & Naming Conventions

Use four-space indentation, Python 3.11 syntax, and a 100-character line target. Ruff enforces `E`, `F`, and `I` rules. Use `snake_case` for modules, functions, variables, and CLI files; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Keep provider behavior behind adapters and new domain logic out of root compatibility modules.

## Testing Guidelines

Use Pytest. Name files `test_<subject>.py` and functions `test_<behavior>`. Add focused tests for every behavior change, including failure paths and CLI parsing. No coverage threshold is configured.

## Security & Configuration

Copy `.env.example` to `.env` for local configuration. Never commit API keys, tokens, service-account files, live page data, or generated logs. Prefer the mock-local provider for deterministic tests.
