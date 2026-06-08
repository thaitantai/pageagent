"""Importable runtime package for Fanpage Agent.

The package contains code, schemas, adapters, services, agents, and packaged
static resources only. Mutable runtime data belongs in project-level `data/`
or `artifacts/`, not under `fanpage_agent/`.
"""

__all__ = [
    "adapters",
    "agents",
    "audit",
    "core",
    "loaders",
    "memory",
    "models",
    "ops",
    "scraping",
    "tools",
]
