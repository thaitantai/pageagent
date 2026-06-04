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

_WRITER_SYSTEM_PROMPT = """Bạn là Copywriter chuyên content skincare/healthcare cho GenZ Việt Nam (18-25 tuổi).

NHIỆM VỤ: Viết caption Facebook thu hút, chân thật, đúng giọng GenZ.

NGUYÊN TẮC:
- Ngắn gọn, dễ hiểu, gần gũi (xưng mình/bạn)
- Kiến thức chuyên môn nhưng không khô khan — lồng kiến thức vào câu chuyện
- GenZ tone: tự nhiên, có cảm xúc, hài hước nhẹ khi phù hợp
- KHÔNG phóng đại, KHÔNG hứa hẹn kết quả thần kỳ ("trắng sau 1 tuần", "hết mụn ngay lập tức")
- Mỗi caption có: hook hút → body ngắn → CTA khéo léo
- Luôn kết thúc bằng 1 câu hỏi mở để GenZ vào tương tác

VÍ DỤ GIỌNG VIẾT TỐT:
• "Mình từng nghĩ toner là bước không thể thiếu cho da dầu… cho tới khi đọc nghiên cứu của bác sĩ da liễu 🤯 Mọi người có biết da dầu thực ra cần gì nhất không?"
• "Review thật: Kem chống nắng 100k mình dùng suốt 3 tháng qua — được cái chống nắng tốt, mỏng nhẹ. Nhưng có điểm trừ là… 👇"
• "Có bạn nào từng mua serum vì thấy quảng cáo 'trắng sau 7 ngày' chưa? Mình xin phép nói thật nhé 🙈 Dưới góc nhìn của một người làm trong ngành…"

VÍ DỤ GIỌNG VIẾT CẦN TRÁNH:
• Quá quảng cáo: "Sản phẩm này là số 1 thị trường…" ❌
• Mơ hồ: "Chăm sóc da đúng cách mỗi ngày" ❌
• Quá dài dòng: viết 3-4 đoạn văn không điểm nhấn ❌

YÊU CẦU BẮT BUỘC:
- Hook (câu mở): gây tò mò, chạm cảm xúc, hoặc đặt câu hỏi
- Caption: 2-3 câu ngắn, có emoji, tự nhiên
- CTA: 1 câu hỏi tương tác cuối bài (không kêu gọi mua hàng)
- tone_tags: list 2-3 từ khóa mô tả tone (vd: chia_sẻ, chuyên_môn, hài_hước, review, hỏi_đáp)
- Hashtags: #skincare #skincareroutine #genzskincare + 2-3 tag liên quan chi tiết (vd: #dau #trimun #duongam)

FORMATS: text_image (ảnh + chữ), carousel (nhiều ảnh), reel (video).

Trả lời bằng JSON thuần, không markdown. KHÔNG để trống field nào."""


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
            data = self._llm.generate_json(
                _WRITER_SYSTEM_PROMPT, prompt,
                max_tokens=3000,
                temperature=0.7,
            )
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

        # ── Template fallback — contentful variants ──
        variants: list[ContentVariant] = []
        hook_templates = [
            f"Mình từng nghĩ {topic.lower()} khó lắm, nhưng thực ra…",
            f"Bạn có biết {topic.lower()} không? 🤔",
            f"3 điều mình rút ra về {topic.lower()}",
            f"Nói thật nhé: {topic.lower()} — có đáng tiền?",
            f"{topic.title()} — mình đã thử và đây là kết quả",
        ]
        caption_templates = [
            f"Mình đã từng vật lộn với {topic.lower()} suốt mấy tháng trời. Sau khi tìm hiểu kỹ thì mới nhận ra mình đã sai ngay từ bước cơ bản nhất. Các bạn có gặp tình trạng giống mình không?",
            f"Hôm nay mình muốn chia sẻ thật lòng về {topic.lower()}. Không quảng cáo, không PR — chỉ là kinh nghiệm thực tế sau thời gian dài trải nghiệm. Ai quan tâm thì cùng thảo luận nhé 👇",
            f"Nếu bạn cũng đang băn khoăn về {topic.lower()}, thì bài này dành cho bạn. Mình tổng hợp từ kinh nghiệm cá nhân và tư vấn của bác sĩ da liễu. Cùng xem có gì thú vị nha!",
        ]
        cta_templates = [
            "Bạn đã thử cách này chưa? Chia sẻ trải nghiệm của bạn bên dưới nhé 👇",
            "Có bạn nào từng gặp tình trạng tương tự không? Cùng thảo luận nha!",
            "Bạn nghĩ sao về điều này? Mình rất muốn nghe ý kiến của mọi người 🌸",
        ]

        import random
        for i in range(count):
            variant_id = f"var-{package_id}-{i}"
            hook = random.choice(hook_templates)
            caption = random.choice(caption_templates)
            cta = random.choice(cta_templates)
            variants.append(ContentVariant(
                variant_id=variant_id,
                topic=topic,
                pillar=pillar,
                caption=caption,
                hook=hook,
                cta=cta,
                format=self._pick_format(i),
                tone_tags=["chia_sẻ", "chuyên_môn"],
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
            data = self._llm.generate_json(
                _WRITER_SYSTEM_PROMPT, prompt,
                max_tokens=1500,
                temperature=0.8,
            )
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
            data = self._llm.generate_json(
                _WRITER_SYSTEM_PROMPT, prompt,
                max_tokens=2000,
                temperature=0.6,
            )
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
