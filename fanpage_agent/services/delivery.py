from __future__ import annotations

from fanpage_agent.adapters.telegram_client import TelegramClient
from fanpage_agent.config import Settings
from fanpage_agent.services.telegram_formatter import TelegramFormatterService


class DeliveryService:
    def __init__(
        self,
        settings: Settings,
        telegram_client: TelegramClient | None = None,
        formatter: TelegramFormatterService | None = None,
    ) -> None:
        self.settings = settings
        self.telegram_client = telegram_client or TelegramClient(settings)
        self.formatter = formatter or TelegramFormatterService()

    def deliver_daily_packet(self, packet: dict, chat_id: str | None = None) -> dict:
        messages = [
            packet.get("telegram_preview", {}).get("plan_message", ""),
            packet.get("telegram_preview", {}).get("caption_message", ""),
        ]
        results = [
            self.telegram_client.send_message(message, chat_id=chat_id)
            for message in messages
            if message
        ]
        return {
            "sent_count": len(results),
            "results": results,
        }

    def deliver_weekly_report(self, report_payload: dict, chat_id: str | None = None) -> dict:
        message = self.formatter.format_weekly_report(report_payload)
        result = self.telegram_client.send_message(message, chat_id=chat_id)
        return {
            "sent_count": 1,
            "results": [result],
        }

    def deliver_community_triage(self, triage_payload: dict, chat_id: str | None = None) -> dict:
        message = self.formatter.format_community_triage(triage_payload)
        # Community/triage payloads often contain underscores, brackets, URLs, etc.
        # Using Telegram Markdown parse_mode can easily 400 on unescaped entities.
        # For operational digests, prefer plain text for reliability.
        result = self.telegram_client.send_message(message, chat_id=chat_id, parse_mode=None)
        return {
            "sent_count": 1,
            "results": [result],
        }

    def deliver_approved_triage_replies(self, payload: dict, chat_id: str | None = None) -> dict:
        message = self.formatter.format_approved_triage_replies(payload)
        result = self.telegram_client.send_message(message, chat_id=chat_id, parse_mode=None)
        return {
            "sent_count": 1,
            "results": [result],
        }

    def deliver_approval_queue(self, payload: dict, chat_id: str | None = None) -> dict:
        message = self.formatter.format_approval_queue(payload)
        result = self.telegram_client.send_message(message, chat_id=chat_id)
        return {
            "sent_count": 1,
            "results": [result],
        }

    def deliver_approval_audit(self, payload: dict, chat_id: str | None = None) -> dict:
        message = self.formatter.format_approval_audit(payload)
        result = self.telegram_client.send_message(message, chat_id=chat_id)
        return {
            "sent_count": 1,
            "results": [result],
        }

    def deliver_metrics_backlog(self, payload: dict, chat_id: str | None = None) -> dict:
        message = self.formatter.format_metrics_backlog(payload)
        result = self.telegram_client.send_message(message, chat_id=chat_id)
        return {
            "sent_count": 1,
            "results": [result],
        }

    def deliver_operator_digest(self, payload: dict, chat_id: str | None = None) -> dict:
        message = self.formatter.format_operator_digest(payload)
        result = self.telegram_client.send_message(message, chat_id=chat_id)
        return {
            "sent_count": 1,
            "results": [result],
        }

    def deliver_research_brief(self, payload: dict, chat_id: str | None = None) -> dict:
        message = self.formatter.format_research_brief(payload)
        result = self.telegram_client.send_message(message, chat_id=chat_id)
        return {
            "sent_count": 1,
            "results": [result],
        }

    def deliver_analytics_review(self, payload: dict, chat_id: str | None = None) -> dict:
        message = self.formatter.format_analytics_review(payload)
        result = self.telegram_client.send_message(message, chat_id=chat_id)
        return {
            "sent_count": 1,
            "results": [result],
        }
