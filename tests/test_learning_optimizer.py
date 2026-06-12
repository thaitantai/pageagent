"""Tests for self-learning modules — calibrator, decay, lifecycle, predictor."""

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from fanpage_agent.tools.research.learning_calibrator import ConfidenceCalibrator
from fanpage_agent.tools.research.learning_lifecycle import DecayModel, LifecycleManager, _exp_decay
from fanpage_agent.tools.research.learning_predictor import PerformancePredictor


class ExpDecayTest(unittest.TestCase):
    """Core decay function used throughout learning modules."""

    def test_exp_decay_at_zero_days(self) -> None:
        self.assertAlmostEqual(_exp_decay(0), 1.0, places=4)

    def test_exp_decay_at_half_life(self) -> None:
        # Half-life = 21 days → decay = 0.5 at day 21
        result = _exp_decay(21)
        self.assertAlmostEqual(result, 0.5, places=2)

    def test_exp_decay_long_term(self) -> None:
        self.assertLess(_exp_decay(90), 0.1)

    def test_exp_decay_short_term(self) -> None:
        self.assertGreater(_exp_decay(3), 0.9)
        self.assertLess(_exp_decay(3), 1.0)

    def test_exp_decay_negative_days(self) -> None:
        self.assertGreaterEqual(_exp_decay(-5), 1.0)


