# CLI Boundary Cleanup Implementation Plan

**For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
**Goal:** Decouple shared CLI constants/helpers from compatibility layers while preserving current CLI behavior.
**Architecture:** Add one shared module for CLI-common paths and parser helpers, then route `fanpage_agent.main` and `fanpage_cli/*` to that module or directly to `fanpage_agent.cli_commands` for business helpers. Keep compatibility exports in place.
**Tech Stack:** Python 3.11, argparse, pytest, uv

---

### Task 1: Lock the desired import boundaries with tests

**Files:**
- Create: `tests/test_cli_boundaries.py`

- [ ] **Step 1: Write failing test**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_main_does_not_import_legacy_cli() -> None:
    assert "from fanpage_agent.legacy_cli import" not in read("fanpage_agent/main.py")


def test_public_cli_modules_do_not_pull_shared_constants_from_main() -> None:
    for path in [
        "fanpage_cli/approval.py",
        "fanpage_cli/deliver.py",
        "fanpage_cli/ops.py",
        "fanpage_cli/plan.py",
        "fanpage_cli/triage.py",
    ]:
        assert "from fanpage_agent.main import" not in read(path)
```

- [ ] **Step 2: Run test and verify it fails**

Run: `uv run python -m pytest tests/test_cli_boundaries.py -q --basetemp .pytest-tmp`
Expected: FAIL because current files still import from `fanpage_agent.main` and `fanpage_agent.legacy_cli`.

- [ ] **Step 3: Write minimal implementation**

```python
# fanpage_agent/cli_common.py
# move shared constants and parser helper here

# fanpage_agent/main.py
# import shared constants/helper from cli_common

# fanpage_cli/*.py
# import shared constants/helper from cli_common
# import payload helpers from fanpage_agent.cli_commands
```

- [ ] **Step 4: Run test and verify it passes**

Run: `uv run python -m pytest tests/test_cli_boundaries.py -q --basetemp .pytest-tmp`
Expected: PASS

### Task 2: Verify compatibility still holds

**Files:**
- Modify: `fanpage_agent/main.py`
- Modify: `fanpage_agent/legacy_cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Run focused regression test**

```bash
uv run python -m pytest tests/test_cli.py -q --basetemp .pytest-tmp
```

- [ ] **Step 2: If needed, re-export shared constants from `fanpage_agent.main`**

```python
from fanpage_agent.cli_common import DEFAULT_CALENDAR_FILE, ROOT_DIR, add_store_backend_arg
```

- [ ] **Step 3: Re-run focused regression test**

```bash
uv run python -m pytest tests/test_cli.py -q --basetemp .pytest-tmp
```

- [ ] **Step 4: Run CLI verification commands**

```bash
uv run fanpage-agent --help
uv run python -m fanpage_agent.main roadmap-status
```

- [ ] **Step 5: Run lint for touched files**

```bash
uv run ruff check fanpage_agent fanpage_cli tests
```
