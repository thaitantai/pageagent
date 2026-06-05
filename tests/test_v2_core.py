"""Tests for V2 core framework — types, agent base, bus."""

import pytest
from fanpage_agent.v2.core.types import (
    AgentRole, ActionPriority, AgentTask, AgentResult, PipelineState, ContentPackage, PerformancePattern,
)
from fanpage_agent.v2.core.agent import BaseAgent
from fanpage_agent.v2.core.bus import AgentBus
from fanpage_agent.v2.core.harness import AgentHarness, HarnessPolicy


class DummyAgent(BaseAgent):
    @property
    def role(self) -> AgentRole:
        return AgentRole.STRATEGIST

    @property
    def capabilities(self) -> list[str]:
        return ["test_action"]

    def handle_task(self, task: AgentTask) -> AgentResult:
        return AgentResult(task_id=task.id, success=True, data={"echo": task.params})


class PublishingDummyAgent(BaseAgent):
    @property
    def role(self) -> AgentRole:
        return AgentRole.PUBLISHER

    @property
    def capabilities(self) -> list[str]:
        return ["publish_post"]

    def handle_task(self, task: AgentTask) -> AgentResult:
        return AgentResult(task_id=task.id, success=True, data={"published": True})


class FakeAuditManager:
    def __init__(self):
        self.records = []

    def record(self, **kwargs):
        self.records.append(kwargs)
        return len(self.records)


class TestAgentTask:
    def test_create_task(self):
        task = AgentTask(id="t1", target=AgentRole.WRITER, action="write")
        assert task.id == "t1"
        assert task.target == AgentRole.WRITER
        assert task.action == "write"

    def test_priority_default(self):
        task = AgentTask(id="t2", target=AgentRole.STRATEGIST, action="plan")
        assert task.priority == ActionPriority.MEDIUM

    def test_priority_order(self):
        low = AgentTask(id="l", target=AgentRole.ANALYST, action="r", priority=ActionPriority.LOW)
        high = AgentTask(id="h", target=AgentRole.ORCHESTRATOR, action="t", priority=ActionPriority.CRITICAL)
        assert high.priority.value < low.priority.value


class TestAgentResult:
    def test_success_result(self):
        r = AgentResult(task_id="t1", success=True, data={"ok": True})
        assert r.success
        assert r.data["ok"]

    def test_error_result(self):
        r = AgentResult(task_id="t2", success=False, error="fail")
        assert not r.success
        assert r.error == "fail"

    def test_auto_timestamp(self):
        r = AgentResult(task_id="t3", success=True)
        assert r.completed_at  # auto-generated


class TestPipelineState:
    def test_default_state(self):
        s = PipelineState()
        assert s.pending_approval == 0
        assert s.weekly_post_count == 0
        assert s.calendar_gap_days == []

    def test_to_dict(self):
        s = PipelineState(pending_approval=3, published_today=1)
        d = s.to_dict()
        assert d["calendar"]["pending_approval"] == 3
        assert d["calendar"]["published_today"] == 1

    def test_full_state(self):
        s = PipelineState(
            pending_approval=2,
            approved_ready=1,
            published_today=3,
            weekly_post_count=5,
            avg_reach_7d=1500.0,
            avg_engagement_7d=45.0,
            top_pillar_last_7d="skincare_routine",
            last_tick_status="ok",
            uptime_hours=12.5,
        )
        d = s.to_dict()
        assert d["performance"]["weekly_posts"] == 5
        assert d["performance"]["top_pillar"] == "skincare_routine"
        assert d["system"]["uptime_hours"] == 12.5


class TestPerformancePattern:
    def test_create_pattern(self):
        p = PerformancePattern(
            pattern_id="p1", pattern_type="pillar", value="skincare",
            avg_reach=500.0, avg_engagement=25.0, sample_size=10,
            confidence=0.8, last_seen="2026-06-01",
            recommendation="Ưu tiên pillar này",
        )
        assert p.pattern_type == "pillar"
        assert p.sample_size == 10
        assert p.confidence == 0.8


class TestContentPackage:
    def test_empty_package(self):
        p = ContentPackage(package_id="pkg1", brand_id="test", scheduled_date="2026-06-10")
        assert p.status == "draft"
        assert p.best_variant() is None

    def test_best_variant_by_score(self):
        from fanpage_agent.v2.core.types import ContentVariant
        p = ContentPackage(package_id="pkg2", brand_id="test", scheduled_date="2026-06-10")
        p.variants = [
            ContentVariant(variant_id="a", topic="t1", pillar="p1",
                          caption="A", hook="h1", cta="cta1", format="text_image",
                          score=10.0),
            ContentVariant(variant_id="b", topic="t2", pillar="p1",
                          caption="B", hook="h2", cta="cta2", format="text_image",
                          score=20.0),
        ]
        best = p.best_variant()
        assert best is not None
        assert best.variant_id == "b"
        assert best.score == 20.0


