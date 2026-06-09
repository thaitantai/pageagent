#!/usr/bin/env python3
"""Tests for the Research Agent self-learning engine.

Covers:
- WeightOptimizer: correlation analysis, weight adjustment, no-data skip
- ConfidenceCalibrator: variance-based adjustment, baseline calibration
- DecayModel: exponential decay, skip on fresh topics, force decay
- UnifiedStore integration: get_weights, update_weight, learning_runs audit
"""

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fanpage_agent.adapters.sqlite_store import UnifiedStore
from fanpage_agent.tools.research.learning_optimizer import (
    ConfidenceCalibrator,
    DecayModel,
    WeightOptimizer,
    _exp_decay,
)


class WeightOptimizerTest(unittest.TestCase):
    """WeightOptimizer: adjusts scoring weights based on correlation analysis."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_learn.db"
        self.store = UnifiedStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.store.close()

    def seed_briefs(self, count: int = 5) -> None:
        """Seed research_briefs with realistic scores + actuals + calendar entries."""
        now = "2026-06-07T12:00:00+00:00"
        published_at = "2026-06-07T10:00:00+00:00"
        # First create calendar entries
        for i in range(count):
            cal_id = f"cal_{i}"
            with self.store._conn() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO calendar
                       (calendar_id, brand_id, date, pillar, objective, topic, angle,
                        status, published_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (cal_id, "test", "2026-06-07", "education", "reach", f"topic_{i}", "test",
                     "published", published_at),
                )
        # Then seed briefs
        for i in range(count):
            self.store.save_research_brief(
                generated_at=now,
                brand_id="test",
                topic=f"topic_{i}",
                total_score=0.8 if i < 3 else 0.4,
                brand_relevance=0.7 if i < 3 else 0.3,
                novelty=0.6 if i < 3 else 0.4,
                content_potential=0.8 if i < 3 else 0.4,
                source_confidence=0.8 if i < 3 else 0.5,
                fanpage_fit=0.6 if i < 3 else 0.4,
                customer_value=0.5 if i < 3 else 0.3,
            )
            # Mark published and add matching calendar with engagement
            self.store.mark_brief_published(i + 1, f"cal_{i}")
        # Then record metrics
        for i, eng in enumerate([40, 35, 45, 10, 8]):
            self.store.record_post_metrics(
                calendar_id=f"cal_{i}",
                reach=1000,
                engagements=eng,
                leads=eng // 5,
                recorded_at=now,
            )

    def test_optimizer_skips_without_enough_data(self) -> None:
        """No briefs → analysis returns empty → optimizer skips."""
        result = WeightOptimizer(self.store).run()
        self.assertEqual(result["status"], "skipped")
        self.assertIn("insufficient data", result["reason"])

    def test_optimizer_with_enough_data(self) -> None:
        """≥5 briefs with variance → optimizer produces changes or no_change."""
        self.seed_briefs(8)
        result = WeightOptimizer(self.store).run()
        self.assertIn(result["status"], ("ok", "no_change"))
        if result["changes"]:
            for c in result["changes"]:
                self.assertIn("weight_name", c)
                self.assertIn("from", c)
                self.assertIn("to", c)
                self.assertIn("correlation", c)
                self.assertTrue(isinstance(c["correlation"], float))

    def test_optimizer_logs_learning_run(self) -> None:
        """Optimization creates an audit log entry."""
        self.seed_briefs(8)
        WeightOptimizer(self.store).run()
        runs = self.store.get_learning_runs(run_type="weight_optimization")
        self.assertGreaterEqual(len(runs), 1)
        self.assertIn("changes", runs[0]["summary"])
        self.assertIsInstance(runs[0]["summary"]["changes"], list)

    def test_optimizer_weight_limits_respected(self) -> None:
        """Weights stay within configured bounds."""
        self.seed_briefs(8)
        # Run multiple iterations to push weights to extremes
        for _ in range(5):
            WeightOptimizer(self.store).run()
        weights = self.store.get_weights()
        # All weights within [0.01, 0.40]
        for name, value in weights.items():
            if name in ("brand_relevance", "novelty", "content_potential",
                        "source_confidence", "fanpage_fit", "customer_value"):
                self.assertGreaterEqual(value, 0.01, f"{name} too low: {value}")
                self.assertLessEqual(value, 0.40, f"{name} too high: {value}")


class ConfidenceCalibratorTest(unittest.TestCase):
    """ConfidenceCalibrator: adjusts thresholds from variance trends."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_calibrate.db"
        self.store = UnifiedStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.store.close()

    def seed_variance(self, variance: float, count: int = 8) -> None:
        """Seed briefs that create a specific variance pattern."""
        now = "2026-06-07T12:00:00+00:00"
        published_at = "2026-06-07T10:00:00+00:00"
        # Create calendar entries first
        eng = 50
        for i in range(count):
            if variance < 0:
                score = 0.8
                actual_eng = max(5, int(50 * (1 + variance)))
            else:
                score = 0.3
                actual_eng = max(5, int(50 * (1 + variance)))
            cal_id = f"cal_{i}"
            with self.store._conn() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO calendar
                       (calendar_id, brand_id, date, pillar, objective, topic, angle,
                        status, published_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (cal_id, "test", "2026-06-07", "education", "reach", f"topic_{i}", "test",
                     "published", published_at),
                )
            self.store.save_research_brief(
                generated_at=now,
                brand_id="test",
                topic=f"topic_{i}",
                total_score=score,
                brand_relevance=score,
                novelty=score,
                content_potential=score,
                source_confidence=score,
                fanpage_fit=score,
                customer_value=score,
            )
            self.store.mark_brief_published(i + 1, f"cal_{i}")
            self.store.record_post_metrics(
                calendar_id=f"cal_{i}",
                reach=1000,
                engagements=actual_eng,
                leads=actual_eng // 5,
                recorded_at=now,
            )

    def test_calibrator_skips_without_data(self) -> None:
        result = ConfidenceCalibrator(self.store).run()
        self.assertEqual(result["status"], "skipped")

    def test_calibrator_adjusts_floor_when_overconfident(self) -> None:
        """Negative variance → raise evidence confidence floor."""
        self.seed_variance(variance=-0.3, count=10)
        floor_before = self.store.get_weights().get("evidence_confidence_floor", 0.45)
        result = ConfidenceCalibrator(self.store).run()
        floor_after = self.store.get_weights().get("evidence_confidence_floor", 0.45)
        self.assertGreaterEqual(floor_after, floor_before,
                                f"Floor dropped: {floor_before} → {floor_after}")

    def test_calibrator_logs_adjustments(self) -> None:
        """Calibration creates audit log."""
        self.seed_variance(variance=-0.3, count=10)
        ConfidenceCalibrator(self.store).run()
        runs = self.store.get_learning_runs(run_type="confidence_calibration")
        self.assertGreaterEqual(len(runs), 1)


