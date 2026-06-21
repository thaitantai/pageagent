"""CLI status helpers extracted from the main runtime entrypoint."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from fanpage_agent.audit.auditor import AuditManager
from fanpage_agent.cli_common import ROOT_DIR


def _run_harness_status(data_dir: str, limit: int = 20) -> None:
    audit = AuditManager(db_dir=str(Path(data_dir)))
    entries = audit.list(source="AgentHarness", limit=limit)
    recent = [
        {
            "id": entry.id,
            "timestamp": entry.timestamp,
            "event_type": entry.event_type,
            "success": entry.success,
            "duration_ms": entry.duration_ms,
            "error": entry.error,
            "event_data": entry.event_data,
        }
        for entry in entries
    ]
    print(
        json.dumps(
            {
                "status": "ok",
                "audit_db": str(Path(data_dir) / "audit.db"),
                "summary_24h": audit.summary(),
                "harness_events_total": audit.count(source="AgentHarness"),
                "recent": recent,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _normalize_roadmap_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_text = ascii_text.replace("đ", "d").replace("Đ", "d")
    return ascii_text.casefold()


def _run_roadmap_status() -> None:
    roadmap_path = ROOT_DIR / "docs" / "roadmaps" / "roadmap-next.md"
    phases: list[str] = []
    priority_items: list[str] = []
    progress_entries: list[str] = []
    phase_tasks: dict[str, list[str]] = {}
    section: str | None = None
    current_phase: str | None = None

    if roadmap_path.exists():
        for raw_line in roadmap_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            normalized_line = _normalize_roadmap_text(line)
            if normalized_line.startswith("## phase "):
                current_phase = line.removeprefix("## ").strip()
                phases.append(current_phase)
                phase_tasks.setdefault(current_phase, [])
                section = "phase"
            elif normalized_line == "viec can lam:":
                section = "phase_tasks"
            elif normalized_line == "## uu tien thuc thi ngay":
                current_phase = None
                section = "priority"
            elif normalized_line == "## tien do thuc thi":
                current_phase = None
                section = "progress"
            elif section == "phase_tasks" and current_phase and normalized_line.startswith("- "):
                phase_tasks[current_phase].append(line.removeprefix("- ").strip())
            elif (
                section == "priority"
                and len(normalized_line) >= 2
                and normalized_line[0].isdigit()
                and normalized_line[1] == "."
            ):
                priority_items.append(line)
            elif section == "progress" and normalized_line.startswith("- "):
                progress_entries.append(line.removeprefix("- ").strip())

    completed_text = _normalize_roadmap_text(" ".join(progress_entries))
    phase_statuses: list[dict[str, Any]] = []
    for phase in phases:
        tasks = phase_tasks.get(phase, [])
        completed_tasks = [
            task for task in tasks if _normalize_roadmap_text(task) in completed_text
        ]
        phase_statuses.append(
            {
                "phase": phase,
                "tasks_total": len(tasks),
                "tasks_confirmed_done": len(completed_tasks),
                "status": "done" if tasks and len(completed_tasks) == len(tasks) else "active",
                "remaining_tasks": [task for task in tasks if task not in completed_tasks],
            }
        )

    active_phase = next((item for item in phase_statuses if item["status"] != "done"), None)
    if active_phase is None and phase_statuses:
        active_phase = phase_statuses[-1]

    next_phase = None
    if active_phase:
        current_index = phases.index(active_phase["phase"])
        next_phase = next((phase for phase in phases[current_index + 1 :]), None)

    print(
        json.dumps(
            {
                "status": "ok",
                "roadmap": roadmap_path.as_posix(),
                "current_phase": (
                    active_phase["phase"]
                    if active_phase
                    else "Phase 1: Don dep nen tang va tang kha nang quan sat"
                ),
                "next_phase": next_phase,
                "phases_total": len(phases),
                "phase_statuses": phase_statuses,
                "immediate_priorities": priority_items,
                "progress_entries": progress_entries,
                "next_recommended_actions": (active_phase or {}).get("remaining_tasks", [])[:3],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
