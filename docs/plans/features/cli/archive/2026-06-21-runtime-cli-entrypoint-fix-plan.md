# Runtime CLI Entrypoint Fix Implementation Plan
**For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) superpowers:executing-plans implement plan task-by-task. Steps use checkbox (`- [ ]`) syntax tracking.
**Goal:** Khôi phục `python -m fanpage_agent.main roadmap-status` bằng cách cho runtime dispatcher fallback sang entrypoint CLI mới thay vì compatibility symbol đã mất.
**Architecture:** Giữ nguyên tách lớp hiện tại: `fanpage_agent.main` chỉ gọi `fanpage_agent.runtime_cli.dispatcher.cli`, còn dispatcher quyết định khi nào chạy runtime actions và khi nào hand off sang public CLI entrypoint. Sửa thêm đường dẫn roadmap trong `status_cli` để smoke command trả về dữ liệu thật từ `docs/roadmaps/roadmap-next.md`.
**Tech Stack:** Python 3.11, argparse, unittest, subprocess
---

### Task 1: Lock failing CLI behavior
**Files:**
- Modify: `tests/test_audit.py`
- [ ] **Step 1: Write failing test**

```python
def test_roadmap_status_cli_runs_through_runtime_dispatcher(self) -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "fanpage_agent.main", "roadmap-status"],
        cwd=root,
        env=isolated_subprocess_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    self.assertEqual(payload["status"], "ok")
    self.assertTrue(payload["roadmap"].endswith("docs/roadmaps/roadmap-next.md"))
```

- [ ] **Step 2: Run test verify fails**
Run: `.\.venv\Scripts\pytest.exe tests\test_audit.py -q`
Expected: FAIL with import/runtime error from `fanpage_agent.runtime_cli.dispatcher` trying to use missing legacy entrypoint.

### Task 2: Route dispatcher to the new public CLI entrypoint
**Files:**
- Modify: `fanpage_agent/runtime_cli/dispatcher.py`
- [ ] **Step 1: Write minimal implementation**

```python
from fanpage_agent.cli_commands.main import main as public_cli_main


def cli() -> None:
    if len(sys.argv) > 1 and sys.argv[1] not in RUNTIME_ACTIONS:
        raise SystemExit(public_cli_main())
```

- [ ] **Step 2: Run test verify passes**
Run: `.\.venv\Scripts\pytest.exe tests\test_audit.py -q`
Expected: roadmap CLI test reaches JSON output instead of import error.

### Task 3: Fix roadmap source path and verify smoke commands
**Files:**
- Modify: `fanpage_agent/status_cli.py`
- [ ] **Step 1: Point roadmap status at the current docs location**

```python
roadmap_path = ROOT_DIR / "docs" / "roadmaps" / "roadmap-next.md"
```

- [ ] **Step 2: Re-run focused verification**
Run: `.\.venv\Scripts\pytest.exe tests\test_audit.py -q`
Expected: PASS, including roadmap path assertion.

- [ ] **Step 3: Run CLI smoke command**
Run: `.\.venv\Scripts\python.exe -m fanpage_agent.main roadmap-status`
Expected: JSON payload with `"status": "ok"` and `"roadmap"` ending in `docs/roadmaps/roadmap-next.md`.
