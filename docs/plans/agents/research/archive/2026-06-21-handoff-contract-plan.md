# Research Agent Handoff Implementation Plan
**For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) superpowers:executing-plans implement plan task-by-task. Steps use checkbox (`- [ ]`) syntax tracking.
**Goal:** Chuẩn hóa downstream handoff của Research Agent để Strategist và Writer dùng cùng một contract khi đọc research output.
**Architecture:** Thêm một adapter nhỏ `research_handoff.py` đứng giữa `ResearchPacket` và downstream consumers. Strategist và Writer đọc contract đã normalize thay vì tự bóc raw packet. Giữ tương thích với `research_brief` legacy.
**Tech Stack:** Python 3.11, dataclasses hoặc typed dict nhẹ, pytest
---

### Task 1: Lock handoff contract bằng unit test
**Files:**
- Create: `tests/test_research_handoff.py`
- [ ] **Step 1: Write failing test**

```python
from fanpage_agent.research_handoff import normalize_research_handoff


def test_normalize_ready_packet_exposes_shared_fields() -> None:
    packet = {
        "packet_id": "rpkt-1",
        "status": "ready",
        "handoff_policy": {"max_safe_use": "public_draft"},
        "page_context": {"page_id": "main", "topic_focus": "soi da"},
        "brief": {
            "confidence_score": 0.82,
            "topic_scores": [{"topic": "Khi nào nên soi da?", "total_score": 0.91}],
            "evidence": [{"claim": "A", "source": "FAQ", "url": "https://example.com/a", "confidence": 0.8}],
        },
    }
    result = normalize_research_handoff(packet)
    assert result["packet_id"] == "rpkt-1"
    assert result["safe_use"] == "public_draft"
    assert result["priority_topics"][0]["topic"] == "Khi nào nên soi da?"
    assert result["evidence_refs"][0]["source"] == "FAQ"
```

- [ ] **Step 2: Run test verify fails**
Run: `.\.venv\Scripts\pytest.exe tests\test_research_handoff.py -q`
Expected: FAIL because module/function does not exist yet.

### Task 2: Implement shared handoff adapter
**Files:**
- Create: `fanpage_agent/research_handoff.py`
- Test: `tests/test_research_handoff.py`
- [ ] **Step 1: Write minimal implementation**

```python
def normalize_research_handoff(packet: dict | None) -> dict[str, object]:
    ...
```

Implementation must:
- unwrap `brief` when present,
- preserve `packet_id`, `status`, `page_context`, `gate_reasons`,
- derive `safe_use` from `handoff_policy.max_safe_use`,
- expose `confidence_score`, `priority_topics`, `blocked_topics`, `evidence_refs`, `findings`, `quality_warnings`,
- support legacy shape without `brief`.

- [ ] **Step 2: Run test verify passes**
Run: `.\.venv\Scripts\pytest.exe tests\test_research_handoff.py -q`
Expected: PASS.

### Task 3: Move Strategist onto the shared adapter
**Files:**
- Modify: `fanpage_agent/agents/strategist.py`
- Modify: `tests/test_agents.py`
- [ ] **Step 1: Write failing regression test**

```python
def test_plan_weekly_uses_shared_research_handoff_for_packet_shape(self, agent):
    ...
```

Assert Strategist still:
- prioritizes ready topics,
- blocks `draft_questions_only`,
- keeps `page_context`,
- exposes evidence status.

- [ ] **Step 2: Run targeted test verify fails**
Run: `.\.venv\Scripts\pytest.exe tests\test_agents.py -q`
Expected: FAIL on Strategist path until adapter integration is wired.

- [ ] **Step 3: Implement minimal integration**
Use `normalize_research_handoff()` inside Strategist to replace shared parsing logic.

- [ ] **Step 4: Run targeted test verify passes**
Run: `.\.venv\Scripts\pytest.exe tests\test_agents.py -q`
Expected: PASS.

### Task 4: Move Writer onto the shared adapter
**Files:**
- Modify: `fanpage_agent/agents/writer.py`
- Modify: `tests/test_agents.py`
- [ ] **Step 1: Write failing regression test**

```python
def test_write_variants_uses_shared_handoff_evidence_refs(self, agent):
    ...
```

Assert Writer:
- reads normalized evidence refs,
- blocks public-claim path for `draft_questions_only`,
- preserves `research_packet_id`.

- [ ] **Step 2: Run targeted test verify fails**
Run: `.\.venv\Scripts\pytest.exe tests\test_agents.py -q`
Expected: FAIL until Writer integration is updated.

- [ ] **Step 3: Implement minimal integration**
Use `normalize_research_handoff()` in Writer for shared fields/evidence refs.

- [ ] **Step 4: Run targeted test verify passes**
Run: `.\.venv\Scripts\pytest.exe tests\test_agents.py -q`
Expected: PASS.

### Task 5: Verify CLI-facing regressions
**Files:**
- Test: `tests/test_research_cli.py`
- Test: `tests/test_daily_ops.py`
- [ ] **Step 1: Run focused verification**
Run: `.\.venv\Scripts\pytest.exe tests\test_research_handoff.py tests\test_agents.py tests\test_research_cli.py tests\test_daily_ops.py -q`
Expected: PASS.

- [ ] **Step 2: Smoke package CLI if dispatcher touched again**
Run: `.\.venv\Scripts\python.exe -m fanpage_agent.main roadmap-status`
Expected: JSON payload with `"status": "ok"`.