class DecayModelTest(unittest.TestCase):
    """DecayModel — time-based score decay on topic performance."""

    def setUp(self) -> None:
        self.mock_store = MagicMock()
        self.model = DecayModel(store=self.mock_store)

    def test_skip_when_no_topic_performance(self) -> None:
        self.mock_store.get_topic_performance.return_value = []
        result = self.model.run()
        self.assertEqual(result["status"], "skipped")
        self.assertIn("no topic performance", result["reason"])

    def test_skips_recent_topics_without_force(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.mock_store.get_topic_performance.return_value = [
            {"topic": "retinol guide", "updated_at": now, "score": 0.8,
             "avg_engagement_rate": 0.05, "total_engagement": 10},
        ]
        result = self.model.run()
        self.assertEqual(result["status"], "no_decay_needed")

    def test_decays_old_topics(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        self.mock_store.get_topic_performance.return_value = [
            {"topic": "old retinol guide", "updated_at": old, "score": 0.8,
             "avg_engagement_rate": 0.05, "total_engagement": 10},
        ]
        self.mock_store.update_topic_performance.return_value = {"success": True}
        result = self.model.run()
        self.assertGreater(result.get("decayed_topics", 0), 0)

    def test_force_decay_applies_to_all(self) -> None:
        now = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        self.mock_store.get_topic_performance.return_value = [
            {"topic": "new topic", "updated_at": now, "score": 0.9,
             "avg_engagement_rate": 0.08, "total_engagement": 15},
        ]
        result = self.model.run(force_decay=True)
        self.assertGreater(result.get("decayed_topics", 0), 0)
        decayed = result.get("details", [])
        if decayed:
            self.assertLess(decayed[0]["decay_factor"], 1.0)


class ConfidenceCalibratorTest(unittest.TestCase):
    """ConfidenceCalibrator — adjusts thresholds based on prediction errors."""

    def setUp(self) -> None:
        self.mock_store = MagicMock()
        self.mock_store.get_weights.return_value = {
            "evidence_confidence_floor": 0.45,
            "engagement_baseline": 1.5,
            "novelty_multiplier": 1.0,
        }

    def test_skip_when_insufficient_samples(self) -> None:
        calibrator = ConfidenceCalibrator(store=self.mock_store)
        self.mock_store.get_variance_summary.return_value = {
            "sample_count": 2,
            "avg_variance": 0.0,
        }
        result = calibrator.run()
        self.assertEqual(result["status"], "skipped")

    def test_adjusts_floor_when_over_confident(self) -> None:
        calibrator = ConfidenceCalibrator(store=self.mock_store)
        self.mock_store.get_variance_summary.return_value = {
            "sample_count": 10,
            "avg_variance": -0.2,
        }
        result = calibrator.run()
        self.assertGreater(len(result.get("adjustments", [])), 0)

    def test_adjusts_floor_when_under_confident(self) -> None:
        calibrator = ConfidenceCalibrator(store=self.mock_store)
        self.mock_store.get_variance_summary.return_value = {
            "sample_count": 10,
            "avg_variance": 0.1,
        }
        result = calibrator.run()
        self.assertGreater(len(result.get("adjustments", [])), 0)

    def test_adjusts_baseline_on_trend(self) -> None:
        calibrator = ConfidenceCalibrator(store=self.mock_store)
        self.mock_store.get_variance_summary.return_value = {
            "sample_count": 10,
            "avg_variance": -0.5,
            "trend": "declining",
            "avg_engagement": 5.0,
        }
        self.mock_store.get_topic_performance.return_value = []
        result = calibrator.run()
        self.assertGreater(len(result.get("adjustments", [])), 0)


class LifecycleManagerTest(unittest.TestCase):
    """LifecycleManager — topic stage transitions."""

    def setUp(self) -> None:
        self.mock_store = MagicMock()
        # Add LIFE_CYCLE_STAGES attr
        self.mock_store.LIFE_CYCLE_STAGES = ("explore", "active", "mature", "retire")
        self.manager = LifecycleManager(store=self.mock_store)

    def test_returns_report_when_empty(self) -> None:
        self.mock_store.get_topic_lifecycle.return_value = []
        report = self.manager.get_lifecycle_report()
        self.assertEqual(report["total_topics"], 0)
        for stage in ("explore", "active", "mature", "retire"):
            self.assertIn(stage, report["by_stage"])

    def test_no_transitions_when_empty(self) -> None:
        self.mock_store.get_topic_performance.return_value = []
        # Don't call mock method — just check return value structure
        self.mock_store.auto_transition_lifecycles.return_value = {"transitions": []}
        result = self.manager.run()
        self.assertIn("transitions", result)


class PerformancePredictorTest(unittest.TestCase):
    """PerformancePredictor — engagement prediction model."""

    def setUp(self) -> None:
        self.mock_store = MagicMock()
        self.predictor = PerformancePredictor(store=self.mock_store)

    def test_skip_when_insufficient_data(self) -> None:
        self.mock_store.get_brief_feedback.return_value = []
        result = self.predictor.train()
        self.assertEqual(result["status"], "skipped")

    def test_train_with_sufficient_data(self) -> None:
        self.mock_store.get_brief_feedback.return_value = [
            {"brief_score": 0.7, "engagements": 15},
            {"brief_score": 0.5, "engagements": 8},
            {"brief_score": 0.3, "engagements": 3},
            {"brief_score": 0.8, "engagements": 22},
            {"brief_score": 0.6, "engagements": 12},
        ]
        result = self.predictor.train()
        self.assertEqual(result["status"], "ok")
        self.assertIn("mae", result.get("metrics", {}))
        self.assertIn("mape", result.get("metrics", {}))

    def test_predict_before_training(self) -> None:
        self.mock_store.get_brief_feedback.return_value = []
        self.predictor.train()
        pred = self.predictor.predict(total_score=0.5)
        self.assertIn("predicted_engagement", pred)

    def test_predict_after_training(self) -> None:
        self.mock_store.get_brief_feedback.return_value = [
            {"brief_score": 0.7, "engagements": 15},
            {"brief_score": 0.5, "engagements": 8},
            {"brief_score": 0.3, "engagements": 3},
            {"brief_score": 0.8, "engagements": 22},
            {"brief_score": 0.6, "engagements": 12},
        ]
        self.predictor.train()
        pred = self.predictor.predict(total_score=0.9)
        self.assertIn("predicted_engagement", pred)
        pred_low = self.predictor.predict(total_score=0.1)
        self.assertGreaterEqual(pred["predicted_engagement"], pred_low["predicted_engagement"])

    def test_get_quality_after_training(self) -> None:
        self.mock_store.get_brief_feedback.return_value = [
            {"brief_score": 0.7, "engagements": 15},
            {"brief_score": 0.5, "engagements": 8},
            {"brief_score": 0.3, "engagements": 3},
            {"brief_score": 0.8, "engagements": 22},
            {"brief_score": 0.6, "engagements": 12},
        ]
        self.predictor.train()
        quality = self.predictor.get_quality()
        self.assertIn("status", quality)


if __name__ == "__main__":
    unittest.main()