class TestBaseAgent:
    def test_dummy_agent(self):
        agent = DummyAgent()
        assert agent.role == AgentRole.STRATEGIST
        assert agent.capabilities == ["test_action"]

    def test_unknown_action_returns_error(self):
        agent = DummyAgent()
        task = AgentTask(id="t1", target=AgentRole.STRATEGIST, action="unknown")
        result = agent.process(task)
        assert not result.success
        assert "cannot handle" in (result.error or "")

    def test_process_success(self):
        agent = DummyAgent()
        task = AgentTask(id="t1", target=AgentRole.STRATEGIST, action="test_action",
                        params={"key": "val"})
        result = agent.process(task)
        assert result.success
        assert result.data["echo"]["key"] == "val"
        assert "elapsed_ms" in result.metrics

    def test_metrics_after_process(self):
        agent = DummyAgent()
        task = AgentTask(id="m1", target=AgentRole.STRATEGIST, action="test_action")
        result = agent.process(task)
        assert result.metrics["agent_role"] == "strategist"
        assert result.metrics["elapsed_ms"] >= 0


class TestAgentBus:
    def test_register_and_dispatch(self):
        bus = AgentBus()
        agent = DummyAgent()
        bus.register(agent)
        assert "strategist" in bus.registered_roles

    def test_dispatch_to_correct_agent(self):
        bus = AgentBus()
        bus.register(DummyAgent())
        task = AgentTask(id="d1", target=AgentRole.STRATEGIST, action="test_action")
        result = bus.dispatch(task)
        assert result.success

    def test_dispatch_unknown_action(self):
        bus = AgentBus()
        bus.register(DummyAgent())
        task = AgentTask(id="d2", target=AgentRole.WRITER, action="unknown")
        result = bus.dispatch(task)
        assert not result.success

    def test_duplicate_register_raises(self):
        bus = AgentBus()
        bus.register(DummyAgent())
        with pytest.raises(ValueError, match="already registered"):
            bus.register(DummyAgent())

    def test_dispatch_batch_priority_order(self):
        bus = AgentBus()
        bus.register(DummyAgent())
        tasks = [
            AgentTask(id="low", target=AgentRole.STRATEGIST, action="test_action",
                     priority=ActionPriority.LOW),
            AgentTask(id="high", target=AgentRole.STRATEGIST, action="test_action",
                     priority=ActionPriority.CRITICAL),
        ]
        results = bus.dispatch_batch(tasks)
        assert len(results) == 2

    def test_create_task_helper(self):
        bus = AgentBus()
        task = bus.create_task(AgentRole.STRATEGIST, "test_action", {"key": "val"},
                              ActionPriority.HIGH)
        assert task.action == "test_action"
        assert task.params["key"] == "val"
        assert task.priority == ActionPriority.HIGH
        assert task.target == AgentRole.STRATEGIST
        assert task.id.startswith("task-")

    def test_history_tracking(self):
        bus = AgentBus()
        bus.register(DummyAgent())
        task = AgentTask(id="h1", target=AgentRole.STRATEGIST, action="test_action")
        bus.dispatch(task)
        assert len(bus.history) == 1
        assert bus.history[0]["task_id"] == "h1"

    def test_summary(self):
        bus = AgentBus()
        bus.register(DummyAgent())
        task = AgentTask(id="s1", target=AgentRole.STRATEGIST, action="test_action")
        bus.dispatch(task)
        summary = bus.summary()
        assert "strategist" in summary["agents"]
        assert summary["dispatches"] == 1
        assert summary["harness"]["events"] == 1


class TestAgentHarness:
    def test_harness_records_success(self):
        harness = AgentHarness()
        agent = DummyAgent()
        task = AgentTask(id="h1", target=AgentRole.STRATEGIST, action="test_action")
        result = harness.run(agent, task)
        assert result.success
        assert result.metrics["harness_status"] == "success"
        assert harness.summary()["counts"]["success"] == 1

    def test_harness_blocks_disallowed_action(self):
        policy = HarnessPolicy(allowed_actions={AgentRole.STRATEGIST: {"other_action"}})
        harness = AgentHarness(policy)
        agent = DummyAgent()
        task = AgentTask(id="h2", target=AgentRole.STRATEGIST, action="test_action")
        result = harness.run(agent, task)
        assert not result.success
        assert "blocked" in (result.error or "")
        assert harness.summary()["counts"]["blocked"] == 1

    def test_harness_requires_approval_for_sensitive_action(self):
        policy = HarnessPolicy(approval_required_actions={"test_action"})
        harness = AgentHarness(policy)
        agent = DummyAgent()
        task = AgentTask(id="h3", target=AgentRole.STRATEGIST, action="test_action")
        result = harness.run(agent, task)
        assert not result.success
        assert "requires explicit approval" in (result.error or "")

    def test_harness_allows_approved_sensitive_action(self):
        policy = HarnessPolicy(approval_required_actions={"test_action"})
        harness = AgentHarness(policy)
        agent = DummyAgent()
        task = AgentTask(
            id="h4",
            target=AgentRole.STRATEGIST,
            action="test_action",
            context={"approved": True},
        )
        result = harness.run(agent, task)
        assert result.success

    def test_harness_requires_approval_for_default_publish_action(self):
        harness = AgentHarness()
        agent = PublishingDummyAgent()
        task = AgentTask(id="h5", target=AgentRole.PUBLISHER, action="publish_post")
        result = harness.run(agent, task)
        assert not result.success
        assert "requires explicit approval" in (result.error or "")

    def test_harness_persists_events_to_audit_manager(self):
        audit_manager = FakeAuditManager()
        harness = AgentHarness(audit_manager=audit_manager)
        agent = DummyAgent()
        task = AgentTask(id="h6", target=AgentRole.STRATEGIST, action="test_action")
        result = harness.run(agent, task)
        assert result.success
        assert audit_manager.records[0]["event_type"] == "harness.success"
        assert audit_manager.records[0]["source"] == "AgentHarness"
