from pathlib import Path
import unittest

from fanpage_agent.loaders.brand_loader import load_brand_profile


class BrandLoaderTest(unittest.TestCase):
    def test_load_brand_profile_from_sample_json(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)

        self.assertEqual(profile.brand_id, "brand_abc")
        self.assertEqual(profile.brand_name, "ABC Clinic")
        self.assertGreaterEqual(len(profile.content_pillars), 2)


if __name__ == "__main__":
    unittest.main()
