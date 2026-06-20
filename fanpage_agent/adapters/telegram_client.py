from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fanpage_agent.config import Settings


class TelegramClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required for Telegram delivery")
        self.base_url = settings.telegram_base_url.rstrip("/")

    def send_message(
        self, text: str, chat_id: str | None = None, parse_mode: str | None = "Markdown"
    ) -> dict:
        target_chat_id = chat_id or self.settings.telegram_chat_id
        if not target_chat_id:
            raise RuntimeError("TELEGRAM_CHAT_ID is required for Telegram delivery")
        payload: dict = {
            "chat_id": target_chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        request = Request(
            f"{self.base_url}/bot{self.settings.telegram_bot_token}/sendMessage",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = (
                exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            )
            # Retry with plain text if markdown parsing fails
            if parse_mode and "can't parse entities" in detail:
                return self.send_message(text, chat_id=chat_id, parse_mode=None)
            raise RuntimeError(f"Telegram HTTP error {exc.code}: {detail[:500]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Telegram connection error: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Telegram returned non-JSON body: {body[:500]}") from exc
        if not parsed.get("ok"):
            raise RuntimeError(f"Telegram API returned error payload: {body[:500]}")
        return parsed
