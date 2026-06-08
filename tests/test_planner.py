from pathlib import Path
import unittest

from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.publishing.planner import PlannerTool


class PlannerToolTest(unittest.TestCase):
    def test_plan_week_returns_requested_number_of_days(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)

        service = PlannerTool()
        plan = service.plan_week(profile=profile, start_date="2026-06-01", days=3)

        self.assertEqual(plan.plan_title, "weekly-plan-brand_abc-2026-06-01")
        self.assertEqual(len(plan.days), 3)
        self.assertEqual(plan.days[0].objective, "reach")
        self.assertTrue(plan.days[0].cta)


if __name__ == "__main__":
    unittest.main()
