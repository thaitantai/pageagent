from __future__ import annotations

import json
import sys
from pathlib import Path


def ensure_utf8_stdio() -> None:
    """Force UTF-8 stdout/stderr where the console defaults to a legacy
    codepage (Windows cp1252) — Vietnamese output crashes print() otherwise."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.encoding and stream.encoding.lower() not in ("utf-8", "utf8"):
                stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
