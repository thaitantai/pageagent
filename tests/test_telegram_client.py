import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fanpage_agent.adapters.telegram_client import TelegramClient
from fanpage_agent.config import Settings


class FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TelegramClientTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.settings = Settings.from_env(
            env={
                "TELEGRAM_BOT_TOKEN": "bot-token",
                "TELEGRAM_CHAT_ID": "123456",
                "TELEGRAM_BASE_URL": "https://telegram.example",
            },
            root_dir=root,
            load_dotenv=False,
        )

    @patch("fanpage_agent.adapters.telegram_client.urlopen")
    def test_send_message_posts_to_telegram_api(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeHttpResponse(
            {
                "ok": True,
                "result": {
                    "message_id": 77,
                    "chat": {"id": 123456},
                    "text": "hello from test",
                },
            }
        )
        client = TelegramClient(self.settings)

        result = client.send_message("hello from test")

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["message_id"], 77)
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://telegram.example/botbot-token/sendMessage")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["chat_id"], "123456")
        self.assertEqual(body["text"], "hello from test")
        self.assertNotIn("parse_mode", body)

    def test_requires_telegram_bot_token(self) -> None:
        root = Path(__file__).resolve().parents[1]
        settings = Settings.from_env(env={"TELEGRAM_CHAT_ID": "123456"}, root_dir=root, load_dotenv=False)
        with self.assertRaises(RuntimeError):
            TelegramClient(settings)


if __name__ == "__main__":
    unittest.main()
