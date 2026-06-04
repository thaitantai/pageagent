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

# ── 5 tone personas for GenZ skincare ──
# Each persona has distinct voice, energy, and structure — variants cycle through these.
_TONE_PERSONAS: dict[str, dict[str, str]] = {
    "chia_se_that": {
        "label": "💬 Chia sẻ thật (Real Talk)",
        "description": "Kể chuyện cá nhân — từng sai, từng học, từng thay đổi. Giọng gần gũi, honest, vulnerable. Không dạy đời, chỉ chia sẻ.",
        "hook_example": "Mình từng nghĩ da dầu thì không cần dưỡng ẩm… cho tới khi da đổ dầu nhiều hơn 😅",
        "cta_example": "Bạn có từng mắc sai lầm giống mình không? Kể mình nghe với 👇",
    },
    "chuyen_mon_nhe": {
        "label": "📚 Chuyên môn nhẹ (Light Expert)",
        "description": "Fact-based, trích dẫn bác sĩ/nghiên cứu nhưng nói dễ hiểu. Dùng từ chuyên ngành ít, giải thích bằng analogy.",
        "hook_example": "Bác sĩ da liễu nói gì về toner cho da dầu? 🤔 Mình tóm gọn 3 điều chính đây…",
        "cta_example": "Có bạn nào từng nghe điều này chưa? Cùng thảo luận bên dưới nha!",
    },
    "hai_huoc_meme": {
        "label": "😆 Hài hước / Meme",
        "description": "GenZ humor, meme energy, exaggeration hài hước. Dùng từ lóng nhẹ (\"thảo nào\", \"xỉu up xỉu down\", \"chắc gì\"). KHÔNG nhảm, vẫn có giá trị.",
        "hook_example": "POV: Bạn tưởng toner là 'thần dược' cho da dầu, nhưng sự thật thì… 💀",
        "cta_example": "Ai từng 'thả thính' toner như mình thì vote 1 phát nào 🤣",
    },
    "hoi_dap_tuong_tac": {
        "label": "❓ Hỏi đáp / Tương tác (Interactive)",
        "description": "Post dạng poll, câu hỏi mở, debate. Không đưa đáp án ngay — để GenZ tự trả lời trước, gây tương tác.",
        "hook_example": "Câu hỏi nhanh: Da dầu có NÊN rửa mặt 3 lần/ngày không? 🤔 👇",
        "cta_example": "Các bạn ngh sao? Yes hay No? Comment bên dưới nha!",
    },
    "review_thuc_te": {
        "label": "🔍 Review thực tế (Real Review)",
        "description": "Review honest — nói cả ưu lẫn nhược. Format: đã dùng bao lâu → giá → cảm nhận → kết luận. Không PR.",
        "hook_example": "Mình đã dùng kem chống nắng này 3 tháng — review thật không filter 🎯",
        "cta_example": "Bạn đã dùng sản phẩm nào tương tự chưa? Review cho mình với 🌸",
    },
}

