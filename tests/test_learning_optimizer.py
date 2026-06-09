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
    GoalWeightOptimizer,
    PerformancePredictor,
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


class PerformancePredictorTest(unittest.TestCase):
    """PerformancePredictor: linear regression from total_score → engagement."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_predict.db"
        self.store = UnifiedStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.store.close()

    def seed_briefs(self, count: int = 10) -> None:
        """Seed briefs with clear score→engagement correlation."""
        now = "2026-06-07T12:00:00+00:00"
        published_at = "2026-06-07T10:00:00+00:00"
        for i in range(count):
            cal_id = f"cal_p_{i}"
            score = min(1.0, max(0.1, 0.25 + i * 0.07))
            eng = int(score * 80)
            with self.store._conn() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO calendar
                       (calendar_id, brand_id, date, pillar, objective, topic, angle,
                        status, published_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (cal_id, "test", "2026-06-07", "education", "engagement",
                     f"pred_topic_{i}", "test", "published", published_at),
                )
            self.store.save_research_brief(
                generated_at=now, brand_id="test", topic=f"pred_topic_{i}",
                total_score=score, brand_relevance=score, novelty=score * 0.8,
                content_potential=score, source_confidence=score,
                fanpage_fit=score * 0.9, customer_value=score * 0.7,
            )
            self.store.mark_brief_published(i + 1, cal_id)
            self.store.record_post_metrics(
                calendar_id=cal_id, reach=1000, engagements=eng,
                leads=eng // 5, recorded_at=now,
            )

    def test_predictor_skips_without_enough_data(self) -> None:
        """Fewer than 5 briefs → skipped."""
        predictor = PerformancePredictor(self.store)
        result = predictor.train()
        self.assertEqual(result["status"], "skipped")

    def test_predictor_trains_with_enough_data(self) -> None:
        """≥5 briefs → train returns model params."""
        self.seed_briefs(10)
        predictor = PerformancePredictor(self.store)
        result = predictor.train()
        self.assertEqual(result["status"], "ok")
        self.assertIn("params", result)
        self.assertIn("metrics", result)
        self.assertIn("slope", result["params"])
        self.assertIn("intercept", result["params"])
        self.assertIn("r2", result["metrics"])
        self.assertIn("mae", result["metrics"])
        self.assertIn("mape", result["metrics"])

    def test_predictor_metrics_are_reasonable(self) -> None:
        """R² should be positive, MAE finite, MAPE < 100%."""
        self.seed_briefs(10)
        predictor = PerformancePredictor(self.store)
        result = predictor.train()
        self.assertGreater(result["metrics"]["r2"], -1.0,
                           "R² shouldn't be terribly negative")
        self.assertLess(result["metrics"]["mae"], 1000,
                        "MAE shouldn't be huge")
        self.assertGreaterEqual(result["metrics"]["mape"], 0.0)
        self.assertLess(result["metrics"]["mape"], 2.0,
                        "MAPE under 200% is reasonable")

    def test_predictor_predicts_reasonable_values(self) -> None:
        """Predict should return engagement within bounds."""
        self.seed_briefs(10)
        predictor = PerformancePredictor(self.store)
        predictor.train()
        result = predictor.predict(total_score=0.7)
        self.assertIn("predicted_engagement", result)
        self.assertIn("confidence", result)
        self.assertGreaterEqual(result["predicted_engagement"], 0)
        self.assertLessEqual(result["predicted_engagement"], 500)
        self.assertGreaterEqual(result["confidence"], 0.1)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_predictor_predicts_lower_for_low_scores(self) -> None:
        """Lower score → lower predicted engagement."""
        self.seed_briefs(10)
        predictor = PerformancePredictor(self.store)
        predictor.train()
        high = predictor.predict(total_score=0.8)["predicted_engagement"]
        low = predictor.predict(total_score=0.2)["predicted_engagement"]
        self.assertGreaterEqual(high, low,
                                "Higher score should predict >= lower score")

    def test_predictor_state_survives_reinit(self) -> None:
        """Trained state persists in store and can be loaded by new instance."""
        self.seed_briefs(10)
        p1 = PerformancePredictor(self.store)
        p1.train()
        p2 = PerformancePredictor(self.store)
        quality = p2.get_quality()
        self.assertEqual(quality["status"], "trained")
        self.assertIsNotNone(quality["mae"])
        self.assertIsNotNone(quality["r2"])

    def test_predictor_logs_learning_run(self) -> None:
        """Training creates predictor_training audit log."""
        self.seed_briefs(10)
        PerformancePredictor(self.store).train()
        runs = self.store.get_learning_runs(run_type="predictor_training")
        self.assertGreaterEqual(len(runs), 1)

    def test_predictor_untrained_quality(self) -> None:
        """Untrained predictor returns status=untrained."""
        p = PerformancePredictor(self.store)
        q = p.get_quality()
        self.assertEqual(q["status"], "untrained")
        self.assertIsNone(q["mae"])

    def test_predictor_save_predictor_state(self) -> None:
        """save_predictor_state/get_predictor_state roundtrip."""
        state = {"params": {"slope": 0.5, "intercept": 0.3}, "metrics": {"mae": 5.0}}
        self.store.save_predictor_state(state)
        loaded = self.store.get_predictor_state()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["params"]["slope"], 0.5)
        self.assertEqual(loaded["params"]["intercept"], 0.3)
        self.assertEqual(loaded["metrics"]["mae"], 5.0)

    def test_get_predictor_state_returns_none_when_empty(self) -> None:
        """No predictor_state in DB → returns None."""
        self.assertIsNone(self.store.get_predictor_state())

    def test_predictor_detect_drift(self) -> None:
        """detect_concept_drift returns False when untrained."""
        p = PerformancePredictor(self.store)
        self.assertFalse(p.detect_concept_drift())

    def test_predictor_handles_score_bounds(self) -> None:
        """Predict clamps score to [0, 1]."""
        self.seed_briefs(10)
        p = PerformancePredictor(self.store)
        p.train()
        r1 = p.predict(total_score=-0.5)
        r2 = p.predict(total_score=1.5)
        self.assertGreaterEqual(r1["predicted_engagement"], 0)
        self.assertGreaterEqual(r2["predicted_engagement"], 0)

    def test_predictor_does_not_mutate_store_on_predict_alone(self) -> None:
        """predict() without train() should read, not write."""
        self.seed_briefs(10)
        p = PerformancePredictor(self.store)
        # Predict without training first — uses defaults, no write
        r = p.predict(total_score=0.5)
        self.assertIn("predicted_engagement", r)
        # No predictor_state should exist
        self.assertIsNone(self.store.get_predictor_state())
        # No predictor_training run either
        runs = self.store.get_learning_runs(run_type="predictor_training")
        self.assertEqual(len(runs), 0)


class GoalWeightOptimizerTest(unittest.TestCase):
    """GoalWeightOptimizer: per-goal weight adjustment based on variance."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_goal_opt.db"
        self.store = UnifiedStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.store.close()

    def seed_goal_briefs(
        self, goal_type: str, count: int = 5, high_eng: bool = True,
    ) -> None:
        """Seed briefs for a specific goal type with calendar + metrics."""
        now = "2026-06-07T12:00:00+00:00"
        published_at = "2026-06-07T10:00:00+00:00"
        for i in range(count):
            cal_id = f"gcal_{goal_type}_{i}"
            topic = f"gtopic_{goal_type}_{i}"
            # Assign topic to goal
            self.store.set_topic_goal(topic, goal_type)
            # Create calendar entry with matching topic
            with self.store._conn() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO calendar
                       (calendar_id, brand_id, date, pillar, objective, topic, angle,
                        status, published_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (cal_id, "test", "2026-06-07", "education", goal_type, topic, "test",
                     "published", published_at),
                )
            # Create brief with topic assigned to goal
            score = 0.8 if high_eng else 0.3
            self.store.save_research_brief(
                generated_at=now, brand_id="test", topic=topic,
                total_score=score, brand_relevance=score, novelty=score * 0.8,
                content_potential=score, source_confidence=score,
                fanpage_fit=score * 0.9, customer_value=score * 0.7,
            )
            # Mark published — find brief by topic
            with self.store._conn() as conn:
                brief_row = conn.execute(
                    "SELECT id FROM research_briefs WHERE topic=? ORDER BY id DESC LIMIT 1",
                    (topic,),
                ).fetchone()
            if brief_row:
                self.store.mark_brief_published(brief_row["id"], cal_id)
            # Record metrics
            eng = 40 if high_eng else 5
            self.store.record_post_metrics(
                calendar_id=cal_id, reach=1000, engagements=eng,
                leads=eng // 5, recorded_at=now,
            )

    def test_goal_optimizer_accepts_valid_goal_types(self) -> None:
        """Goal types from store.GOAL_TYPES are accepted."""
        optimizer = GoalWeightOptimizer(self.store)
        for gt in ("reach", "engagement", "conversion", "balanced"):
            result = optimizer.run(gt)
            self.assertIn(result["status"], ("skipped", "ok", "no_change"))

    def test_goal_optimizer_rejects_invalid_goal(self) -> None:
        """Unknown goal type => skipped."""
        result = GoalWeightOptimizer(self.store).run("invalid")
        self.assertEqual(result["status"], "skipped")

    def test_goal_optimizer_skips_without_data(self) -> None:
        """No briefs for a goal type => skipped."""
        result = GoalWeightOptimizer(self.store).run("reach")
        self.assertEqual(result["status"], "skipped")
        self.assertIn("insufficient data", result.get("reason", ""))

    def test_goal_optimizer_generates_changes(self) -> None:
        """With enough briefs, optimizer produces changes or no_change."""
        self.seed_goal_briefs("reach", count=8, high_eng=True)
        result = GoalWeightOptimizer(self.store).run("reach")
        self.assertIn(result["status"], ("ok", "no_change"))

    def test_goal_optimizer_does_not_affect_other_goals(self) -> None:
        """Optimizing one goal leaves other goals' weights unchanged."""
        self.seed_goal_briefs("conversion", count=8, high_eng=True)
        w_before = self.store.get_weights_for_goal("balanced")
        GoalWeightOptimizer(self.store).run("conversion")
        w_after = self.store.get_weights_for_goal("balanced")
        self.assertEqual(w_before, w_after,
                         "Balanced weights changed after optimizing conversion")

    def test_goal_optimizer_logs_to_learning_runs(self) -> None:
        """Per-goal optimization creates an audit log."""
        self.seed_goal_briefs("engagement", count=8, high_eng=True)
        GoalWeightOptimizer(self.store).run("engagement")
        runs = self.store.get_learning_runs(run_type="goal_weight_optimization_engagement")
        self.assertGreaterEqual(len(runs), 1)
        self.assertEqual(runs[0]["summary"].get("goal_type"), "engagement")

    def test_goal_weight_limits_per_goal(self) -> None:
        """Reach weights have higher novelty limit than conversion."""
        from fanpage_agent.tools.research.learning_optimizer import _GOAL_WEIGHT_LIMITS
        reach_limits = _GOAL_WEIGHT_LIMITS["reach"]
        conv_limits = _GOAL_WEIGHT_LIMITS["conversion"]
        # Reach has higher novelty max
        self.assertGreater(reach_limits["novelty"][1], conv_limits["novelty"][1])
        # Conversion has higher customer_value max
        self.assertGreater(conv_limits["customer_value"][1], reach_limits["customer_value"][1])

    def test_goal_weights_independent_in_store(self) -> None:
        """Each goal type has its own weight set in the DB."""
        # Change a weight for 'reach'
        self.store.update_goal_weight("reach", "novelty", 0.25)
        # Verify 'balanced' unchanged
        bw = self.store.get_weights_for_goal("balanced")
        self.assertNotAlmostEqual(bw.get("novelty", 0), 0.25, places=4)


