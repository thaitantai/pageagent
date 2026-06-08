from __future__ import annotations

import argparse
import json
from pathlib import Path

from fanpage_agent.config import Settings
from fanpage_agent.tools.publishing.telegram_formatter import TelegramFormatterTool

from .parser import ROOT_DIR

try:
    from fanpage_agent.adapters.telegram_client import TelegramClient
except ImportError:
    TelegramClient = None


def render_telegram_preview(artifact_type: str, input_file: str) -> str:
    payload = json.loads(Path(input_file).read_text(encoding="utf-8"))
    formatter = TelegramFormatterTool()
    if artifact_type == "plan":
        return formatter.format_weekly_plan(payload)
    if artifact_type == "caption":
        return formatter.format_caption_package(payload)
    if artifact_type == "report":
        return formatter.format_weekly_report(payload)
    if artifact_type == "triage":
        return formatter.format_community_triage(payload)
    if artifact_type == "approved_replies":
        return formatter.format_approved_triage_replies(payload)
    if artifact_type == "approval":
        return formatter.format_approval_queue(payload)
    if artifact_type == "approval_audit":
        return formatter.format_approval_audit(payload)
    if artifact_type == "metrics":
        return formatter.format_metrics_backlog(payload)
    if artifact_type == "operator":
        return formatter.format_operator_digest(payload)
    if artifact_type == "research":
        return formatter.format_research_brief(payload)
    raise ValueError(f"Unsupported artifact type: {artifact_type}")


def cmd_preview_telegram(args: argparse.Namespace) -> int:
    print(render_telegram_preview(args.artifact_type, args.input_file))
    return 0


def cmd_send_telegram_preview(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    message = render_telegram_preview(args.artifact_type, args.input_file)
    result = TelegramClient(settings).send_message(message, chat_id=args.chat_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
