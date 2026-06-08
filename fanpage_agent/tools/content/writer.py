from __future__ import annotations

from fanpage_agent.adapters.llm_client import MockLLMClient
from fanpage_agent.models import BrandProfile, CaptionPackage


class WriterTool:
    def __init__(self, llm_client: object | None = None) -> None:
        self.llm_client = llm_client or MockLLMClient()

    def write_caption(
        self,
        profile: BrandProfile,
        topic: str,
        pillar: str,
        objective: str,
        fmt: str,
    ) -> CaptionPackage:
        return self.llm_client.generate_caption_package(
            profile=profile,
            topic=topic,
            pillar=pillar,
            objective=objective,
            fmt=fmt,
        )
