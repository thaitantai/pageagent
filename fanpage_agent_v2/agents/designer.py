"""DesignerAgent — generates visual content for posts.

Manages image briefs, generation, and selection of best visuals.
"""

from __future__ import annotations

import uuid
from typing import Any

from fanpage_agent_v2.core.agent import BaseAgent
from fanpage_agent_v2.core.types import AgentRole, AgentResult, AgentTask


class DesignerAgent(BaseAgent):
    """Designer — creates visual content for posts.

    Capabilities:
    - generate_brief: Create a visual brief from content
    - generate_image: Generate/produce an image
    - select_visual: Pick the best visual from options
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._img_backend = (config or {}).get("image_backend", "url")  # url | dalle | stability

    @property
    def role(self) -> AgentRole:
        return AgentRole.DESIGNER

    @property
    def capabilities(self) -> list[str]:
        return ["generate_brief", "generate_image", "select_visual"]

    def handle_task(self, task: AgentTask) -> AgentResult:
        action = task.action
        params = task.params

        if action == "generate_brief":
            return self._generate_brief(
                topic=params.get("topic", ""),
                hook=params.get("hook", ""),
                format=params.get("format", "text_image"),
            )
        elif action == "generate_image":
            return self._generate_image(
                brief=params.get("brief", ""),
                style=params.get("style", "clean_skincare"),
            )
        return AgentResult(task_id=task.id, success=False, error=f"Unknown action: {action}")

    def _generate_brief(self, topic: str, hook: str, format: str) -> AgentResult:
        """Create a visual brief — text description of desired image."""
        brief = f"Ảnh cho bài {format} về: {topic}. Hook: {hook}."

        if format == "carousel":
            brief += " Thiết kế dạng carousel 4-5 slide."
        elif format == "reel":
            brief += " Concept cho reel ngắn 15-30s."
        else:
            brief += " Ảnh nền sạch, chữ overlay ngắn gọn."

        return AgentResult(
            task_id=f"brief-{uuid.uuid4().hex[:8]}",
            success=True,
            data={
                "visual_brief": brief,
                "format": format,
                "style_suggestions": [
                    "Nền trắng/be, sản phẩm trung tâm",
                    "Màu pastel, ánh sáng tự nhiên",
                    "Chữ to, font dễ đọc (Inter/BeVietnamPro)",
                ],
                "safe_for_facebook": True,
            },
        )

    def _generate_image(self, brief: str, style: str) -> AgentResult:
        """Generate/produce an image based on brief.

        For now, returns the brief so the orchestrator/LLM can decide
        how to produce the image (DALL-E, Stability, or manual upload).
        """
        return AgentResult(
            task_id=f"img-{uuid.uuid4().hex[:8]}",
            success=True,
            data={
                "brief": brief,
                "style": style,
                "backend": self._img_backend,
                "image_path": None,  # Filled when actually generated
                "image_url": None,   # Filled when generated
                "notes": "Image generation deferred to LLM pipeline",
            },
        )