_WRITER_SYSTEM_PROMPT = """Bạn là Copywriter chuyên content skincare/healthcare cho GenZ Việt Nam (18-25 tuổi).

NHIỆM VỤ: Viết caption Facebook thu hút, chân thật, đúng giọng GenZ theo TONE PERSONA được chỉ định.

NGUYÊN TẮC CHUNG:
- Ngắn gọn, dễ hiểu, gần gũi (xưng mình/bạn)
- Kiến thức chuyên môn nhưng không khô khan — lồng kiến thức vào câu chuyện
- KHÔNG phóng đại, KHÔNG hứa hẹn kết quả thần kỳ ("trắng sau 1 tuần", "hết mụn ngay lập tức")
- Mỗi caption có: hook hút → body ngắn → CTA khéo léo
- Luôn kết thúc bằng 1 câu hỏi mở để GenZ vào tương tác

CÁC TONE PERSONA CÓ SẴN (chọn đúng 1 cho mỗi variant):
1. 💬 Chia sẻ thật — Kể chuyện cá nhân, honest, vulnerable. Hook: từng sai → giờ hiểu. CTA: hỏi kinh nghiệm tương tự.
2. 📚 Chuyên môn nhẹ — Fact-based, giải thích dễ hiểu. Hook: bác sĩ nói / nghiên cứu chỉ ra. CTA: cùng thảo luận.
3. 😆 Hài hước / Meme — GenZ humor, exaggeration, từ lóng nhẹ (POV, thảo nào, xỉu). CTA: vote/comment hài.
4. ❓ Hỏi đáp tương tác — Post dạng câu hỏi, debate, poll. KHÔNG đưa đáp án ngay. CTA: Yes/No, bạn nghĩ sao.
5. 🔍 Review thực tế — Review honest: ưu + nhược. Hook: review thật không filter. CTA: bạn đã dùng chưa?

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
- tone_tags: gồm 2-3 từ khóa, PHẢI có tên tone persona được giao (vd: ["chia_sẻ_thật", "gần_gũi"])
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
        """Generate N content variants — LLM or template fallback."""
        now = datetime.now(timezone.utc).isoformat()
        package_id = f"pkg-{uuid.uuid4().hex[:8]}"
        date = scheduled_date or now[:10]
        # ── Smart scheduling: different pillars perform best at different times ──
        pillar_time_map: dict[str, str] = {
            "education": "07:30",    # sáng sớm — tâm lý học hỏi
            "trust": "08:00",        # sáng — xây dựng niềm tin
            "review": "12:00",       # trưa — giờ nghỉ, đọc review
            "entertainment": "19:00",# tối — giải trí, thư giãn
            "engagement": "20:30",   # tối muộn — tương tác cao
        }
        time = scheduled_time or pillar_time_map.get(pillar.strip().lower(), "09:00")

        # ── Assign tone personas round-robin ──
        persona_keys = list(_TONE_PERSONAS.keys())
        assigned: list[tuple[str, str]] = []
        for i in range(count):
            key = persona_keys[i % len(persona_keys)]
            assigned.append((key, _TONE_PERSONAS[key]["label"]))

        # ── Try LLM ──
        if self._llm and topic:
            persona_section = "\n".join(
                f"  Variant {i+1}: TONE = \"{label}\""
                for i, (_, label) in enumerate(assigned)
            )
            prompt = f"""Viết {count} variant caption cho bài đăng Facebook về chủ đề skincare.

Thương hiệu: {self._brand_id}
Chủ đề: {topic}
Pillar: {pillar}
Số lượng variant: {count}

MỖI VARIANT PHẢI DÙNG ĐÚNG TONE PERSONA được chỉ định:

