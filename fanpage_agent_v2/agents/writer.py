"""WriterAgent — generates multi-variant content captions for A/B testing.

Uses LLM (via LLMAdapter) to write real captions in GenZ skincare voice.
Falls back to empty variants if no LLM is configured.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fanpage_agent_v2.adapters.llm_adapter import LLMAdapter
from fanpage_agent_v2.core.agent import BaseAgent
from fanpage_agent_v2.core.types import (
    AgentRole,
    AgentResult,
    AgentTask,
    ContentPackage,
    ContentVariant,
)

_WRITER_SYSTEM_PROMPT = """Bạn là Copywriter chuyên content skincare/healthcare cho GenZ Việt Nam.

NHIỆM VỤ: Viết caption Facebook thu hút, chân thật, đúng giọng GenZ.

NGUYÊN TẮC:
- Ngắn gọn, dễ hiểu, gần gũi (xưng mình/bạn)
- Kiến thức chuyên môn nhưng không khô khan
- GenZ tone: tự nhiên, có thể hài hước nhẹ, không quá quảng cáo
- Kết bài bằng câu hỏi để tương tác
- Hashtags: #skincare #skincareroutine #genzskincare + 2-3 tag liên quan

FORMAT phổ biến: text_image (ảnh + chữ), carousel (nhiều ảnh), reel (video).

