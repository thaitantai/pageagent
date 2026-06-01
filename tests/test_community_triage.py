import tempfile
import unittest
from pathlib import Path

from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.services.community_triage import CommunityTriageService


class CommunityTriageServiceTest(unittest.TestCase):
    def test_triage_comments_classifies_priority_escalation_and_draft_reply(self) -> None:
        root = Path(__file__).resolve().parents[1]
        profile = load_brand_profile(root / "data" / "sample" / "brand_profile.json")

        with tempfile.TemporaryDirectory() as tmp:
            comment_file = Path(tmp) / "comment_inbox.csv"
            comment_file.write_text(
                "created_at,source,message\n"
                "2026-06-24,comment,Bên mình bán thuốc mọc tóc không ạ?\n"
                "2026-06-24,inbox,Chi phí soi da là bao nhiêu?\n"
                "2026-06-24,comment,Mình bị kích ứng sau treatment, cần hỗ trợ gấp\n"
                "2026-06-24,comment,Xem ngay http://spam.example để nhận quà\n",
                encoding="utf-8",
            )

            payload = CommunityTriageService().triage_from_csv(profile=profile, comment_csv=comment_file)

        self.assertEqual(payload.summary["total_items"], 4)
        self.assertEqual(payload.summary["by_category"]["question"], 1)
        self.assertEqual(payload.summary["by_category"]["lead"], 1)
        self.assertEqual(payload.summary["by_category"]["complaint"], 1)
        self.assertEqual(payload.summary["by_category"]["spam"], 1)

        question_item = payload.items[0]
        self.assertEqual(question_item.category, "question")
        self.assertEqual(question_item.priority, "normal")
        self.assertFalse(question_item.escalation_required)
        self.assertTrue(question_item.requires_human_approval)
        self.assertIn("không thay thế tư vấn chuyên môn", question_item.draft_reply.lower())

        lead_item = payload.items[1]
        self.assertEqual(lead_item.category, "lead")
        self.assertEqual(lead_item.priority, "high")
        self.assertTrue(lead_item.escalation_required)
        self.assertIn("nhắn tin", lead_item.draft_reply.lower())

        complaint_item = payload.items[2]
        self.assertEqual(complaint_item.category, "complaint")
        self.assertEqual(complaint_item.priority, "urgent")
        self.assertTrue(complaint_item.escalation_required)
        self.assertIn("xin lỗi", complaint_item.draft_reply.lower())

        spam_item = payload.items[3]
        self.assertEqual(spam_item.category, "spam")
        self.assertEqual(spam_item.priority, "low")
        self.assertEqual(spam_item.recommended_action, "ignore_or_hide")
        self.assertEqual(spam_item.draft_reply, "")


if __name__ == "__main__":
    unittest.main()
