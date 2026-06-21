# Research Agent Completion Status Tracking Implementation Plan

**For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) and superpowers:executing-plans to implement plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
**Goal:** Hoàn tất vòng đời roadmap/spec/plan của Research Agent và thêm evidence machine-readable để chứng minh trạng thái completion qua CLI status.
**Architecture:** Giữ research roadmap làm nguồn trạng thái cho agent này, sau đó trích logic parse roadmap trong `status_cli.py` thành helper nhận path/target để dùng cho cả product roadmap mặc định lẫn research roadmap. Cập nhật test theo TDD để khóa backward compatibility và research-specific reporting trước khi sửa implementation.
**Tech Stack:** Python 3.11, pytest, PowerShell, uv

---

### Task 1: Khóa behavior roadmap status cho research target bằng test

**Files:**

- Modify: `tests/test_audit.py`
- Test: `tests/test_audit.py`

- [ ] **Step 1: Write failing test**

```python
def test_roadmap_status_reads_research_agent_roadmap(self) -> None:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        _run_roadmap_status(roadmap_target="research")
    payload = json.loads(stdout.getvalue())
    self.assertEqual(payload["status"], "ok")
    self.assertTrue(payload["roadmap"].endswith("docs/roadmaps/agents/research-agent-roadmap.md"))
    self.assertIn("Research Agent Roadmap", payload["title"])
    self.assertGreaterEqual(payload["phases_total"], 5)
```

- [ ] **Step 2: Run test verify fails**

Run: `uv run python -m pytest -q tests\test_audit.py -k research_agent_roadmap --basetemp .pytest-tmp`

Expected: FAIL because `_run_roadmap_status()` does not accept `roadmap_target`.

- [ ] **Step 3: Write second failing compatibility test**

```python
def test_roadmap_status_default_still_reads_product_roadmap(self) -> None:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        _run_roadmap_status()
    payload = json.loads(stdout.getvalue())
    self.assertTrue(payload["roadmap"].endswith("docs/roadmaps/roadmap-next.md"))
```

- [ ] **Step 4: Run test verify first red remains valid**

Run: `uv run python -m pytest -q tests\test_audit.py -k "research_agent_roadmap or default_still_reads_product" --basetemp .pytest-tmp`

Expected: FAIL on research-target path only, default path still GREEN or unchanged.

### Task 2: Implement roadmap target selection in status CLI

**Files:**

- Modify: `fanpage_agent/status_cli.py`
- Modify: `fanpage_agent/runtime_cli/dispatcher.py`
- Test: `tests/test_audit.py`

- [ ] **Step 1: Implement minimal helper-based parser**

```python
def _resolve_roadmap_path(roadmap_target: str | None = None) -> Path:
    ...


def _run_roadmap_status(roadmap_target: str | None = None) -> None:
    roadmap_path = _resolve_roadmap_path(roadmap_target)
    ...
```

Behavior:

- `None` or `"product"` → `docs/roadmaps/roadmap-next.md`
- `"research"` → `docs/roadmaps/agents/research-agent-roadmap.md`
- output adds a `title` field from first markdown heading and a `roadmap_target` field

- [ ] **Step 2: Wire runtime parser/dispatcher**

```python
parser.add_argument(
    "--roadmap-target",
    choices=["product", "research"],
    default="product",
    help="Roadmap target for roadmap-status",
)
...
if args.action == "roadmap-status":
    _run_roadmap_status(roadmap_target=args.roadmap_target)
```

- [ ] **Step 3: Run targeted tests verify passes**

Run: `uv run python -m pytest -q tests\test_audit.py -k "research_agent_roadmap or default_still_reads_product" --basetemp .pytest-tmp`

Expected: PASS.

### Task 3: Cập nhật research roadmap thành current-state record đúng

**Files:**

- Modify: `docs/roadmaps/agents/research-agent-roadmap.md`

- [ ] **Step 1: Update roadmap text**

Edit roadmap so that:

- `Current State` phản ánh shared handoff adapter đã tồn tại,
- Phase 1-5 được đánh dấu `— Done`,
- mỗi phase giữ outcome/scope ngắn gọn nhưng không còn mô tả như backlog mở,
- phần cuối đổi từ `First Implementation Target` sang completion note hoặc next recommended focus phù hợp với current state.

- [ ] **Step 2: Self-check roadmap against evidence**

Verify every claimed done phase has direct support from current tests or CLI:

- Phase 1-3 → `tests/test_research_handoff.py`, `tests/test_agents.py`
- Phase 4 → `tests/test_research_cli.py`, `tests/test_daily_ops.py`
- Phase 5 → `tests/test_multi_page.py`, `tests/test_research_cli.py`

No command here; this is a file-content audit before next test.

### Task 4: Lock research roadmap parsing expectations with tests

**Files:**

- Modify: `tests/test_audit.py`
- Test: `tests/test_audit.py`

- [ ] **Step 1: Write failing test for research roadmap phase status**

```python
def test_roadmap_status_research_reports_completed_phases(self) -> None:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        _run_roadmap_status(roadmap_target="research")
    payload = json.loads(stdout.getvalue())
    done_phases = [item["phase"] for item in payload["phase_statuses"] if item["status"] == "done"]
    self.assertIn("Phase 1: Contract Stabilization", done_phases)
    self.assertIn("Phase 5: Multi-Page Governance", done_phases)
```

- [ ] **Step 2: Run test verify fails**

Run: `uv run python -m pytest -q tests\test_audit.py -k completed_phases --basetemp .pytest-tmp`

Expected: FAIL before roadmap text and parser semantics align.

- [ ] **Step 3: Implement minimal parsing support for done phases**

If needed, extend parser to recognize `## Phase X: ... — Done` and mark those phase sections as done independently of task text completion.

- [ ] **Step 4: Run targeted tests verify passes**

Run: `uv run python -m pytest -q tests\test_audit.py -k "research_agent_roadmap or completed_phases or default_still_reads_product" --basetemp .pytest-tmp`

Expected: PASS.

### Task 5: Verify research completion end-to-end

**Files:**

- Test: `tests/test_audit.py`
- Test: `tests/test_research_handoff.py`
- Test: `tests/test_agents.py`
- Test: `tests/test_research_cli.py`
- Test: `tests/test_daily_ops.py`
- Test: `tests/test_multi_page.py`

- [ ] **Step 1: Run focused research verification**

Run: `uv run python -m pytest -q tests\test_audit.py tests\test_research_handoff.py tests\test_agents.py tests\test_research_cli.py tests\test_daily_ops.py tests\test_multi_page.py --basetemp .pytest-tmp`

Expected: PASS.

- [ ] **Step 2: Smoke CLI for both roadmap targets**

Run: `uv run python -m fanpage_agent.main roadmap-status`

Expected: JSON payload with `"roadmap_target": "product"` and `"status": "ok"`.

Run: `uv run python -m fanpage_agent.main roadmap-status --roadmap-target research`

Expected: JSON payload with `"roadmap_target": "research"` and roadmap path ending in `docs/roadmaps/agents/research-agent-roadmap.md`.

- [ ] **Step 3: Run full suite**

Run: `uv run python -m pytest -q --basetemp .pytest-tmp`

Expected: PASS.
