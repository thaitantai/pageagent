"""CLI status helpers extracted from the runtime entrypoint."""

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
    ascii_text = ascii_text.replace("đ", "d").replace("Đ", "D")
    return ascii_text.casefold()


def _resolve_roadmap_path(roadmap_target: str | None = None) -> Path:
    target = (roadmap_target or "product").strip().casefold()
    if target == "research":
        return ROOT_DIR / "docs" / "roadmaps" / "agents" / "research-agent-roadmap.md"
    return ROOT_DIR / "docs" / "roadmaps" / "roadmap-next.md"


def _clean_phase_heading(heading: str) -> str:
    cleaned = heading.strip()
    for marker in (" — Done", " - Done", " — done", " - done"):
        if cleaned.endswith(marker):
            return cleaned[: -len(marker)].strip()
    return cleaned


def _phase_is_explicitly_done(raw_heading: str) -> bool:
    normalized = _normalize_roadmap_text(raw_heading)
    return normalized.endswith(" done")


def _run_roadmap_status(roadmap_target: str | None = None) -> None:
    roadmap_path = _resolve_roadmap_path(roadmap_target)
    phases: list[str] = []
    explicit_done_phases: set[str] = set()
    priority_items: list[str] = []
    progress_entries: list[str] = []
    phase_tasks: dict[str, list[str]] = {}
    title = roadmap_path.stem
    section: str | None = None
    current_phase: str | None = None

    if roadmap_path.exists():
        for raw_line in roadmap_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue

            normalized_line = _normalize_roadmap_text(line)
            if line.startswith("# "):
                title = line.removeprefix("# ").strip()
                continue

            if normalized_line.startswith("## phase "):
                current_phase = _clean_phase_heading(line.removeprefix("## ").strip())
                phases.append(current_phase)
                phase_tasks.setdefault(current_phase, [])
                section = "phase"
                if _phase_is_explicitly_done(line.removeprefix("## ").strip()):
                    explicit_done_phases.add(current_phase)
                continue

            if normalized_line == "viec can lam:":
                section = "phase_tasks"
                continue

            if normalized_line in {
                "## uu tien thuc thi ngay",
                "## completion status",
                "## trang thai hoan tat",
                "## next recommended focus",
                "## huong tiep theo duoc khuyen nghi",
            }:
                current_phase = None
                section = "priority"
                continue

            if normalized_line in {"## tien do thuc thi", "## current state"}:
                current_phase = None
                section = "progress"
                continue

            if section == "phase_tasks" and current_phase and line.startswith("- "):
                phase_tasks[current_phase].append(line.removeprefix("- ").strip())
                continue

            if section == "priority":
                if line.startswith("- "):
                    priority_items.append(line.removeprefix("- ").strip())
                elif len(normalized_line) >= 2 and normalized_line[0].isdigit() and normalized_line[1] == ".":
                    priority_items.append(line)
                continue

            if section == "progress" and line.startswith("- "):
                progress_entries.append(line.removeprefix("- ").strip())

    completed_text = _normalize_roadmap_text(" ".join(progress_entries))
    phase_statuses: list[dict[str, Any]] = []
    for phase in phases:
        tasks = phase_tasks.get(phase, [])
        completed_tasks = [
            task for task in tasks if _normalize_roadmap_text(task) in completed_text
        ]
        is_done = phase in explicit_done_phases or (tasks and len(completed_tasks) == len(tasks))
        phase_statuses.append(
            {
                "phase": phase,
                "tasks_total": len(tasks),
                "tasks_confirmed_done": len(completed_tasks),
                "status": "done" if is_done else "active",
                "remaining_tasks": [] if is_done else [task for task in tasks if task not in completed_tasks],
            }
        )

    active_phase = next((item for item in phase_statuses if item["status"] != "done"), None)
    if active_phase is None and phase_statuses:
        active_phase = phase_statuses[-1]

    next_phase = None
    if active_phase and active_phase["phase"] in phases:
        current_index = phases.index(active_phase["phase"])
        next_phase = next((phase for phase in phases[current_index + 1 :] if phase), None)

    print(
        json.dumps(
            {
                "status": "ok",
                "title": title,
                "roadmap_target": (roadmap_target or "product").strip().casefold(),
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
