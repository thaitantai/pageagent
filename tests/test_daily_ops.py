import json
import tempfile
import unittest
from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.tools.publishing.daily_ops import DailyOpsTool


class DailyOpsToolTest(unittest.TestCase):
    def test_build_packet_contains_plan_caption_and_telegram_preview(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            calendar = tmpdir / "calendar.csv"
            history = tmpdir / "history.csv"
            store = LocalSheetStore(calendar_csv=calendar, history_csv=history)

            packet = DailyOpsTool().build_packet(
                profile=profile,
                run_date="2026-06-12",
                store=store,
                days=1,
                write_calendar=True,
            )

            self.assertEqual(packet["run_date"], "2026-06-12")
            self.assertEqual(packet["plan"]["plan_title"], "weekly-plan-brand_abc-2026-06-12")
            self.assertEqual(packet["calendar_id"], "weekly-plan-brand_abc-2026-06-12-1")
            self.assertIn("caption_package", packet)
            self.assertIn("telegram_preview", packet)
            self.assertIn("Weekly Plan", packet["telegram_preview"]["plan_message"])
            self.assertIn("Caption Package", packet["telegram_preview"]["caption_message"])

    def test_evidence_gate_blocked_packet_skips_public_caption_draft(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "brand_profile.json"
        profile = load_brand_profile(sample)

        class BlockedResearchPacket:
            handoff_policy = {"max_safe_use": "draft_questions_only"}
            gate_reasons = ["chưa có source_documents đã kiểm chứng"]

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            store = LocalSheetStore(
                calendar_csv=tmpdir / "calendar.csv",
                history_csv=tmpdir / "history.csv",
            )

            packet = DailyOpsTool().build_packet(
                profile=profile,
                run_date="2026-06-12",
                store=store,
                days=1,
                research_packet=BlockedResearchPacket(),
            )

            self.assertIn("add_sources", packet["actions"])
            self.assertNotIn("approve_or_revise", packet["actions"])
            self.assertFalse(packet["caption_package"]["verification"]["passed"])
            self.assertIn("Research blocked", packet["caption_package"]["topic"])


if __name__ == "__main__":
    unittest.main()