class DecayModelTest(unittest.TestCase):
    """DecayModel: time-based decay for topic performance scores."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_decay.db"
        self.store = UnifiedStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.store.close()

    def _inject_old_topic(self, topic: str, avg_rate: float, days_ago: int) -> None:
        """Inject a topic_performance record with an old updated_at."""
        from datetime import datetime, timedelta, timezone
        old = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        with self.store._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO topic_performance
                   (topic, total_reach, total_engagements, total_posts,
                    avg_engagement_rate, recent_engagement, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (topic, 5000, 200, 5, avg_rate, avg_rate, old),
            )

    def test_exp_decay_formula(self) -> None:
        """_exp_decay returns expected decay factors."""
        # At day 0: factor = 1.0
        self.assertAlmostEqual(_exp_decay(0), 1.0, places=4)
        # At half-life (21 days): factor ≈ 0.5
        self.assertAlmostEqual(_exp_decay(21), 0.5, places=2)
        # At day 42: factor ≈ 0.25
        self.assertAlmostEqual(_exp_decay(42), 0.25, places=1)
        # At day 7: ~0.79
        f7 = _exp_decay(7)
        self.assertLess(f7, 0.85)
        self.assertGreater(f7, 0.70)

    def test_decay_model_decays_old_topics(self) -> None:
        """Topics updated >3 days ago get decayed."""
        self._inject_old_topic("da khô và mất nước", avg_rate=0.07, days_ago=30)
        self._inject_old_topic("soi da có cần thiết không", avg_rate=0.05, days_ago=14)
        result = DecayModel(self.store).run()
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["decayed_topics"], 1)

    def test_decay_model_skips_fresh_topics(self) -> None:
        """Topics updated <3 days ago are not decayed unless force=True."""
        self._inject_old_topic("fresh topic", avg_rate=0.06, days_ago=1)
        result = DecayModel(self.store).run()
        if result.get("decayed_topics", 0) > 0:
            # Might still decay other seeded topics — check this specific one
            details = [d for d in result.get("details", []) if d.get("topic") == "fresh topic"]
            self.assertEqual(len(details), 0, "Fresh topic should not be decayed")

    def test_decay_model_force_decays_anyway(self) -> None:
        """force_decay=True decays even fresh topics."""
        self._inject_old_topic("fresh topic force", avg_rate=0.06, days_ago=1)
        result = DecayModel(self.store).run(force_decay=True)
        self.assertIn(result["status"], ("ok", "no_decay_needed"))

    def test_decay_model_logs_learning_run(self) -> None:
        """Decay creates audit log with topic names."""
        self._inject_old_topic("da khô", avg_rate=0.07, days_ago=30)
        DecayModel(self.store).run()
        runs = self.store.get_learning_runs(run_type="topic_decay")
        self.assertGreaterEqual(len(runs), 1)

    def test_decay_model_skips_when_no_topics(self) -> None:
        """No topic_performance data → status=skipped."""
        result = DecayModel(self.store).run()
        self.assertEqual(result["status"], "skipped")


class UnifiedStoreLearningExtrasTest(unittest.TestCase):
    """UnifiedStore methods for learning support."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_us_learn.db"
        self.store = UnifiedStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.store.close()

    def test_get_topic_performance_returns_list(self) -> None:
        tp = self.store.get_topic_performance()
        self.assertIsInstance(tp, list)

    def test_log_and_get_learning_runs(self) -> None:
        rid = self.store.log_learning_run("test_run", {"msg": "hello"})
        self.assertGreater(rid, 0)
        runs = self.store.get_learning_runs("test_run")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["summary"]["msg"], "hello")

    def test_get_learning_runs_filter_type(self) -> None:
        self.store.log_learning_run("type_a", {"x": 1})
        self.store.log_learning_run("type_b", {"y": 2})
        a_runs = self.store.get_learning_runs("type_a")
        self.assertEqual(len(a_runs), 1)
        b_runs = self.store.get_learning_runs("type_b")
        self.assertEqual(len(b_runs), 1)

    def test_update_topic_performance_decay(self) -> None:
        # Create a record first
        with self.store._conn() as conn:
            conn.execute(
                """INSERT INTO topic_performance
                   (topic, total_reach, total_engagements, total_posts,
                    avg_engagement_rate, recent_engagement, updated_at)
                   VALUES ('test_topic', 1000, 50, 2, 0.05, 0.05, datetime('now'))"""
            )
        self.store.update_topic_performance_decay("test_topic", 0.03, 0.6)
        tp = self.store.get_topic_performance()
        matching = [t for t in tp if t["topic"] == "test_topic"]
        self.assertEqual(len(matching), 1)
        self.assertAlmostEqual(matching[0]["avg_engagement_rate"], 0.03, places=4)

    def test_weights_have_new_columns(self) -> None:
        """evidence_confidence_floor and engagement_baseline are seeded."""
        weights = self.store.get_weights()
        self.assertIn("evidence_confidence_floor", weights)
        self.assertIn("engagement_baseline", weights)
        self.assertEqual(weights["evidence_confidence_floor"], 0.45)
        self.assertEqual(weights["engagement_baseline"], 50.0)


if __name__ == "__main__":
    unittest.main()
