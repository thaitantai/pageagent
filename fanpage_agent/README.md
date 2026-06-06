# `fanpage_agent` Package

`fanpage_agent/` is the importable Python package for the agent runtime. It should contain code, schemas, and packaged static resources only. It must not contain live runtime data, generated outputs, local databases, credentials, or operator CSV files.

## Package Roles

```text
fanpage_agent/
├── adapters/      # Boundary clients for external systems: Facebook, LLMs, Sheets, Telegram, stores
├── agents/        # Autonomous role agents: researcher, strategist, writer, designer, publisher, community, analyst
├── audit/         # Audit event persistence and querying
├── core/          # Agent base classes, bus, harness, shared runtime types
├── loaders/       # Small input loaders, e.g. brand profile parsing
├── memory/        # PerformanceMemory and restore/snapshot logic
├── ops/           # Operator/runtime health and SLA helpers
├── scraping/      # Search, trend scraping, and trend analysis helpers
├── services/      # Business workflows used by CLI/agents: planning, triage, analytics, delivery, research
├── main.py        # Main argparse CLI for the package runtime
├── manager_cli.py # Operator manager CLI
├── models.py      # Shared Pydantic/domain models
└── throttle.py    # Rate-limit helpers
```

## Runtime Data Boundary

Use project-level folders for mutable data:

```text
data/          # local/runtime DBs, state, live inputs, snapshots; ignored by Git
artifacts/     # generated reports, briefs, previews, and packets; ignored by Git
```

Do not create these under `fanpage_agent/`:

```text
fanpage_agent/data/
fanpage_agent/artifacts/
*.db
*.db-shm
*.db-wal
.env
.env.*
*encoded-*.json
```

If the package ever needs static resources, keep them read-only, non-secret, small, and documented as package resources. Runtime code should write to `data/` or `artifacts/`, never into this package directory.

## Legacy Compatibility

Some top-level modules still exist for backward compatibility (`agent.py`, `config.py`, `tools.py`, `scheduler.py`, `cli.py`). Package shims under `fanpage_agent/agent/` and `fanpage_agent/config.py` re-export pieces from those modules. New code should prefer package imports and keep new runtime logic inside `fanpage_agent/`.
