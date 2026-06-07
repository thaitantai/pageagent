from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from fanpage_agent.models import (
    BrandProfile,
    CommentInboxEntry,
    CommunityTriageBatch,
    CommunityTriageItem,
)
from fanpage_agent.services.research import ResearchService


class CommunityTriageService:
    SPAM_KEYWORDS = ("http://", "https://", "bit.ly", "kiếm tiền", "nhận quà", "combo giá sỉ")
    COMPLAINT_KEYWORDS = (
        "khiếu nại",
        "không hài lòng",
        "bực",
        "tệ",
        "hoàn tiền",
        "kích ứng",
        "dị ứng",
        "hỗ trợ gấp",
        "phản ánh",
    )
    LEAD_KEYWORDS = (
        "giá",
        "bao nhiêu",
        "chi phí",
        "đặt lịch",
        "tư vấn",
        "inbox",
        "soi da",
        "khám",
    )
    QUESTION_KEYWORDS = ("?", "là gì", "khi nào", "như thế nào", "có nên", "ở đâu")

    def triage_from_csv(self, profile: BrandProfile, comment_csv: str | Path | None = None) -> CommunityTriageBatch:
        entries = ResearchService._read_comments(comment_csv)
        return self.triage_entries(profile=profile, entries=entries)

    def triage_entries(self, profile: BrandProfile, entries: list[CommentInboxEntry]) -> CommunityTriageBatch:
        items = [self._triage_entry(profile, entry, index=index) for index, entry in enumerate(entries, start=1)]
        category_counts = Counter(item.category for item in items)
        priority_counts = Counter(item.priority for item in items)
        summary = {
            "total_items": len(items),
            "by_category": dict(category_counts),
            "by_priority": dict(priority_counts),
            "escalation_count": sum(1 for item in items if item.escalation_required),
            "approval_required_count": sum(1 for item in items if item.requires_human_approval),
        }
        return CommunityTriageBatch(items=items, summary=summary)

    def _triage_entry(self, profile: BrandProfile, entry: CommentInboxEntry, index: int) -> CommunityTriageItem:
        normalized = entry.message.lower().strip()
        escalation_terms = [rule for rule in profile.approval_flow.escalation_rules if rule and rule.lower() in normalized]

        if self._contains_any(normalized, self.SPAM_KEYWORDS):
            category = "spam"
            priority = "low"
            recommended_action = "ignore_or_hide"
            draft_reply = ""
            matched_rules = ["spam-keyword"]
            escalation_required = False
        elif self._contains_any(normalized, self.COMPLAINT_KEYWORDS):
            category = "complaint"
            priority = "urgent"
            recommended_action = "escalate_to_human"
            draft_reply = self._build_complaint_reply(profile)
            matched_rules = ["complaint-keyword"]
            escalation_required = True
        elif escalation_terms or self._contains_any(normalized, self.LEAD_KEYWORDS):
            category = "lead"
            priority = "high"
            recommended_action = "reply_and_route_to_inbox"
            draft_reply = self._build_lead_reply(profile)
            matched_rules = ["lead-keyword"]
            asks_for_price = any(term in normalized for term in ("giá", "bao nhiêu", "chi phí"))
            if escalation_terms:
                matched_rules.extend([f"escalation:{term}" for term in escalation_terms])
            if asks_for_price:
                matched_rules.append("escalation:price-request")
            escalation_required = bool(escalation_terms) or asks_for_price
        elif self._contains_any(normalized, self.QUESTION_KEYWORDS):
            category = "question"
            priority = "normal"
            recommended_action = "reply_with_guidance"
            draft_reply = self._build_question_reply(profile)
            matched_rules = ["question-pattern"]
            escalation_required = False
        else:
            category = "general"
            priority = "normal"
            recommended_action = "reply_or_monitor"
            draft_reply = self._build_general_reply(profile)
            matched_rules = ["fallback"]
            escalation_required = False

        return CommunityTriageItem(
            triage_id=self._build_triage_id(entry, index),
            created_at=entry.created_at,
            source=entry.source,
            message=entry.message,
            category=category,
            priority=priority,
            recommended_action=recommended_action,
            draft_reply=draft_reply,
            escalation_required=escalation_required,
            requires_human_approval=profile.approval_flow.comment_reply_requires_human_approval,
            matched_rules=matched_rules,
        )

    @staticmethod
    def _build_triage_id(entry: CommentInboxEntry, index: int) -> str:
        source_slug = re.sub(r"[^a-z0-9]+", "-", entry.source.lower()).strip("-") or "source"
        message_slug = re.sub(r"[^a-z0-9]+", "-", entry.message.lower())
        message_slug = message_slug.strip("-")[:24] or "message"
        date_slug = re.sub(r"[^0-9]+", "", entry.created_at)[:8] or "00000000"
        return f"triage-{date_slug}-{source_slug}-{index:02d}-{message_slug}"

    @staticmethod
    def _contains_any(message: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in message for keyword in keywords)

    @staticmethod
    def _opening_phrase(profile: BrandProfile) -> str:
        if profile.tone_of_voice.sample_phrases:
            return profile.tone_of_voice.sample_phrases[0]
        return f"{profile.brand_name} đã nhận được tin nhắn của bạn"

    def _build_question_reply(self, profile: BrandProfile) -> str:
        opening = self._opening_phrase(profile)
        compliance = (
            profile.compliance_notes[-1]
            if profile.compliance_notes
            else "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn chuyên môn"
        )
        return (
            f"{opening}, bên mình sẽ giải thích ngắn gọn để bạn dễ hình dung. "
            f"{compliance.lower()}. Nếu bạn muốn, có thể nhắn tin để đội ngũ tư vấn xem tình trạng cụ thể kỹ hơn."
        )

    def _build_lead_reply(self, profile: BrandProfile) -> str:
        opening = self._opening_phrase(profile)
        lead_cta = next((item.cta_text for item in profile.approved_cta_patterns if item.objective == "lead"), "Nhắn tin để được tư vấn kỹ hơn")
        return (
            f"{opening}, để tư vấn đúng tình trạng và báo thông tin phù hợp hơn, "
            f"bạn có thể {lead_cta.lower()}. Bên mình sẽ hỗ trợ theo hướng rõ ràng và thực tế hơn cho bạn."
        )

    def _build_complaint_reply(self, profile: BrandProfile) -> str:
        approver = profile.approval_flow.approver
        return (
            f"{profile.brand_name} xin lỗi vì trải nghiệm này chưa tốt như mong đợi của bạn. "
            f"Bạn vui lòng nhắn tin kèm tình trạng cụ thể để đội ngũ {approver} kiểm tra và hỗ trợ sớm hơn nhé."
        )

    def _build_general_reply(self, profile: BrandProfile) -> str:
        opening = self._opening_phrase(profile)
        return f"{opening}. Bên mình đã ghi nhận và sẽ phản hồi theo hướng phù hợp nhất cho bạn."
