"""CommunityAgent — community triage, comment management, and auto-replies.

Uses LLM (via LLMAdapter) for contextual reply generation.
Keeps keyword-based triage for speed, with optional LLM enhancement.
Includes self-reply on new posts for early engagement boost.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fanpage_agent.adapters.llm_adapter import LLMAdapter
from fanpage_agent.core.agent import BaseAgent
from fanpage_agent.core.types import ActionPriority, AgentRole, AgentResult, AgentTask

# ── Quality thresholds ──────────────────────────────────────────────
_MIN_REPLY_LENGTH = 10
_MAX_REPLY_LENGTH = 200
_QUALITY_SCORE_THRESHOLD = 0.4
_GENERIC_REPLY_MODELS = [
    "cảm ơn bạn", "cảm ơn em", "cảm ơn chị", "cảm ơn anh",
    "thanks bạn", "ok bạn", "ok em", "ok chị", "ok anh",
]
_REPLY_TIMESTAMPS_FILE = "data/agent/reply_timestamps.json"

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
        data_dir: str | Path | None = None,
        default_page_id: str | None = None,
    ) -> None:
        super().__init__(config)
        self._llm = llm
        self._fb = fb_adapter
        self._default_page_id = default_page_id
        self._last_fetched: list[dict] = []

        # Reply tracking — avoids double-reply, supports scheduling
        data_path = Path(data_dir) if data_dir else Path("data/agent")
        self._reply_cache_path = data_path / "replied_comments.json"
        self._reply_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._replied_comment_ids: set[str] = self._load_replied_ids()

    # ── Persistence ──────────────────────────────────────────────

    def _load_replied_ids(self) -> set[str]:
        """Load already-replied comment IDs from disk."""
        try:
            data = json.loads(self._reply_cache_path.read_text())
            return set(data.get("ids", []))
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            return set()

    def _save_replied_ids(self) -> None:
        """Persist replied comment IDs to disk."""
        try:
            self._reply_cache_path.write_text(
                json.dumps({"ids": list(self._replied_comment_ids)}, ensure_ascii=False)
            )
        except Exception:
            pass  # Non-critical

    def _mark_replied(self, comment_id: str) -> None:
        """Mark a comment as already replied to."""
        self._replied_comment_ids.add(comment_id)
        if len(self._replied_comment_ids) > 200:
            # Trim oldest entries to keep file small
            self._replied_comment_ids = set(list(self._replied_comment_ids)[-200:])
        self._save_replied_ids()

    @property
    def role(self) -> AgentRole:
        return AgentRole.COMMUNITY

    @property
    def capabilities(self) -> list[str]:
        return [
            "fetch_and_triage", "triage_comments", "suggest_reply",
            "sentiment_summary", "auto_reply", "self_reply_post",
        ]

    def _resolve_page_id(self, params: dict) -> str | None:
        return params.get("page_id") or self._default_page_id

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params
        page_id = self._resolve_page_id(params)

        if action == "fetch_and_triage":
            return self._fetch_and_triage(
                limit=params.get("limit", 50),
                page_id=page_id,
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
                max_replies=params.get("max_replies", 3),
                page_id=page_id,
            )
        elif action == "self_reply_post":
            result = self._self_reply_post(
                fb_post_id=params.get("fb_post_id", ""),
                post_topic=params.get("topic", ""),
                page_id=page_id,
            )
            if result.success:
                self._mark_shared_done(
                    processed_publisher_version=self._pipeline_version("publisher"),
                    self_replied=True,
                    fb_post_id=result.data.get("post_id", ""),
                    preview=result.data.get("comment_preview", ""),
                )
            return result
        return AgentResult(task_id=task.id, success=False, error=f"Unknown action: {action}")

    def self_driving_tick(self) -> list[tuple[str, dict, ActionPriority]]:
        """Propose community tasks: self-reply after new publish, or periodic triage."""
        proposals: list[tuple[str, dict, ActionPriority]] = []

        # Check for new publisher data (choreography chain)
        if self._has_upstream_data("publisher", "processed_publisher_version"):
            publisher_data = self._get_shared("publisher", {})
            proposals.append(("self_reply_post", {
                "fb_post_id": publisher_data.get("fb_post_id", ""),
                "topic": "",
            }, ActionPriority.MEDIUM))

        if self._should_act("fetch_and_triage", 21600):
            proposals.append(("fetch_and_triage", {"limit": 50}, ActionPriority.HIGH))
        if self._should_act("auto_reply", 10800):
            proposals.append(("auto_reply", {"limit": 5, "max_replies": 3}, ActionPriority.MEDIUM))
        if self._should_act("sentiment_summary", 86400):
            proposals.append(("sentiment_summary", {}, ActionPriority.LOW))
        return proposals

    # ── Self-reply on own post (early engagement boost) ──────────

    def _self_reply_post(
        self, fb_post_id: str, post_topic: str = "",
        page_id: str | None = None,
    ) -> AgentResult:
        """Post a natural comment on the page's own new post to boost early engagement.

        This simulates the first comment to break the ice and encourage
        the audience to join the conversation.
        """
        if not self._fb:
            return AgentResult(
                task_id="self-reply", success=True,
                data={"replied": 0, "note": "No FacebookAdapter — skip self-reply"},
            )

        self_replies = [
            "Mình vừa chia sẻ xong, hy vọng có ích cho mọi người! Có ai đã thử cách này chưa? 👇",
            "Bài viết mới nóng hổi vừa ra lò! Mọi người đọc thử rồi cho mình biết nghĩ sao nhé ✨",
            "Vừa viết xong bài này, mình cũng bất ngờ với mấy tips này luôn đó! Các bạn thấy sao?",
            "Chia sẻ với mọi người bài mới đây! Cảm ơn đã ghé đọc và ủng hộ fanpage nha 💕",
            "Mới đăng nè! Mình mong là tips này sẽ giúp ích được cho các bạn đang gặp vấn đề tương tự 🤗",
        ]

        import random
        comment = random.choice(self_replies)
        if post_topic:
            short_topic = post_topic[:30]
            comment = f"Mình vừa chia sẻ về {short_topic}, hy vọng có ích cho mọi người! Cảm ơn đã ghé đọc nha 💕"

        try:
            self._fb.comment_on_post(fb_post_id=fb_post_id, message=comment, page_id=page_id)
            return AgentResult(
                task_id="self-reply",
                success=True,
                data={
                    "replied": 1,
                    "post_id": fb_post_id,
                    "comment_preview": comment[:60],
                },
            )
        except Exception as e:
            return AgentResult(
                task_id="self-reply",
                success=False,
                error=f"Self-reply failed: {e}",
            )

    # ── Fetch + Triage ────────────────────────────────────────────

    def _fetch_and_triage(self, limit: int = 50, page_id: str | None = None) -> AgentResult:
        # ... unchanged from original ...
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
            posts = self._fb.get_recent_posts(limit=5, page_id=page_id)
            for post in posts:
                post_id = post.get("id", "")
                if not post_id:
                    continue
                try:
                    comments = self._fb.get_comments(post_id, limit=limit, page_id=page_id)
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

        self._last_fetched = all_comments
        return self._triage_comments(all_comments, limit)

    def _triage_comments(self, comments: list[dict], limit: int) -> AgentResult:
        # ... unchanged from original ...
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

    # ── Reply Suggestion (with quality control) ──────────────────

    def _suggest_reply(self, comment_text: str, sentiment: str) -> AgentResult:
        """Generate a reply suggestion — LLM or template fallback.
        
        Adds quality checks: minimum length, generic reply detection.
        """
        # ── Try LLM ──
        if self._llm and comment_text:
            prompt = f"""Đề xuất câu trả lời cho bình luận sau trên fanpage skincare:

Bình luận: "{comment_text}"
Sentiment: {sentiment}

YÊU CẦU CHẤT LƯỢNG:
- Trả lời phải dài tối thiểu 10 ký tự, tối đa 200 ký tự
- KHÔNG dùng các câu chung chung như "Cảm ơn bạn", "Ok bạn", "Thanks"
- Phải có nội dung cụ thể liên quan đến bình luận
- Phải có câu hỏi tương tác ở cuối để khuyến khích reply tiếp

Output JSON:
{{
  "suggestion": "câu trả lời tự nhiên, friendly, bằng tiếng Việt",
  "sentiment": "{sentiment}",
  "auto_reply": false,
  "reasoning": "tại sao reply thế này",
  "quality_score": 0.0
}}"""
            data = self._llm.generate_json(_COMMUNITY_SYSTEM_PROMPT, prompt)
            if data:
                suggestion = data.get("suggestion", "")
                quality = data.get("quality_score", 0.5)
                # Quality gate: check length and generic patterns
                if self._passes_quality_gate(suggestion, quality):
                    return AgentResult(
                        task_id=f"reply-{hash(comment_text) % 10**6}",
                        success=True,
                        data={
                            "suggestion": suggestion,
                            "sentiment": sentiment,
                            "auto_reply": data.get("auto_reply", False),
                            "generated_by": "llm",
                            "quality_score": quality,
                        },
                    )

        # ── Template fallback with personalization ──
        # Use a piece of the comment to make reply less generic
        snippet = comment_text[:30].strip() if comment_text else ""
        templates = {
            "praise": (
                f"Cảm ơn bạn đã chia sẻ! Mình rất vui vì '{snippet}' có ích với bạn. "
                "Bạn đã thử sản phẩm/dịch vụ này chưa? 🤗"
            ),
            "question": (
                f"Mình xin phép giải thích nhé! Về '{snippet}', "
                "mình recommend inbox để được tư vấn chi tiết hơn phù hợp với da của bạn nha!"
            ),
            "complaint": (
                "Mình rất tiếc về trải nghiệm này. Bạn có thể inbox cho mình "
                "để được hỗ trợ chi tiết hơn không ạ? Mình muốn giúp bạn giải quyết vấn đề này! 💪"
            ),
            "spam": "",
        }

        reply = templates.get(sentiment, "")
        if reply and not self._passes_template_gate(reply):
            reply = ""  # Spam catches will just get silence

        return AgentResult(
            task_id=f"reply-{hash(comment_text) % 10**6}",
            success=True,
            data={
                "suggestion": reply,
                "sentiment": sentiment,
                "auto_reply": sentiment in ("spam",),
                "generated_by": "template",
                "quality_score": 0.5,
            },
        )

    @staticmethod
    def _passes_quality_gate(suggestion: str, quality_score: float) -> bool:
        """Check if a reply suggestion meets minimum quality standards."""
        if len(suggestion.strip()) < _MIN_REPLY_LENGTH:
            return False
        if len(suggestion) > _MAX_REPLY_LENGTH:
            return False
        if quality_score < _QUALITY_SCORE_THRESHOLD:
            return False
        sug_lower = suggestion.lower().strip()
        for generic in _GENERIC_REPLY_MODELS:
            if generic in sug_lower:
                return False
        return True

    @staticmethod
    def _passes_template_gate(reply: str) -> bool:
        """Minimal check for template replies."""
        return len(reply.strip()) >= _MIN_REPLY_LENGTH

    # ── Sentiment Summary ─────────────────────────────────────────

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

    # ── Auto-reply (with scheduling + quality gate) ──────────────

    def _auto_reply(self, comments: list[dict], limit: int = 5, max_replies: int = 3,
                     page_id: str | None = None) -> AgentResult:
        """Auto-reply to comments that qualify (praise, simple questions).

        Respects ``max_replies`` cap per tick. Uses replied-IDs cache to
        avoid double-replying. Filters by quality gate so generic replies
        don't get posted.

        Requires fb_adapter to actually post replies.
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
            # Respect max_replies cap
            if replied >= max_replies:
                break

            text = c.get("message", "")
            cid = c.get("id", "")
            if not cid or not text:
                continue

            # Skip already-replied comments
            if cid in self._replied_comment_ids:
                continue

            sentiment = self._classify(text)

            # Only auto-reply to praise, questions, neutral
            if sentiment not in ("praise", "question", "neutral"):
                continue

            # Generate reply
            suggestion = self._suggest_reply(text, sentiment)
            if not suggestion.success:
                errors += 1
                continue

            reply_text = suggestion.data.get("suggestion", "")
            quality = suggestion.data.get("quality_score", 0.0)
            if not reply_text:
                continue

            # Quality gate for auto-reply (stricter than suggest)
            if not self._passes_quality_gate(reply_text, quality):
                errors += 1
                continue

            # Post reply to Facebook
            try:
                self._fb.reply_to_comment(comment_id=cid, message=reply_text, page_id=page_id)
                replied += 1
                self._mark_replied(cid)
                replies.append({
                    "comment_id": cid,
                    "sentiment": sentiment,
                    "reply_preview": reply_text[:60],
                    "quality_score": quality,
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
                "max_replies_hit": replied >= max_replies,
            },
        )

    # ── Classification (improved) ─────────────────────────────────

    @staticmethod
    def _classify(text: str) -> str:
        """Improved keyword-based classification.

        Changes from original:
        - "mua", "giá" moved to question (they're sales leads, not spam)
        - Added skincare-specific keywords for better triage
        """
        text_lower = text.lower()

        # Spam — only actual spam patterns
        spam_words = [
            "http://", "https://", "bit.ly", "tặng quà", "trúng thưởng",
            "spam", "lừa đảo",
        ]

        # Complaint — negative experiences
        complaint_words = [
            "tệ", "kém", "thất vọng", "lừa", "giả", "không hiệu quả",
            "phí tiền", "kích ứng", "dị ứng", "mụn thêm", "bỏng rát",
            "không đúng", "hàng fake", "hàng giả", "tiền mất",
        ]

        # Praise — positive feedback
        praise_words = [
            "tốt", "hay", "cảm ơn", "thích", "đẹp", "tuyệt", "hiệu quả",
            "👍", "❤️", "😍", "🥰", "xoá mụn", "giảm mụn", "cải thiện",
        ]

        # Question — inquiries, buying intent, advice seeking
        question_words = [
            "?", "có", "không", "sao", "thế nào", "bao nhiêu", "gì",
            "tại sao", "mua", "giá", "ở đâu", "khi nào", "loại nào",
            "còn không", "có tốt", "dùng được", "phù hợp", "nên dùng",
            "bôi", "uống", "dùng", "cần", "tư vấn", "inbox",
            "spf", "retinol", "aha", "bha", "niacinamide",
        ]

        if any(w in text_lower for w in spam_words):
            return "spam"
        if "?" in text_lower or text_lower.startswith(("tại sao", "vì sao")):
            return "question"
        if any(w in text_lower for w in complaint_words):
            return "complaint"
        if any(w in text_lower for w in praise_words):
            return "praise"
        if any(w in text_lower for w in question_words):
            return "question"
        return "neutral"