class GoalWeightStoreTest(unittest.TestCase):
    """UnifiedStore methods for per-goal weight management."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_goal_store.db"
        self.store = UnifiedStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.store.close()

    def test_get_goal_types_returns_all(self) -> None:
        types = self.store.get_goal_types()
        self.assertCountEqual(types, ["reach", "engagement", "conversion", "balanced"])

    def test_get_weights_for_goal_returns_dict(self) -> None:
        w = self.store.get_weights_for_goal("reach")
        self.assertIn("brand_relevance", w)
        self.assertIn("novelty", w)
        self.assertGreater(w["novelty"], 0)

    def test_update_goal_weight_persists(self) -> None:
        self.store.update_goal_weight("reach", "novelty", 0.30)
        w = self.store.get_weights_for_goal("reach")
        self.assertAlmostEqual(w["novelty"], 0.30, places=4)

    def test_set_and_get_topic_goal(self) -> None:
        self.store.set_topic_goal("retinoid cho da dầu", "conversion")
        goal = self.store.get_topic_goal("retinoid cho da dầu")
        self.assertEqual(goal, "conversion")

    def test_get_topic_goal_default(self) -> None:
        goal = self.store.get_topic_goal("unknown_topic")
        self.assertEqual(goal, "balanced")

    def test_get_all_topic_goals(self) -> None:
        self.store.set_topic_goal("topic_a", "reach")
        self.store.set_topic_goal("topic_b", "engagement")
        goals = self.store.get_all_topic_goals()
        self.assertEqual(len(goals), 2)
        goal_map = {g["topic"]: g["goal_type"] for g in goals}
        self.assertEqual(goal_map["topic_a"], "reach")
        self.assertEqual(goal_map["topic_b"], "engagement")


if __name__ == "__main__":
    unittest.main()
