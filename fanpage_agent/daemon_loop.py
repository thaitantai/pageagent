"""Runtime daemon loop for repeated orchestrator ticks."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fanpage_agent.core.types import ActionPriority, AgentRole, AgentTask
from fanpage_agent.memory import PerformanceMemory
from fanpage_agent.runtime_pipeline import _load_pages, create_pipeline


def run_daemon_loop(
    *,
    data_dir: str,
    brand_id: str,
    interval: int,
    keep: int,
) -> None:
    pages = _load_pages()
    print(f"🔁 Agent daemon starting tick every {interval}s")
    print(f"📂 Data dir: {data_dir}")
    print(f"🏷️ Brand: {brand_id}")
    print(f"📄 Pages: {[page.get('page_id') for page in pages]}")
    print(f"💾 Auto-backup every {6 * interval // 3600}h (every 6 ticks)")
    print("─" * 40)

    orchestrator = create_pipeline(data_dir=data_dir, brand_id=brand_id, pages=pages)
    tick_count = 0

    while True:
        result = orchestrator.process(
            AgentTask(
                id=f"daemon-tick-{int(time.time())}",
                target=AgentRole.ORCHESTRATOR,
                action="tick",
                priority=ActionPriority.HIGH,
            )
        )
        tick_count += 1
        status = (
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] tick: "
            f"{'✅ ok' if result.success else '❌ fail'} "
            f"({result.metrics.get('elapsed_ms', 0)}ms)"
        )

        if tick_count % 6 == 0:
            try:
                memory = PerformanceMemory(Path(data_dir) / "memory.db")
                path = memory.backup(keep=keep)
                status += f" | 💾 backed up ({path})"
            except Exception as exc:
                status += f" | ⚠️ backup failed: {exc}"

        print(status)
        sys.stdout.flush()
        time.sleep(interval)
