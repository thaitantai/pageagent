"""CommunityAgent — community triage, comment management, and auto-replies.

Uses LLM (via LLMAdapter) for contextual reply generation.
Keeps keyword-based triage for speed, with optional LLM enhancement.
"""
from __future__ import annotations

from typing import Any

from fanpage_agent_v2.adapters.llm_adapter import LLMAdapter
from fanpage_agent_v2.core.agent import BaseAgent
from fanpage_agent_v2.core.types import AgentRole, AgentResult, AgentTask

_COMMUNITY_SYSTEM_PROMPT = """Bạn là Community Manager cho fanpage skincare GenZ.

NHIỆM VỤ: Trả lời bình luận của khách hàng với giọng điệu chân thật, ấm áp, gần gũi.

NGUYÊN TẮC:
- Khách khen: cảm ơn và hỏi thêm để tương tác
- Khách hỏi: trả lời chuyên môn nhưng dễ hiểu, gợi ý inbox nếu cần tư vấn cá nhân
- Khách phàn nàn: xin lỗi chân thành, đề nghị hỗ trợ riêng
- Spam: không cần reply
- GenZ tone: tự nhiên, friendly, không copy-paste

Trả lời bằng JSON thuần, không markdown."""


class CommunityAgent(BaseAgent):
    """Community manager — triages comments, suggests replies using LLM or template.

    When an ``fb_adapter`` is provided, the agent can also fetch live comments
    from Facebook (``fetch_and_triage``) so the orchestrator doesn't need to
    manually pass in comment data.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        llm: LLMAdapter | None = None,
        fb_adapter: Any = None,  # FacebookAdapter | None
    ) -> None:
        super().__init__(config)
        self._llm = llm
        self._fb = fb_adapter
        self._last_fetched: list[dict] = []

    @property
    def role(self) -> AgentRole:
        return AgentRole.COMMUNITY

    @property
    def capabilities(self) -> list[str]:
        return ["fetch_and_triage", "triage_comments", "suggest_reply", "sentiment_summary", "auto_reply"]

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params

        if action == "fetch_and_triage":
            return self._fetch_and_triage(
                limit=params.get("limit", 50),
            )
        elif action == "triage_comments":
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
        elif action == "auto_reply":
            return self._auto_reply(
                comments=params.get("comments", []),
                limit=params.get("limit", 5),
            )
        return AgentResult(task_id=task.id, success=False, error=f"Unknown action: {action}")

    def _fetch_and_triage(self, limit: int = 50) -> AgentResult:
        """Fetch recent comments from Facebook and triage them.

        Gets recent posts, fetches comments for each, classifies them,
        and returns the triage result. Falls back gracefully if no FB
        adapter is available.
        """
        if self._fb is None:
            return AgentResult(
                task_id="fetch-triage",
                success=True,
                data={
                    "total_analysed": 0,
                    "categories": {},
                    "note": "No FacebookAdapter — skip fetch",
                    "urgent_count": 0,
                    "reply_needed_count": 0,
                },
            )

        all_comments: list[dict] = []
        fetch_errors = 0
        try:
            posts = self._fb.get_recent_posts(limit=5)
            for post in posts:
                post_id = post.get("id", "")
                if not post_id:
                    continue
                try:
                    comments = self._fb.get_comments(post_id, limit=limit)
                    for c in comments:
                        c["post_id"] = post_id
                    all_comments.extend(comments)
                except Exception:
                    fetch_errors += 1
        except Exception as e:
            return AgentResult(
                task_id="fetch-triage",
                success=False,
                error=f"Failed to fetch posts: {e}",
            )

        self._last_fetched = all_comments  # cache for sentiment_summary
        return self._triage_comments(all_comments, limit)

    def _triage_comments(self, comments: list[dict], limit: int) -> AgentResult:
        """Classify comments into categories using keyword matching."""
        categories = {"spam": [], "question": [], "praise": [], "complaint": [], "neutral": []}

        for c in comments[:limit]:
            text = c.get("message", "")
            cat = self._classify(text)
            categories[cat].append(c)

        urgent = categories["complaint"]
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
        """Generate a reply suggestion — LLM or template fallback."""
        # ── Try LLM ──
        if self._llm and comment_text:
            prompt = f"""Đề xuất câu trả lời cho bình luận sau trên fanpage skincare:

Bình luận: "{comment_text}"
Sentiment: {sentiment}

Output JSON:
{{
  "suggestion": "câu trả lời tự nhiên, friendly, bằng tiếng Việt",
  "sentiment": "{sentiment}",
  "auto_reply": false,
  "reasoning": "tại sao reply thế này"
}}"""
            data = self._llm.generate_json(_COMMUNITY_SYSTEM_PROMPT, prompt)
            if data:
                return AgentResult(
                    task_id=f"reply-{hash(comment_text) % 10**6}",
                    success=True,
                    data={
                        "suggestion": data.get("suggestion", ""),
                        "sentiment": sentiment,
                        "auto_reply": data.get("auto_reply", False),
                        "generated_by": "llm",
                    },
                )

        # ── Template fallback ──
        suggestions = {
            "praise": "Cảm ơn bạn đã chia sẻ! Mình rất vui vì điều đó 🤗",
            "question": "Mình xin phép giải thích nhé! ...",
            "complaint": "Mình rất tiếc về trải nghiệm này. Bạn có thể inbox cho mình để được hỗ trợ chi tiết hơn không ạ?",
            "spam": "",
        }

        return AgentResult(
            task_id=f"reply-{hash(comment_text) % 10**6}",
            success=True,
            data={
                "suggestion": suggestions.get(sentiment, ""),
                "sentiment": sentiment,
                "auto_reply": sentiment in ("spam",),
                "generated_by": "template",
            },
        )

    def _sentiment_summary(self, comments: list[dict]) -> AgentResult:
        """Summarise community sentiment."""
        n = len(comments)
        if n == 0:
            return AgentResult(
                task_id="sentiment-summary",
                success=True,
                data={"total": 0, "summary": "Chưa có comments mới.", "trend": "neutral"},
            )

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

        # LLM enhancement for summary
        if self._llm and n > 5:
            prompt = f"""Tóm tắt cảm xúc cộng đồng từ {n} comments:
- Tích cực: {cats['positive']}
- Tiêu cực: {cats['negative']}
- Trung tính: {cats['neutral']}

Output JSON:
{{
  "summary": "tóm tắt 1-2 câu bằng tiếng Việt",
  "trend": "positive|negative|neutral"
}}"""
            data = self._llm.generate_json(_COMMUNITY_SYSTEM_PROMPT, prompt)
            if data:
                return AgentResult(
                    task_id="sentiment-summary",
                    success=True,
                    data={
                        "total": n,
                        "breakdown": cats,
                        "positive_ratio": round(cats["positive"] / n * 100, 1),
                        "negative_ratio": round(cats["negative"] / n * 100, 1),
                        "summary": data.get("summary", ""),
                        "trend": data.get("trend", "neutral"),
                        "generated_by": "llm",
                    },
                )

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
                "generated_by": "template",
            },
        )

    def _auto_reply(self, comments: list[dict], limit: int = 5) -> AgentResult:
        """Auto-reply to comments that qualify (praise, simple questions).

        Requires fb_adapter to actually post replies. Generates reply
        via LLM or template, then posts via Graph API.
        """
        if not self._fb:
            return AgentResult(
                task_id="auto-reply", success=True,
                data={"replied": 0, "note": "No FacebookAdapter — skip auto-reply"},
            )

        replied = 0
        errors = 0
        replies: list[dict] = []

        for c in comments[:limit]:
            text = c.get("message", "")
            cid = c.get("id", "")
            if not cid or not text:
                continue

            sentiment = self._classify(text)

            # Only auto-reply to praise and simple questions
            if sentiment not in ("praise", "question", "neutral"):
                continue

            # Generate reply
            suggestion = self._suggest_reply(text, sentiment)
            if not suggestion.success:
                errors += 1
                continue

            reply_text = suggestion.data.get("suggestion", "")
            if not reply_text:
                continue

            # Post reply to Facebook
            try:
                self._fb.reply_to_comment(comment_id=cid, message=reply_text)
                replied += 1
                replies.append({
                    "comment_id": cid,
                    "sentiment": sentiment,
                    "reply_preview": reply_text[:60],
                })
            except Exception as e:
                errors += 1

        return AgentResult(
            task_id="auto-reply",
            success=True,
            data={
                "total_processed": len(comments[:limit]),
                "replied": replied,
                "errors": errors,
                "replies": replies,
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
