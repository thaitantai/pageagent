"""Telegram notification tool."""

from __future__ import annotations

from fanpage_agent.adapters.telegram_client import TelegramClient

from .helpers import settings


def tool_send_telegram_message(text: str) -> dict:
    s = settings()
    client = TelegramClient(s)
    client.send_message(text=text, chat_id=s.telegram_chat_id, parse_mode="Markdown")
    return {"sent": True}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "send_telegram_message",
            "description": "Send a text message to the operator's Telegram",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Message text"},
                },
                "required": ["text"],
            },
        },
    },
]

REGISTRY_BUILDERS = {
    "send_telegram_message": (tool_send_telegram_message, {"text": ""}),
}
