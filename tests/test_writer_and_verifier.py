from pathlib import Path
import unittest

from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.services.writer import WriterService
from fanpage_agent.services.verifier import VerifierService


class WriterAndVerifierTest(unittest.TestCase):
    def test_writer_returns_three_variants_and_verifier_accepts(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)

        writer = WriterService()
        verifier = VerifierService()

        package = writer.write_caption(
            profile=profile,
            topic="5 dấu hiệu da đang thiếu nước",
            pillar="education",
            objective="engagement",
            fmt="post_short",
        )
        result = verifier.verify_caption_package(profile, package)

        self.assertEqual(len(package.variants), 3)
        self.assertTrue(result.passed)
        self.assertEqual(result.issues, [])


if __name__ == "__main__":
    unittest.main()
