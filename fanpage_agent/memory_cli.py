"""CLI helpers for memory database maintenance operations."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _run_backup(data_dir: str, keep: int = 7) -> None:
    from fanpage_agent.memory import PerformanceMemory

    memory = PerformanceMemory(Path(data_dir) / "memory.db")
    path = memory.backup(keep=keep)
    print(
        json.dumps(
            {
                "status": "ok",
                "backup_path": str(path),
                "backups_kept": keep,
                "available": memory.list_backups(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _run_restore(data_dir: str, backup_idx: int = 1) -> None:
    from fanpage_agent.memory import BackupError, PerformanceMemory

    memory = PerformanceMemory(Path(data_dir) / "memory.db")
    try:
        memory.restore(backup_idx=backup_idx)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "restored_from": f"backup #{backup_idx}",
                    "db_path": str(memory.db_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except BackupError as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": str(exc),
                    "available": memory.list_backups(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)


def _run_list_backups(data_dir: str) -> None:
    from fanpage_agent.memory import PerformanceMemory

    memory = PerformanceMemory(Path(data_dir) / "memory.db")
    backups = memory.list_backups()
    print(
        json.dumps(
            {
                "status": "ok",
                "count": len(backups),
                "backups": backups,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _run_check_db(data_dir: str) -> None:
    from fanpage_agent.memory import PerformanceMemory

    memory = PerformanceMemory(Path(data_dir) / "memory.db")
    errors = memory.integrity_check()
    if errors:
        print(
            json.dumps(
                {
                    "status": "error",
                    "integrity_errors": errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)

    print(
        json.dumps(
            {
                "status": "ok",
                "integrity": "passed",
                "db_path": str(memory.db_path),
                "total_posts": memory._total_posts(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
