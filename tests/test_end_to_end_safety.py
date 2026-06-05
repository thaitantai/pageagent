from fanpage_agent.agents.writer import WriterAgent
from fanpage_agent.core.harness import AgentHarness
from fanpage_agent.core.types import AgentRole, AgentTask


def _grounded_writer_task(page_context: dict | None = None) -> AgentTask:
    return AgentTask(
        id="e2e-writer",
        target=AgentRole.WRITER,
        action="write_variants",
        params={
            "topic": "SPF cho da dau",
            "pillar": "education",
            "variants": 1,
            "page_context": page_context or {},
            "research_packet": {
                "packet_id": "rpkt-e2e",
                "brief": {
                    "evidence": [
                        {"claim": "SPF can boi du luong", "source": "AAD", "url": "https://example.test/aad"}
                    ]
                },
            },
        },
    )


def test_harness_blocks_writer_without_page_context() -> None:
    harness = AgentHarness()
    writer = WriterAgent(config={"brand_id": "skincare_genz", "enable_llm": False})

    result = harness.run(writer, _grounded_writer_task())

    assert not result.success
    assert result.error is not None
    assert "requires page context" in result.error
    assert harness.events[-1]["status"] == "blocked"


def test_evidence_grounded_writer_records_page_context_through_harness() -> None:
    harness = AgentHarness()
    writer = WriterAgent(config={"brand_id": "skincare_genz", "enable_llm": False})

    result = harness.run(
        writer,
        _grounded_writer_task({
            "page_id": "main",
            "community_value": "Giai dap skincare an toan cho cong dong",
        }),
    )

    assert result.success
    assert harness.events[-1]["status"] == "success"
    assert harness.events[-1]["page_id"] == "main"
    assert result.data.page_id == "main"
    assert result.data.research_packet_id == "rpkt-e2e"
    assert result.data.variants[0].evidence_refs[0]["source"] == "AAD"
