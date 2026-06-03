"""WriterAgent — generates multi-variant content captions for A/B testing.

This is the core content creation engine. It produces 2-3 variants per topic
so the system can test which performs better and learn from results.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fanpage_agent_v2.core.agent import BaseAgent
from fanpage_agent_v2.core.types import (
    AgentRole,
    AgentResult,
    AgentTask,
    ContentPackage,
    ContentVariant,
)


class WriterAgent(BaseAgent):
    """Writer — generates N variants of a content post.

    Capabilities:
    - write_variants: Generate 2-3 content variants for A/B testing
    - rewrite: Revise a variant based on feedback
    - merge_variants: Combine best elements from multiple variants
    - generate_hooks: Generate N hook options for a topic
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        brand_id: str = "skincare_genz",
        default_variants: int = 2,
    ) -> None:
        super().__init__(config)
        self._brand_id = brand_id
        self._default_variants = default_variants

        # Tone/style templates for GenZ skincare
        self._tone_profiles: dict[str, dict] = (config or {}).get("tone_profiles", {
            "chia_sẻ": {
                "desc": "Kiểu chia sẻ chân thật, gần gũi",
                "markers": ["Mình từng...", "Có bạn nào...", "Chia sẻ thật lòng"],
            },
            "chuyên_môn": {
                "desc": "Kiểu giải thích khoa học, đáng tin",
                "markers": ["Theo nghiên cứu", "Bác sĩ da liễu khuyên", "Thành phần hoạt động"],
            },
            "hài_hước": {
                "desc": "Kiểu hài hước, trend GenZ",
                "markers": ["POV:", "Be like", "Rant nhẹ"],
            },
        })

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
        """Generate N content variants with different angles and tones.

        In production, this calls the LLM to generate unique variants.
        Currently returns structured templates that the LLM fills in.
        """
        now = datetime.now(timezone.utc).isoformat()
        package_id = f"pkg-{uuid.uuid4().hex[:8]}"
        date = scheduled_date or now[:10]
        time = scheduled_time or "09:00"

        variants: list[ContentVariant] = []
        tones = list(self._tone_profiles.keys())

        for i in range(count):
            tone = tones[i % len(tones)]
            variant_id = f"var-{package_id}-{i}"
            variants.append(ContentVariant(
                variant_id=variant_id,
                topic=topic,
                pillar=pillar,
                caption="",  # LLM fills this
                hook="",     # LLM fills this
                cta="",      # LLM fills this
                format=self._pick_format(i),
                tone_tags=[tone],
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
        """Generate N hook options for a topic."""
        hooks = [
            f"Mình từng {topic.lower()} và đây là điều rút ra…",
            f"Bạn có biết {topic.lower()} không? 🤔",
            f"3 sai lầm khi {topic.lower()} mà ai cũng mắc phải",
            f"POV: Bạn {topic.lower()} và kết quả bất ngờ",
            f"Review thật: {topic.title()} — có đáng tiền?",
            f"Bác sĩ da liễu nói gì về {topic.lower()}?",
            f"Bạn thuộc team nào? {topic} kiểu A hay kiểu B?",
        ]
        selected = hooks[:count]
        return AgentResult(
            task_id=f"hooks-{topic[:20]}",
            success=True,
            data={"hooks": selected, "count": len(selected)},
        )

    def _rewrite_variant(self, variant_id: str, feedback: str) -> AgentResult:
        """Revise a variant (placeholder for LLM orchestration)."""
        return AgentResult(
            task_id=f"rewrite-{variant_id}",
            success=True,
            data={"variant_id": variant_id, "feedback": feedback, "revised": True},
        )

    @staticmethod
    def _pick_format(index: int) -> str:
        formats = ["text_image", "carousel", "reel", "text_image"]
        return formats[index % len(formats)]

    @staticmethod
    def _base_hashtags() -> list[str]:
        return ["skincare", "skincareroutine", "genzskincare", "damatdep"]
