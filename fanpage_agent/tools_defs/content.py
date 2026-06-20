"""Content tools: caption writing and performance stats."""

from __future__ import annotations

import json

from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.tools.content.content_stats import compute_content_stats
from fanpage_agent.tools.content.writer import WriterTool

from .helpers import local_store, profile, settings


def tool_write_caption(topic: str | None = None) -> dict:
    s = settings()
    p = profile(s)
    topic_val = topic or ""
    writer = WriterTool(llm_client=build_llm_client(s))
    result = writer.write_caption(
        brand_profile=p,
        topic=topic_val,
        pillar="",
        objective="",
    )
    return json.loads(result.model_dump_json())


def tool_content_stats(days_back: int = 14) -> dict:
    store = local_store()
    return compute_content_stats(store, days_back=days_back)


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "write_caption",
            "description": "Generate a caption for a given topic (uses brand voice + tone validation)",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to write about"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "content_stats",
            "description": "Get content performance stats — which pillars/formats are performing best. Use this to decide what to write next.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_back": {
                        "type": "integer",
                        "description": "Number of days to look back (default 14)",
                    },
                },
            },
        },
    },
]

REGISTRY_BUILDERS = {
    "write_caption": (tool_write_caption, {"topic": None}),
    "content_stats": (tool_content_stats, {"days_back": 14}),
}
