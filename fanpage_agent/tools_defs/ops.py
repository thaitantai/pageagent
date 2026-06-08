"""Ops tools: status check and pipeline run."""

from __future__ import annotations

from datetime import date

from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.legacy_cli import build_daily_artifacts, build_ops_status_payload
from fanpage_agent.tools.publishing.daily_ops import DailyOpsTool
from fanpage_agent.tools.publishing.planner import PlannerTool
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.tools.content.writer import WriterTool

from .helpers import DEFAULT_COMMENT, local_store, profile, settings


def tool_ops_status(reason: str = "status check") -> dict:
    s = settings()
    return build_ops_status_payload(s)


def tool_run_daily() -> dict:
    s = settings()
    p = profile(s)
    llm = build_llm_client(s)
    store = local_store()
    run_date = date.today().isoformat()

    research_brief = ResearchTool().build_brief(
        store=store,
        comment_csv=str(DEFAULT_COMMENT),
        campaign_notes_file=None,
    )
    packet = DailyOpsTool(
        planner=PlannerTool(llm_client=llm),
        writer=WriterTool(llm_client=llm),
    ).build_packet(
        profile=p,
        run_date=run_date,
        store=store,
        days=7,
        write_calendar=True,
        research_brief=research_brief,
    )
    packet["artifacts"] = build_daily_artifacts(s, packet, run_date)
    return packet


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "ops_status",
            "description": "Get current pipeline status — calendar, community, artifacts freshness",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why you're checking status (e.g. 'cycle start', 'after action')"},
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_daily",
            "description": "Run the full daily pipeline: research → plan → write → verify → queue",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]

REGISTRY_BUILDERS = {
    "ops_status": (tool_ops_status, {}),
    "run_daily": (tool_run_daily, {}),
}