{persona_section}

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
      "tone_tags": ["tone_persona_used", "keyword"],
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
                        hashtags=v.get("hashtags", self._base_hashtags(pillar)),
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

        # ── Template fallback — persona-based contentful variants ──
        variants: list[ContentVariant] = []
        # Each persona gets dedicated hook/caption/cta templates
        persona_templates: dict[str, dict[str, list[str]]] = {
            "chia_se_that": {
                "hooks": [
                    f"Mình từng nghĩ {topic.lower()} khó lắm, nhưng thực ra…",
                    f"Mình đã từng vật lộn với {topic.lower()} suốt mấy tháng 😅",
                    f"Nói thật: mình từng bỏ qua {topic.lower()} vì nghĩ không quan trọng…",
                ],
                "captions": [
                    f"Mình đã từng vật lộn với {topic.lower()} suốt mấy tháng trời. Sau khi tìm hiểu kỹ thì mới nhận ra mình đã sai ngay từ bước cơ bản nhất. Các bạn có gặp tình trạng giống mình không?",
                    f"Đúng là không trải nghiệm thì không biết. Mình từng {topic.lower()} và kết quả thật sự bất ngờ… Kể ra đây để các bạn cùng rút kinh nghiệm nè 👇",
                ],
                "ctas": [
                    "Bạn có từng mắc sai lầm giống mình không? Kể mình nghe với 👇",
                    "Ai từng như mình thì giơ tay nào 🙋",
                ],
            },
            "chuyen_mon_nhe": {
                "hooks": [
                    f"Bạn có biết {topic.lower()} không? 🤔",
                    f"Bác sĩ da liễu nói gì về {topic.lower()}?",
                    f"3 điều mình rút ra về {topic.lower()}",
                ],
                "captions": [
                    f"Hôm nay mình muốn chia sẻ về {topic.lower()}. Không quảng cáo, không PR — chỉ là kiến thức mình tổng hợp từ bác sĩ da liễu và kinh nghiệm thực tế. Cùng nhau học nha 🌸",
                    f"Đây là những gì mình học được về {topic.lower()} sau thời gian tìm hiểu. Có thể bạn sẽ bất ngờ đấy! Dưới góc nhìn chuyên môn nhẹ, dễ hiểu ✨",
                ],
                "ctas": [
                    "Có bạn nào từng nghe điều này chưa? Cùng thảo luận bên dưới nha!",
                    "Bạn nghĩ sao về thông tin này? Comment góp ý nhé 👇",
                ],
            },
            "hai_huoc_meme": {
                "hooks": [
                    f"POV: Bạn nghĩ {topic.lower()} là chuyện đơn giản 💀",
                    f"Thảo nào {topic.lower()} — mình tưởng biết hết rồi…",
                ],
                "captions": [
                    f"Xỉu up xỉu down khi phát hiện ra sự thật về {topic.lower()} 😵 Thôi thì chia sẻ để các bạn khỏi mắc sai lầm như mình. Đọc xong nhớ cmt cảm nghĩ nha 🤣",
                    f"Sự thật thì {topic.lower()} không hề khó như bạn nghĩ đâu. Mình cũng từng 'gà mờ' như ai — nhưng giờ đã có kinh nghiệm để kể lại rồi. Đọc xong bạn sẽ thấy 'ngộ' ra nhiều điều 😆",
                ],
                "ctas": [
                    "Ai từng 'thả thính' như mình thì vote 1 phát nào 🤣",
                    "Bạn có 'gà mờ' y như mình hồi xưa không? Comment kể đi 👇",
                ],
            },
            "hoi_dap_tuong_tac": {
                "hooks": [
                    f"Câu hỏi nhanh: {topic.title()} có thực sự quan trọng? 🤔",
                    f"Nhanh — bạn nghĩ {topic.lower()} nên làm ngay hay không?",
                ],
                "captions": [
                    f"Mình đố các bạn: {topic.lower()} — có hay không? Trả lời trước khi đọc phần dưới đây nha 👇",
                ],
                "ctas": [
                    "Các bạn ngh sao? Yes hay No? Comment bên dưới nha!",
                    "Bạn có đồng ý không? Mình rất muốn nghe ý kiến trái chiều 👇",
                ],
            },
            "review_thuc_te": {
                "hooks": [
                    f"Review thật: {topic.lower()} — có đáng tiền?",
                    f"Mình dùng thử {topic.lower()} trong thời gian dài và đây là sự thật 🎯",
                ],
                "captions": [
                    f"Review thật không filter về {topic.lower()}: ưu điểm, nhược điểm, và kết luận sau thời gian sử dụng. Mình không PR, chỉ nói những gì mình trải nghiệm. Ai quan tâm thì đọc thử nhé!",
                ],
                "ctas": [
                    "Bạn đã dùng sản phẩm nào tương tự chưa? Review cho mình với 🌸",
                    "Có bạn nào có trải nghiệm khác không? Chia sẻ để mọi người cùng biết nha 👇",
                ],
            },
        }

        import random
        for i in range(count):
            persona_key, persona_label = assigned[i]
            templates = persona_templates[persona_key]
            variant_id = f"var-{package_id}-{i}"
            hook = random.choice(templates["hooks"])
            caption = random.choice(templates["captions"])
            cta = random.choice(templates["ctas"])
            variants.append(ContentVariant(
                variant_id=variant_id,
                topic=topic,
                pillar=pillar,
                caption=caption,
                hook=hook,
                cta=cta,
                format=self._pick_format(i),
                tone_tags=[persona_key.replace("_", "_thật" if persona_key == "chia_se_that" else "_nhẹ" if persona_key == "chuyen_mon_nhe" else "_meme" if persona_key == "hai_huoc_meme" else "_tương_tác" if persona_key == "hoi_dap_tuong_tac" else "_thực_tế"), "chia_sẻ"],
                hashtags=self._base_hashtags(pillar),
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
    def _base_hashtags(pillar: str = "") -> list[str]:
        """Base hashtags with pillar-specific additions for better discoverability."""
        base: list[str] = ["skincare", "skincareroutine", "genzskincare", "damatdep"]

        pillar_map: dict[str, list[str]] = {
            "education": ["skincaretips", "hocskincare", "chamsocdatainha"],
            "review": ["reviewthat", "reviewmypham", "dungthu"],
            "trust": ["skincaretips", "myphamchatluong", "damatdep"],
            "engagement": ["hoctap", "cunghocskincare", "genzlife"],
            "entertainment": ["genzhumor", "skincarefunny", "trending"],
        }

        key = pillar.strip().lower()
        extra = pillar_map.get(key, ["chamsocda", "lamdepcunggenz"])
        return base + extra
