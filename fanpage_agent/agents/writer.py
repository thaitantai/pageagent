"""WriterAgent - generates multi-variant content captions for A/B testing.

Uses LLM (via LLMAdapter) to write real captions in GenZ skincare voice.
Falls back to empty variants if no LLM is configured.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fanpage_agent.adapters.llm_adapter import LLMAdapter
from fanpage_agent.core.agent import BaseAgent
from fanpage_agent.core.types import (
    ActionPriority,
    AgentResult,
    AgentRole,
    AgentTask,
    ContentPackage,
    ContentVariant,
)
from fanpage_agent.prompts._loader import PromptLoader
from fanpage_agent.research_handoff import normalize_research_handoff


def _extract_research_grounding(
    research_packet: dict[str, Any] | None,
) -> tuple[str, list[dict[str, Any]], str]:
    """Return concise writer grounding from a ResearchPacket-shaped dict."""
    if not research_packet:
        return "", [], ""
    handoff = normalize_research_handoff(research_packet)
    refs = [
        item for item in handoff.get("evidence_refs", []) if isinstance(item, dict)
    ]
    packet_id = str(handoff.get("packet_id", ""))
    lines = [f"- {ref['claim']} (source: {ref['source']})" for ref in refs if ref.get("claim")]
    return "\n".join(lines), refs, packet_id


def _normalise_page_context(page_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(page_context, dict):
        return {}
    allowed = {
        "page_id",
        "name",
        "topic_focus",
        "community_value",
        "target_audience",
        "content_tone",
        "quality_standards",
        "posting_frequency",
    }
    return {key: value for key, value in page_context.items() if key in allowed and value}


# ── 5 tone personas for GenZ skincare ──
# Each persona has distinct voice, energy, and structure - variants cycle through these.
_TONE_PERSONAS: dict[str, dict[str, str]] = {
    "chia_se_that": {
        "label": "💬 Chia sẻ thật (Real Talk)",
        "description": "Kể chuyện cá nhân - từng sai, từng học, từng thay đổi. Giọng gần gũi, honest, vulnerable. Không dạy đời, chỉ chia sẻ.",
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
        "description": 'GenZ humor, meme energy, exaggeration hài hước. Dùng từ lóng nhẹ ("thảo nào", "xỉu up xỉu down", "chắc gì"). KHÔNG nhảm, vẫn có giá trị.',
        "hook_example": "POV: Bạn tưởng toner là 'thần dược' cho da dầu, nhưng sự thật thì… 💀",
        "cta_example": "Ai từng 'thả thính' toner như mình thì vote 1 phát nào 🤣",
    },
    "hoi_dap_tuong_tac": {
        "label": "❓ Hỏi đáp / Tương tác (Interactive)",
        "description": "Post dạng poll, câu hỏi mở, debate. Không đưa đáp án ngay - để GenZ tự trả lời trước, gây tương tác.",
        "hook_example": "Câu hỏi nhanh: Da dầu có NÊN rửa mặt 3 lần/ngày không? 🤔 👇",
        "cta_example": "Các bạn ngh sao? Yes hay No? Comment bên dưới nha!",
    },
    "review_thuc_te": {
        "label": "🔍 Review thực tế (Real Review)",
        "description": "Review honest - nói cả ưu lẫn nhược. Format: đã dùng bao lâu → giá → cảm nhận → kết luận. Không PR.",
        "hook_example": "Mình đã dùng kem chống nắng này 3 tháng - review thật không filter 🎯",
        "cta_example": "Bạn đã dùng sản phẩm nào tương tự chưa? Review cho mình với 🌸",
    },
}


def _writer_system_prompt() -> str:
    return PromptLoader.load("writer_system.md")


class WriterAgent(BaseAgent):
    """Writer - generates N variants of a content post using LLM or template."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        brand_id: str = "skincare_genz",
        default_variants: int = 2,
        llm: LLMAdapter | None = None,
        memory_dir: str = "data/agent",
    ) -> None:
        super().__init__(config)
        self._brand_id = brand_id
        self._default_variants = default_variants
        self._llm = llm
        self._memory_dir = memory_dir

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
            result = self._write_variants(
                topic=params.get("topic", ""),
                pillar=params.get("pillar", ""),
                count=params.get("variants", self._default_variants),
                scheduled_date=params.get("scheduled_date"),
                scheduled_time=params.get("scheduled_time"),
                page_context=_normalise_page_context(params.get("page_context")),
                research_packet=params.get("research_packet"),
            )
            if result.success:
                pkg = result.data
                self._mark_shared_done(
                    processed_strategy_version=self._pipeline_version("strategist"),
                    package_id=getattr(pkg, "package_id", None),
                    pillar=getattr(pkg, "pillar", params.get("pillar", "")),
                    variant_count=len(getattr(pkg, "variants", [])),
                    scheduled_date=getattr(pkg, "scheduled_date", None),
                )
            return result
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

    def self_driving_tick(self) -> list[tuple[str, dict, ActionPriority]]:
        """Propose writing: respond to new strategy, or periodic timer.

        Choreography: if Strategist has produced a new schedule, Writer
        generates content variants for the first pending topic.
        Periodic fallback for regular content generation.
        """
        proposals: list[tuple[str, dict, ActionPriority]] = []

        # Check for new strategy data (choreography chain)
        if self._has_upstream_data("strategist", "processed_strategy_version"):
            strategy_data = self._get_shared("strategist", {})
            schedule = strategy_data.get("schedule", [])
            if schedule:
                # Pick first scheduled item
                item = schedule[0]
                proposals.append(
                    (
                        "write_variants",
                        {
                            "topic": item.get("topic_template", "Chăm sóc da GenZ"),
                            "pillar": item.get("pillar", "skincare_routine"),
                            "variants": 2,
                        },
                        ActionPriority.MEDIUM,
                    )
                )
            else:
                proposals.append(("write_variants", {"variants": 2}, ActionPriority.MEDIUM))
        elif self._should_act("write_variants", 21600):
            # Periodic fallback: write without new strategy
            proposals.append(("write_variants", {"variants": 2}, ActionPriority.MEDIUM))

        return proposals

    def _write_variants(
        self,
        topic: str,
        pillar: str,
        count: int,
        scheduled_date: str | None,
        scheduled_time: str | None,
        page_context: dict[str, Any] | None = None,
        research_packet: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Generate N content variants - LLM or template fallback."""
        now = datetime.now(timezone.utc).isoformat()
        package_id = f"pkg-{uuid.uuid4().hex[:8]}"
        date = scheduled_date or now[:10]
        # ── Smart scheduling: different pillars perform best at different times ──
        pillar_time_map: dict[str, str] = {
            "education": "07:30",  # sáng sớm - tâm lý học hỏi
            "trust": "08:00",  # sáng - xây dựng niềm tin
            "review": "12:00",  # trưa - giờ nghỉ, đọc review
            "entertainment": "19:00",  # tối - giải trí, thư giãn
            "engagement": "20:30",  # tối muộn - tương tác cao
        }
        time = scheduled_time or pillar_time_map.get(pillar.strip().lower(), "09:00")
        page_context = _normalise_page_context(page_context)
        evidence_text, evidence_refs, research_packet_id = _extract_research_grounding(
            research_packet
        )
        handoff = normalize_research_handoff(research_packet)
        if handoff.get("safe_use") == "draft_questions_only":
            reasons = handoff.get("gate_reasons") or ["research evidence gate blocked writer claims"]
            return AgentResult(
                task_id=f"write-{package_id}",
                success=False,
                error="Evidence gate blocked writer claims: "
                + "; ".join(str(item) for item in reasons),
            )
        page_id = str(page_context.get("page_id", ""))

        # ── Tick offset for format rotation across days ──
        tick_offset = sum(int(part) for part in date.split("-"))

        # ── Assign tone personas round-robin ──
        persona_keys = list(_TONE_PERSONAS.keys())
        assigned: list[tuple[str, str]] = []
        for i in range(count):
            key = persona_keys[i % len(persona_keys)]
            assigned.append((key, _TONE_PERSONAS[key]["label"]))

        # ── Try LLM ──
        if self._llm and topic:
            persona_section = "\n".join(
                f'  Variant {i + 1}: TONE = "{label}"' for i, (_, label) in enumerate(assigned)
            )
            brand_id = self._brand_id
            page_context_str = str(page_context or "khong co")
            evidence_text_val = (
                evidence_text
                or "- Khong co evidence; viet can trong va noi ro la goc nhin tong hop."
            )
            prompt = PromptLoader.format(
                "writer_user_variants.md",
                count=count,
                topic=topic,
                pillar=pillar,
                brand_id=brand_id,
                page_context_str=page_context_str,
                evidence_text=evidence_text_val,
                persona_section=persona_section,
            )

            data = self._llm.generate_json(
                _writer_system_prompt(),
                prompt,
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
                        format=v.get("format", self._pick_format(i, tick_offset)),
                        tone_tags=v.get("tone_tags", []),
                        hashtags=v.get("hashtags") or self._base_hashtags(pillar, tick_offset),
                        visual_brief=v.get("visual_brief", None),
                        evidence_refs=evidence_refs,
                    )
                    for i, v in enumerate(data["variants"][:count])
                ]

                # ── Quality scoring - auto-fail low-quality variants ──
                try:
                    scored = self._score_variants(variants, topic)
                    low = [v for v in scored if v.get("score", 5) < 3.0]
                    if low and self._llm:
                        # regenerate low scorers with higher temperature
                        retry_prompt = (
                            prompt
                            + f"\n\n⚠️ {len(low)} variant(s) failed quality check (score < 3.0). Regenerate specifically variant #{[scored.index(v) + 1 for v in low]} with stronger hook, clearer value, and a more engaging CTA. BE MORE CREATIVE."
                        )
                        retry_data = self._llm.generate_json(
                            _writer_system_prompt(),
                            retry_prompt,
                            max_tokens=3000,
                            temperature=0.85,
                        )
                        if retry_data and "variants" in retry_data:
                            # merge retry results back
                            for ri, rv in enumerate(retry_data["variants"][:count]):
                                if ri < len(variants):
                                    variants[ri] = ContentVariant(
                                        variant_id=f"var-{package_id}-{ri}",
                                        topic=rv.get("topic", topic),
                                        pillar=rv.get("pillar", pillar),
                                        caption=rv.get("caption", variants[ri].caption),
                                        hook=rv.get("hook", variants[ri].hook),
                                        cta=rv.get("cta", variants[ri].cta),
                                        format=rv.get("format", self._pick_format(ri, tick_offset)),
                                        tone_tags=rv.get("tone_tags", variants[ri].tone_tags),
                                        hashtags=rv.get(
                                            "hashtags", self._base_hashtags(pillar, tick_offset)
                                        ),
                                    )
                except Exception:
                    pass  # scoring is best-effort, never block publishing

                return AgentResult(
                    task_id=f"write-{package_id}",
                    success=True,
                    data=ContentPackage(
                        package_id=package_id,
                        brand_id=self._brand_id,
                        scheduled_date=date,
                        scheduled_time=time,
                        variants=variants,
                        page_id=page_id,
                        page_context=page_context,
                        research_packet_id=research_packet_id,
                        status="draft",
                    ),
                )

        # ── Visual brief templates for each persona × format combo ──
        _VISUAL_BRIEFS: dict[str, dict[str, list[str]]] = {
            "chia_se_that": {
                "text_image": [
                    "Ảnh selfie gần gũi, ánh sáng tự nhiên, background phòng ngủ/bàn học. Tone màu ấm (beige/cream). Chân thật, không chỉnh filter quá tay.",
                    "Ảnh close-up sản phẩm trên bàn gỗ, có tay cầm điện thoại chụp. Cảm giác 'đang dùng thực tế'. Không dàn dựng quá chuyên nghiệp.",
                ],
                "carousel": [
                    "Carousel 3-4 slide: (1) Ảnh chân dung + quote cảm xúc, (2) Sản phẩm/dụng cụ trên bàn, (3) Mẹo/tip list. Font chữ tay viết, background pastel.",
                    "Carousel kiểu 'before & insight': (1) Biểu cảm ngạc nhiên, (2) Sản phẩm zoom nhẹ, (3) Kết luận. Màu hồng đất + cam đào.",
                ],
                "reel": [
                    "Cảnh quay ngắn 15s: thoại kể chuyện, cut cảnh sản phẩm. Âm thanh tự nhiên, beat nhẹ. Chân thật, không kịch bản.",
                ],
            },
            "chuyen_mon_nhe": {
                "text_image": [
                    "Ảnh minh họa kiểu infographic đơn giản: biểu tượng + chữ trên nền trắng/xanh nhạt. Phong cách clean, medical aesthetic.",
                    "Ảnh sản phẩm trên nền marble/gỗ sáng, có chú thích chuyên môn nhỏ. Cảm giác đáng tin cậy, chuyên nghiệp.",
                ],
                "carousel": [
                    "Carousel 3 slide kiểu 'học nhanh': (1) Tiêu đề + icon, (2) Nội dung chính dạng bullet, (3) Tóm tắt + cta. Màu xanh mint + trắng.",
                    "Carousel 4 slide chia theo bước: (1) Giới thiệu vấn đề, (2) Giải thích, (3) Cách áp dụng, (4) Kết luận. Font Helvetica/Lato.",
                ],
                "reel": [
                    "Cảnh quay 'giải thích nhanh' 30s: mặt + key text overlay (không thoại). Nhạc nền chill lofi. Màu xanh mint chủ đạo.",
                ],
            },
            "hai_huoc_meme": {
                "text_image": [
                    "Ảnh meme-style: chụp màn hình tweet/reddit hoặc ảnh chế có caption. Màu sặc sỡ, font Impact hoặc Comic Sans. GenZ humor energy.",
                    "Ảnh 'hai mặt' (before vs after) hoặc POV: chia đôi ảnh, bên trái sai/bên phải đúng. Style meme Việt Nam quen thuộc.",
                ],
                "carousel": [
                    "Carousel kiểu 'storytime hài': (1) Mở đầu kịch tính với icon mặt cười, (2) Plot twist ảnh chế, (3) Kết luận + reaction meme. Tone vàng/tím neon.",
                ],
                "reel": [
                    "Cảnh quay 'POV' 15s: quay từ góc nhìn thứ nhất, có chèn meme sound effect. Style TikTok GenZ. Cắt nhanh, nhạc trend.",
                ],
            },
            "hoi_dap_tuong_tac": {
                "text_image": [
                    "Ảnh dạng poll/câu hỏi big text: nền gradient trắng-xanh, chữ to, dấu hỏi lớn. Khoảng trống để comment.",
                    "Ảnh 'This or That': chia đôi ảnh, bên trái option A/bên phải option B. Kêu gọi vote trong comment.",
                ],
                "carousel": [
                    "Carousel 2 slide: (1) Câu hỏi lớn giữa màn hình, (2) Gợi ý trả lời + lời kêu gọi tag bạn bè. Màu cam/tím pastel.",
                ],
                "reel": [
                    "Cảnh quay đặt câu hỏi 10s: nhìn vào camera, hỏi trực tiếp. Overlay chữ to. Beat chờ đợi hồi hộp.",
                ],
            },
            "review_thuc_te": {
                "text_image": [
                    "Ảnh 'review haul': sản phẩm trải trên bàn, kèm chú thích tay. Phong cách lifestyle blog. Màu trung tính, ánh sáng cửa sổ.",
                    "Ảnh chụp sản phẩm chính diện + list pros/cons bên cạnh. Dạng 'honest review card'. Font viết tay.",
                ],
                "carousel": [
                    "Carousel 4-5 slide đánh giá chi tiết: (1) Ảnh sản phẩm + điểm, (2) Kết cấu/bao bì, (3) Cảm nhận khi dùng, (4) Pros & Cons, (5) Kết luận + điểm số. Màu xám sáng + xanh lá nhẹ.",
                ],
                "reel": [
                    "Cảnh quay 'unboxing + review' 30s: cầm sản phẩm quay gần, thoại đánh giá thật. Không kịch bản, quay tay. Ánh sáng tự nhiên.",
                ],
            },
        }

        # ── Template fallback - persona-based contentful variants ──
        variants: list[ContentVariant] = []
        persona_templates: dict[str, dict[str, list[str]]] = {
            "chia_se_that": {
                "hooks": [
                    f"Mình từng nghĩ {topic.lower()} khó lắm, nhưng thực ra…",
                    f"Mình đã từng vật lộn với {topic.lower()} suốt mấy tháng 😅",
                    f"Nói thật: mình từng bỏ qua {topic.lower()} vì nghĩ không quan trọng…",
                    f"Hôm qua mình mới ngồi nghĩ lại về {topic.lower()}…",
                    f"Có bạn nào như mình không: sợ {topic.lower()} vì sợ sai?",
                    f"Mình từng sai rất nhiều về {topic.lower()}, giờ mới biết đúng là…",
                ],
                "captions": [
                    f"Mình đã từng vật lộn với {topic.lower()} suốt mấy tháng trời. Sau khi tìm hiểu kỹ thì mới nhận ra mình đã sai ngay từ bước cơ bản nhất. Các bạn có gặp tình trạng giống mình không?",
                    f"Đúng là không trải nghiệm thì không biết. Mình từng {topic.lower()} và kết quả thật sự bất ngờ… Kể ra đây để các bạn cùng rút kinh nghiệm nè 👇",
                    f"Phải công nhận {topic.lower()} không hề dễ như mình tưởng. Qua bao lần 'thử và sai', cuối cùng mình cũng tìm ra cách ổn nhất. Các bạn thì sao?",
                    f"Chuyện là mình từng khá tự tin về {topic.lower()}, cho tới khi một người bạn trong ngành chỉ ra mình sai cơ bản. Bài học đắt giá nhưng đáng 😅",
                ],
                "ctas": [
                    "Bạn có từng mắc sai lầm giống mình không? Kể mình nghe với 👇",
                    "Ai từng như mình thì giơ tay nào 🙋",
                    "Kinh nghiệm của bạn về vụ này là gì? Chia sẻ để mọi người cùng học nha 🌸",
                    "Bạn có tips gì hay hơn không? Comment bên dưới để mình học hỏi với 👇",
                ],
            },
            "chuyen_mon_nhe": {
                "hooks": [
                    f"Bạn có biết {topic.lower()} không? 🤔",
                    f"Bác sĩ da liễu nói gì về {topic.lower()}?",
                    f"3 điều mình rút ra về {topic.lower()}",
                    f"Nghiên cứu mới chỉ ra: {topic.lower()} quan trọng hơn bạn nghĩ",
                    f"99% người làm sai {topic.lower()} - bạn có thuộc số đó?",
                    f"Mình hỏi bác sĩ về {topic.lower()} và đây là câu trả lời 🎯",
                ],
                "captions": [
                    f"Hôm nay mình muốn chia sẻ về {topic.lower()}. Không quảng cáo, không PR - chỉ là kiến thức mình tổng hợp từ bác sĩ da liễu và kinh nghiệm thực tế. Cùng nhau học nha 🌸",
                    f"Đây là những gì mình học được về {topic.lower()} sau thời gian tìm hiểu. Có thể bạn sẽ bất ngờ đấy! Dưới góc nhìn chuyên môn nhẹ, dễ hiểu ✨",
                    f"Mình đọc được nghiên cứu thú vị về {topic.lower()}. Dịch ra tiếng Việt dễ hiểu cho các bạn đây - cực kỳ hữu ích cho ai quan tâm skincare khoa học 📚",
                    f"Bác sĩ da liễu khuyên gì về {topic.lower()}? Mình tóm gọn lại bằng ngôn ngữ dễ hiểu nhất - không dùng từ chuyên ngành rối rắm ✨",
                ],
                "ctas": [
                    "Có bạn nào từng nghe điều này chưa? Cùng thảo luận bên dưới nha!",
                    "Bạn nghĩ sao về thông tin này? Comment góp ý nhé 👇",
                    "Bạn có biết thêm nghiên cứu nào khác không? Chia sẻ cho mình với 🌸",
                    "Ai muốn mình phân tích sâu hơn về chủ đề này thì thả 🔥 nha!",
                ],
            },
            "hai_huoc_meme": {
                "hooks": [
                    f"POV: Bạn nghĩ {topic.lower()} là chuyện đơn giản 💀",
                    f"Thảo nào {topic.lower()} - mình tưởng biết hết rồi…",
                    f"{topic.title()} be like: 'Tưởng dễ, hóa ra khó vãi' 😆",
                    f"Mình cười mình mất 2 năm mới hiểu {topic.lower()} 🤡",
                    f"Có một nhóm người: nghĩ {topic.lower()} chỉ dành cho… 😂",
                ],
                "captions": [
                    f"Xỉu up xỉu down khi phát hiện ra sự thật về {topic.lower()} 😵 Thôi thì chia sẻ để các bạn khỏi mắc sai lầm như mình. Đọc xong nhớ cmt cảm nghĩ nha 🤣",
                    f"Sự thật thì {topic.lower()} không hề khó như bạn nghĩ đâu. Mình cũng từng 'gà mờ' như ai - nhưng giờ đã có kinh nghiệm để kể lại rồi. Đọc xong bạn sẽ thấy 'ngộ' ra nhiều điều 😆",
                    f"Nói thiệt: {topic.lower()} mà biết sớm thì mình đỡ tốn bao nhiêu tiền vô ích rồi. Thôi thì 'better late than never' - chia sẻ để các bạn đỡ khổ 😂👇",
                ],
                "ctas": [
                    "Ai từng 'thả thính' như mình thì vote 1 phát nào 🤣",
                    "Bạn có 'gà mờ' y như mình hồi xưa không? Comment kể đi 👇",
                    "Ai thấy mình nói đúng thì share cho bạn bè cười cùng nha 😆",
                ],
            },
            "hoi_dap_tuong_tac": {
                "hooks": [
                    f"Câu hỏi nhanh: {topic.title()} có thực sự quan trọng? 🤔",
                    f"Nhanh - bạn nghĩ {topic.lower()} nên làm ngay hay không?",
                    f"1 câu hỏi cho các bạn: {topic.title()} - CÓ hay KHÔNG? 👇",
                ],
                "captions": [
                    f"Mình đố các bạn: {topic.lower()} - có hay không? Trả lời trước khi đọc phần dưới đây nha 👇",
                    f"Trước khi đọc tiếp, hãy dừng lại 3 giây và tự hỏi: mình có đang làm {topic.lower()} đúng cách không? 🤔 Không thì comment ngay để mình chỉ cho 👇",
                ],
                "ctas": [
                    "Các bạn ngh sao? Yes hay No? Comment bên dưới nha!",
                    "Bạn có đồng ý không? Mình rất muốn nghe ý kiến trái chiều 👇",
                    "Có ai nghĩ khác không? Cmt tranh luận vui vẻ nha 🌸",
                ],
            },
            "review_thuc_te": {
                "hooks": [
                    f"Review thật: {topic.lower()} - có đáng tiền?",
                    f"Mình dùng thử {topic.lower()} trong thời gian dài và đây là sự thật 🎯",
                    f"Không filter, không PR - trải nghiệm thật của mình với {topic.lower()}",
                ],
                "captions": [
                    f"Review thật không filter về {topic.lower()}: ưu điểm, nhược điểm, và kết luận sau thời gian sử dụng. Mình không PR, chỉ nói những gì mình trải nghiệm. Ai quan tâm thì đọc thử nhé!",
                    f"Mình đã dùng {topic.lower()} khá lâu rồi, hôm nay ngồi viết lại cảm nhận thật. Có điểm tốt, có điểm chưa ổn - nhưng quan trọng là HONEST. Bạn nào đang phân vân thì tham khảo nha 🌸",
                ],
                "ctas": [
                    "Bạn đã dùng sản phẩm nào tương tự chưa? Review cho mình với 🌸",
                    "Có bạn nào có trải nghiệm khác không? Chia sẻ để mọi người cùng biết nha 👇",
                    "Bạn có muốn mình review thêm sản phẩm nào khác không? Gợi ý bên dưới nha!",
                ],
            },
        }

        for i in range(count):
            persona_key, persona_label = assigned[i]
            templates = persona_templates[persona_key]
            variant_id = f"var-{package_id}-{i}"
            fmt = self._pick_format(i, tick_offset)
            # Rotate hooks/captions/ctas by (tick_offset + i) for diversity across ticks
            hook = templates["hooks"][(tick_offset + i) % len(templates["hooks"])]
            caption = templates["captions"][(tick_offset + i) % len(templates["captions"])]
            if evidence_refs:
                caption = f"{caption} Mình dựa trên nguồn: {evidence_refs[0].get('source', 'research')} - {evidence_refs[0].get('claim', '')}."
            if page_context.get("community_value"):
                caption = (
                    f"{caption} Gắn với mục tiêu cộng đồng: {page_context['community_value']}."
                )
            cta = templates["ctas"][(tick_offset + i) % len(templates["ctas"])]
            # Rotate visual briefs
            brief_pool = _VISUAL_BRIEFS.get(persona_key, {}).get(fmt, [""])
            visual_brief = brief_pool[(tick_offset + i) % len(brief_pool)] if brief_pool else None
            variants.append(
                ContentVariant(
                    variant_id=variant_id,
                    topic=topic,
                    pillar=pillar,
                    caption=caption,
                    hook=hook,
                    cta=cta,
                    format=fmt,
                    visual_brief=visual_brief or None,
                    tone_tags=[
                        persona_key.replace(
                            "_",
                            "_thật"
                            if persona_key == "chia_se_that"
                            else "_nhẹ"
                            if persona_key == "chuyen_mon_nhe"
                            else "_meme"
                            if persona_key == "hai_huoc_meme"
                            else "_tương_tác"
                            if persona_key == "hoi_dap_tuong_tac"
                            else "_thực_tế",
                        ),
                        "chia_sẻ",
                    ],
                    hashtags=self._base_hashtags(pillar, tick_offset),
                    evidence_refs=evidence_refs,
                )
            )

        return AgentResult(
            task_id=f"write-{package_id}",
            success=True,
            data=ContentPackage(
                package_id=package_id,
                brand_id=self._brand_id,
                scheduled_date=date,
                scheduled_time=time,
                variants=variants,
                page_id=page_id,
                page_context=page_context,
                research_packet_id=research_packet_id,
                status="draft",
            ),
        )

    def _generate_hooks(self, topic: str, count: int) -> AgentResult:
        """Generate N hook options - LLM or template fallback."""
        if self._llm and topic:
            prompt = PromptLoader.format(
                "writer_user_hooks.md",
                count=count,
                topic=topic,
            )
            data = self._llm.generate_json(
                _writer_system_prompt(),
                prompt,
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
            f"Review thật: {topic.title()} - có đáng tiền?",
            f"Bác sĩ da liễu nói gì về {topic.lower()}?",
        ]
        return AgentResult(
            task_id=f"hooks-{topic[:20]}",
            success=True,
            data={
                "hooks": hooks[:count],
                "count": min(len(hooks), count),
                "generated_by": "template",
            },
        )

    def _rewrite_variant(self, variant_id: str, feedback: str) -> AgentResult:
        """Revise a variant - LLM rewrite or stub."""
        if self._llm and feedback:
            prompt = PromptLoader.format(
                "writer_user_rewrite.md",
                variant_id=variant_id,
                feedback=feedback,
            )
            data = self._llm.generate_json(
                _writer_system_prompt(),
                prompt,
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
            data={
                "variant_id": variant_id,
                "feedback": feedback,
                "revised": True,
                "generated_by": "template",
            },
        )

    @staticmethod
    def _score_variants(variants: list[ContentVariant], topic: str) -> list[dict]:
        """Lightweight heuristic scoring - no LLM call, checks structure and completeness."""
        results: list[dict] = []
        for v in variants:
            score = 5.0
            reasons: list[str] = []

            # hook quality
            hook = (v.hook or "").strip()
            if len(hook) < 10:
                score -= 1.5
                reasons.append("hook_too_short")
            if not any(c in hook for c in "?!~😅🤔💀🎯👇"):
                score -= 0.5
                reasons.append("hook_no_emotional_punch")

            # caption quality
            cap = (v.caption or "").strip()
            if len(cap) < 30:
                score -= 1.5
                reasons.append("caption_too_short")
            if "?" not in cap:
                score -= 0.5
                reasons.append("caption_no_question")
            if not any(c in cap for c in "😅🤔😂🌸✨💀👇🎯🔥"):
                score -= 0.3
                reasons.append("caption_no_emoji")

            # CTA quality
            cta = (v.cta or "").strip()
            if len(cta) < 10:
                score -= 1.0
                reasons.append("cta_too_short")
            if "?" not in cta and "👇" not in cta:
                score -= 0.5
                reasons.append("cta_no_question_or_arrow")

            # penalize copy-paste
            if hook and cap and hook.lower() in cap.lower():
                score -= 1.0
                reasons.append("hook_repeated_in_caption")

            score = max(1.0, min(5.0, score))
            results.append(
                {
                    "variant_id": v.variant_id,
                    "score": score,
                    "reasons": reasons,
                    "persona": (v.tone_tags or ["unknown"])[0],
                }
            )
        return results

    @staticmethod
    def _pick_format(index: int, tick_offset: int = 0) -> str:
        formats = ["text_image", "carousel", "reel", "text_image", "reel"]
        return formats[(index + tick_offset) % len(formats)]

    def _base_hashtags(self, pillar: str = "", tick_offset: int = 0) -> list[str]:
        """Base hashtags with pillar-specific rotation and dedup from memory."""
        import json
        import os
        import sqlite3

        base: list[str] = ["skincare", "skincareroutine", "genzskincare", "damatdep"]

        pillar_pool: dict[str, list[str]] = {
            "education": [
                "skincaretips",
                "hocskincare",
                "chamsocdatainha",
                "bikipchamsocda",
                "skincarechongenz",
                "hoclamsong",
            ],
            "review": [
                "reviewthat",
                "reviewmypham",
                "dungthu",
                "reviewchamsocda",
                "myphamtot",
                "thatnghiemthat",
            ],
            "trust": [
                "skincaretips",
                "myphamchatluong",
                "damatdep",
                "chamsocdathat",
                "lammetda",
                "genzskincaredep",
            ],
            "engagement": [
                "hoctap",
                "cunghocskincare",
                "genzlife",
                "cungnhaulamsong",
                "chiaSeKinhNghiem",
                "genzdep",
            ],
            "entertainment": [
                "genzhumor",
                "skincarefunny",
                "trending",
                "skincarevui",
                "genzfun",
                "trendskincare",
            ],
        }

        key = pillar.strip().lower()
        pool = pillar_pool.get(key, ["chamsocda", "lamdepcunggenz", "skincareviet"])

        # Rotate: pick 3 from pool, shifted by tick_offset
        if len(pool) > 0:
            offset = tick_offset % len(pool)
            extra = pool[offset:] + pool[:offset]
            extra = extra[:3]
        else:
            extra = pool

        result = base + extra

        # ── Dedup: exclude hashtags used in recent posts ──
        mem_db = os.path.join(self._memory_dir, "memory.db")
        if os.path.isfile(mem_db):
            try:
                conn = sqlite3.connect(mem_db)
                # Check if hashtags column exists
                col_check = conn.execute(
                    "SELECT COUNT(*) FROM pragma_table_info('published_posts') WHERE name='hashtags'"
                ).fetchone()[0]
                if col_check:
                    cur = conn.execute(
                        "SELECT hashtags FROM published_posts WHERE hashtags IS NOT NULL AND hashtags != '[]' ORDER BY id DESC LIMIT 10"
                    )
                    recent_tags: set[str] = set()
                    for (row,) in cur.fetchall():
                        try:
                            parsed = json.loads(row)
                            if isinstance(parsed, list):
                                recent_tags.update(h.lower().lstrip("#") for h in parsed if h)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    if recent_tags:
                        result = [h for h in result if h.lower().lstrip("#") not in recent_tags]
                conn.close()
            except Exception:
                pass  # silence db read errors

        return result
