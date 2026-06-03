"""CommunityAgent — community triage, comment management, and auto-replies."""

from __future__ import annotations

from typing import Any

from fanpage_agent_v2.core.agent import BaseAgent
from fanpage_agent_v2.core.types import AgentRole, AgentResult, AgentTask, ActionPriority


class CommunityAgent(BaseAgent):
    """Community manager — triages comments, suggests replies.

    Capabilities:
    - triage_comments: Classify new comments (spam/question/praise/complaint)
    - suggest_reply: Generate a reply suggestion
    - urgent_mentions: Flag urgent/high-priority mentions
    - sentiment_summary: Summarise community sentiment
    """

    @property
    def role(self) -> AgentRole:
        return AgentRole.COMMUNITY

    @property
    def capabilities(self) -> list[str]:
        return ["triage_comments", "suggest_reply", "urgent_mentions", "sentiment_summary"]

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params

        if action == "triage_comments":
            return self._triage_comments(
                comments=params.get("comments", []),
                limit=params.get("limit", 20),
            )
        elif action == "suggest_reply":
            return self._suggest_reply(
                comment_text=params.get("text", ""),
                sentiment=params.get("sentiment", "neutral"),
            )
        elif action == "sentiment_summary":
            return self._sentiment_summary(
                comments=params.get("comments", []),
            )
        return AgentResult(task_id=task.id, success=False, error=f"Unknown action: {action}")

    def _triage_comments(self, comments: list[dict], limit: int) -> AgentResult:
        """Classify comments into categories."""
        categories = {"spam": [], "question": [], "praise": [], "complaint": [], "neutral": []}

        for c in comments[:limit]:
            text = c.get("message", "")
            cat = self._classify(text)
            categories[cat].append(c)

        urgent = [c for c in categories["complaint"]]
        reply_needed = categories["question"] + categories["complaint"]

        return AgentResult(
            task_id="triage",
            success=True,
            data={
                "total_analysed": len(comments[:limit]),
                "categories": {k: len(v) for k, v in categories.items()},
                "urgent_count": len(urgent),
                "reply_needed_count": len(reply_needed),
                "recommendations": [
                    f"Trả lời {len(reply_needed)} comments cần phản hồi",
                    f"{len(urgent)} complaints cần xử lý gấp" if urgent else None,
                ],
            },
        )

    def _suggest_reply(self, comment_text: str, sentiment: str) -> AgentResult:
        """Generate a reply suggestion (LLM placeholder)."""
        suggestions = {
            "praise": "Cảm ơn bạn đã chia sẻ! Mình rất vui vì điều đó 🤗",
            "question": "Mình xin phép giải thích nhé! ...",
            "complaint": "Mình rất tiếc về trải nghiệm này. Bạn có thể inbox cho mình để được hỗ trợ chi tiết hơn không ạ?",
            "spam": "",  # No reply needed
        }

        return AgentResult(
            task_id=f"reply-{id(comment_text)}",
            success=True,
            data={
                "suggestion": suggestions.get(sentiment, ""),
                "sentiment": sentiment,
                "auto_reply": sentiment in ("spam",),
            },
        )

    def _sentiment_summary(self, comments: list[dict]) -> AgentResult:
        """Summarise community sentiment."""
        n = len(comments)
        if n == 0:
            return AgentResult(
                task_id="sentiment-summary",
                success=True,
                data={
                    "total": 0,
                    "summary": "Chưa có comments mới.",
                    "trend": "neutral",
                },
            )

        # Map classification → sentiment category
        cat_map = {
            "praise": "positive",
            "complaint": "negative",
            "question": "neutral",
            "neutral": "neutral",
            "spam": "neutral",
        }
        cats = {"positive": 0, "negative": 0, "neutral": 0}
        for c in comments:
            cls = self._classify(c.get("message", ""))
            cats[cat_map.get(cls, "neutral")] += 1

        return AgentResult(
            task_id="sentiment-summary",
            success=True,
            data={
                "total": n,
                "breakdown": cats,
                "positive_ratio": round(cats["positive"] / n * 100, 1),
                "negative_ratio": round(cats["negative"] / n * 100, 1),
                "summary": f"{cats['positive']} tích cực, {cats['negative']} tiêu cực, {cats['neutral']} trung tính",
                "trend": "positive" if cats["positive"] > cats["negative"] else "negative",
            },
        )

    @staticmethod
    def _classify(text: str) -> str:
        """Simple keyword-based classification."""
        text_lower = text.lower()
        spam_words = ["mua", "giá", "khuyến mãi", "spam", "link", "http"]
        question_words = ["có", "không", "sao", "thế nào", "bao nhiêu", "gì", "?", "tại sao"]
        praise_words = ["tốt", "hay", "cảm ơn", "thích", "đẹp", "tuyệt", "hiệu quả", "👍", "❤️"]
        complaint_words = ["tệ", "kém", "thất vọng", "lừa", "giả", "không hiệu quả", "phí tiền"]

        if any(w in text_lower for w in spam_words):
            return "spam"
        if any(w in text_lower for w in complaint_words):
            return "complaint"
        if any(w in text_lower for w in praise_words):
            return "praise"
        if any(w in text_lower for w in question_words):
            return "question"
        return "neutral"
