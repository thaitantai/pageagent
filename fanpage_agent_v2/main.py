"""V2 main entry point — wires all agents and starts the pipeline."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from fanpage_agent_v2.core.bus import AgentBus
from fanpage_agent_v2.core.types import AgentRole, AgentTask, ActionPriority
from fanpage_agent_v2.agents.orchestrator import OrchestratorAgent
from fanpage_agent_v2.agents.strategist import StrategistAgent
from fanpage_agent_v2.agents.writer import WriterAgent
from fanpage_agent_v2.agents.designer import DesignerAgent
from fanpage_agent_v2.agents.community import CommunityAgent
from fanpage_agent_v2.agents.analyst import AnalystAgent
from fanpage_agent_v2.memory.performance import PerformanceMemory


def create_pipeline(
    data_dir: str | Path = "data/v2",
    brand_id: str = "skincare_genz",
) -> OrchestratorAgent:
    """Create and wire up the full V2 pipeline.

    Returns a ready-to-run OrchestratorAgent with all agents registered.
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    # ── Memory layer ────────────────────────────────────────────
    memory = PerformanceMemory(db_path=data_path / "memory.db")

    # ── Agents ──────────────────────────────────────────────────
    strategist = StrategistAgent(
        config={},
        performance_memory=memory,
        brand_id=brand_id,
    )
    writer = WriterAgent(
        config={},
        brand_id=brand_id,
        default_variants=2,
    )
    designer = DesignerAgent(config={})
    community = CommunityAgent(config={})
    analyst = AnalystAgent(
        config={},
        performance_memory=memory,
    )

    # ── Bus ─────────────────────────────────────────────────────
    bus = AgentBus()

    # ── Orchestrator ────────────────────────────────────────────
    orchestrator = OrchestratorAgent(
        config={},
        bus=bus,
        state_path=data_path / "state.json",
    )

    orchestrator.register_all([
        strategist, writer, designer, community, analyst,
    ])

    return orchestrator


def run_tick(
    data_dir: str | Path = "data/v2",
    brand_id: str = "skincare_genz",
) -> dict[str, Any]:
    """Run a single V2 pipeline tick."""
    orchestrator = create_pipeline(data_dir=data_dir, brand_id=brand_id)
    result = orchestrator.process(AgentTask(
        id="cli-tick",
        target=AgentRole.ORCHESTRATOR,
        action="tick",
        priority=ActionPriority.HIGH,
    ))
    return result.data if result.success else {"error": result.error, "success": False}


def run_status(
    data_dir: str | Path = "data/v2",
    brand_id: str = "skincare_genz",
) -> dict[str, Any]:
    """Get V2 pipeline status."""
    orchestrator = create_pipeline(data_dir=data_dir, brand_id=brand_id)
    result = orchestrator.process(AgentTask(
        id="cli-status",
        target=AgentRole.ORCHESTRATOR,
        action="status",
    ))
    return result.data if result.success else {"error": result.error, "success": False}


def cli() -> None:
    """CLI entry point for V2."""
    import argparse

    parser = argparse.ArgumentParser(description="Fanpage Agent V2")
    parser.add_argument("action", choices=["tick", "status", "daemon"],
                       help="Action to perform")
    parser.add_argument("--data-dir", default="data/v2",
                       help="V2 data directory")
    parser.add_argument("--brand-id", default="skincare_genz",
                       help="Brand identifier")
    parser.add_argument("--interval", type=int, default=7200,
                       help="Daemon interval (seconds, default 7200=2h)")

    args = parser.parse_args()

    if args.action == "tick":
        result = run_tick(data_dir=args.data_dir, brand_id=args.brand_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "status":
        result = run_status(data_dir=args.data_dir, brand_id=args.brand_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "daemon":
        print(f"🔁 V2 daemon starting — tick every {args.interval}s")
        print(f"📂 Data dir: {args.data_dir}")
        print(f"🏷️  Brand: {args.brand_id}")
        print("─" * 40)
        orchestrator = create_pipeline(data_dir=args.data_dir, brand_id=args.brand_id)
        while True:
            result = orchestrator.process(AgentTask(
                id=f"daemon-tick-{int(time.time())}",
                target=AgentRole.ORCHESTRATOR,
                action="tick",
                priority=ActionPriority.HIGH,
            ))
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] tick: {'✅ ok' if result.success else '❌ fail'} "
                  f"({result.metrics.get('elapsed_ms', 0)}ms)")
            sys.stdout.flush()
            time.sleep(args.interval)


if __name__ == "__main__":
    cli()