Trả lời bằng JSON thuần, không markdown."""


class WriterAgent(BaseAgent):
    """Writer — generates N variants of a content post using LLM or template."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        brand_id: str = "skincare_genz",
        default_variants: int = 2,
        llm: LLMAdapter | None = None,
    ) -> None:
        super().__init__(config)
        self._brand_id = brand_id
        self._default_variants = default_variants
        self._llm = llm

    @property
    def role(self) -> AgentRole:
        return AgentRole.WRITER

    @property
    def capabilities(self) -> list[str]:
        return ["write_variants", "rewrite", "merge_variants", "generate_hooks"]

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params

        if action == "write_variants":
            return self._write_variants(
                topic=params.get("topic", ""),
                pillar=params.get("pillar", ""),
                count=params.get("variants", self._default_variants),
                scheduled_date=params.get("scheduled_date"),
                scheduled_time=params.get("scheduled_time"),
            )
        elif action == "generate_hooks":
            return self._generate_hooks(
                topic=params.get("topic", ""),
                count=params.get("count", 5),
            )
        elif action == "rewrite":
            return self._rewrite_variant(
                variant_id=params.get("variant_id", ""),
                feedback=params.get("feedback", ""),
            )
        return AgentResult(task_id=task.id, success=False, error=f"Unknown action: {action}")

    def _write_variants(
        self,
        topic: str,
        pillar: str,
        count: int,
        scheduled_date: str | None,
        scheduled_time: str | None,
    ) -> AgentResult:
        """Generate N content variants — LLM or empty template fallback."""
        now = datetime.now(timezone.utc).isoformat()
        package_id = f"pkg-{uuid.uuid4().hex[:8]}"
        date = scheduled_date or now[:10]
        time = scheduled_time or "09:00"

        # ── Try LLM ──
        if self._llm and topic:
            prompt = f"""Viết {count} variant caption cho bài đăng Facebook về chủ đề skincare.

Thương hiệu: {self._brand_id}
Chủ đề: {topic}
Pillar: {pillar}
Số lượng variant: {count}

Mỗi variant cần có góc nhìn/giong điệu khác nhau (ví dụ: 1 chia sẻ, 1 chuyên môn, 1 hài hước).

Output JSON:
{{
  "variants": [
    {{
      "topic": "{topic}",
      "pillar": "{pillar}",
      "caption": "caption hoàn chỉnh (2-3 câu, có emoji, kết câu hỏi)",
      "hook": "câu mở đầu thu hút (1 câu)",
      "cta": "kêu gọi hành động (1 câu ngắn)",
      "format": "text_image|carousel|reel",
      "tone_tags": ["tone1", "tone2"],
      "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3"]
    }}
  ]
}}"""
            data = self._llm.generate_json(_WRITER_SYSTEM_PROMPT, prompt)
            if data and "variants" in data:
                variants = [
                    ContentVariant(
                        variant_id=f"var-{package_id}-{i}",
                        topic=v.get("topic", topic),
                        pillar=v.get("pillar", pillar),
                        caption=v.get("caption", ""),
                        hook=v.get("hook", ""),
                        cta=v.get("cta", ""),
                        format=v.get("format", self._pick_format(i)),
                        tone_tags=v.get("tone_tags", []),
                        hashtags=v.get("hashtags", self._base_hashtags()),
                    )
                    for i, v in enumerate(data["variants"][:count])
                ]
                return AgentResult(
                    task_id=f"write-{package_id}",
                    success=True,
                    data=ContentPackage(
                        package_id=package_id,
                        brand_id=self._brand_id,
                        scheduled_date=date,
                        scheduled_time=time,
                        variants=variants,
                        status="draft",
                    ),
                )

        # ── Template fallback — empty variants ──
        variants: list[ContentVariant] = []
        for i in range(count):
            variant_id = f"var-{package_id}-{i}"
            variants.append(ContentVariant(
                variant_id=variant_id,
                topic=topic,
                pillar=pillar,
                caption="",
                hook="",
                cta="",
                format=self._pick_format(i),
                tone_tags=["chia_sẻ"],
                hashtags=self._base_hashtags(),
            ))

        return AgentResult(
            task_id=f"write-{package_id}",
            success=True,
            data=ContentPackage(
                package_id=package_id,
                brand_id=self._brand_id,
                scheduled_date=date,
                scheduled_time=time,
                variants=variants,
                status="draft",
            ),
        )

    def _generate_hooks(self, topic: str, count: int) -> AgentResult:
        """Generate N hook options — LLM or template fallback."""
        if self._llm and topic:
            prompt = f"""Viết {count} câu hook thu hút cho bài đăng Facebook về: {topic}

Chủ đề: {topic}
Đối tượng: GenZ Việt Nam (18-25), quan tâm skincare

Output JSON:
{{
  "hooks": [
    "hook 1 - ngắn gọn, gây tò mò, có cảm xúc",
    "hook 2",
    ...
  ]
}}"""
            data = self._llm.generate_json(_WRITER_SYSTEM_PROMPT, prompt)
            if data and "hooks" in data:
                return AgentResult(
                    task_id=f"hooks-{topic[:20]}",
                    success=True,
                    data={
                        "hooks": data["hooks"][:count],
                        "count": min(len(data["hooks"]), count),
                        "generated_by": "llm",
                    },
                )

        # ── Template fallback ──
        hooks = [
            f"Mình từng {topic.lower()} và đây là điều rút ra…",
            f"Bạn có biết {topic.lower()} không? 🤔",
            f"3 sai lầm khi {topic.lower()} mà ai cũng mắc phải",
            f"Review thật: {topic.title()} — có đáng tiền?",
            f"Bác sĩ da liễu nói gì về {topic.lower()}?",
        ]
        return AgentResult(
            task_id=f"hooks-{topic[:20]}",
            success=True,
            data={"hooks": hooks[:count], "count": min(len(hooks), count), "generated_by": "template"},
        )

    def _rewrite_variant(self, variant_id: str, feedback: str) -> AgentResult:
        """Revise a variant — LLM rewrite or stub."""
        if self._llm and feedback:
            prompt = f"""Viết LẠI caption dựa trên phản hồi sau:

Variant ID: {variant_id}
Phản hồi: {feedback}

Output JSON:
{{
  "variant_id": "{variant_id}",
  "revised_caption": "caption đã sửa theo feedback",
  "changes": "mô tả ngắn những gì đã thay đổi"
}}"""
            data = self._llm.generate_json(_WRITER_SYSTEM_PROMPT, prompt)
            if data:
                return AgentResult(
                    task_id=f"rewrite-{variant_id}",
                    success=True,
                    data={**data, "feedback": feedback, "generated_by": "llm"},
                )

        return AgentResult(
            task_id=f"rewrite-{variant_id}",
            success=True,
            data={"variant_id": variant_id, "feedback": feedback, "revised": True, "generated_by": "template"},
        )

    @staticmethod
    def _pick_format(index: int) -> str:
        formats = ["text_image", "carousel", "reel", "text_image"]
        return formats[index % len(formats)]

    @staticmethod
    def _base_hashtags() -> list[str]:
        return ["skincare", "skincareroutine", "genzskincare", "damatdep"]
