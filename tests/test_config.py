import os
import tempfile
import unittest
from pathlib import Path

from fanpage_agent.config import ConfigError, Settings


class SettingsRequireTest(unittest.TestCase):
    def test_require_passes_when_fields_set(self) -> None:
        settings = Settings(fb_page_id="123", fb_page_token="tok")
        self.assertIs(settings.require("fb_page_id", "fb_page_token"), settings)

    def test_require_lists_every_missing_env_var(self) -> None:
        settings = Settings()
        with self.assertRaises(ConfigError) as ctx:
            settings.require("fb_page_id", "fb_page_token", "telegram_bot_token")
        message = str(ctx.exception)
        self.assertIn("FB_PAGE_ID", message)
        self.assertIn("FB_PAGE_TOKEN", message)
        self.assertIn("TELEGRAM_BOT_TOKEN", message)

    def test_config_error_is_runtime_error(self) -> None:
        self.assertTrue(issubclass(ConfigError, RuntimeError))


class SettingsTest(unittest.TestCase):
    def test_from_env_uses_defaults_and_root_relative_artifacts_dir(self) -> None:
        root = Path(__file__).resolve().parents[1]
        settings = Settings.from_env(env={}, root_dir=root, load_dotenv=False)

        self.assertEqual(settings.llm_provider, "mock-local")
        self.assertEqual(settings.llm_model, "mock-local")
        self.assertEqual(settings.store_backend, "local")
        self.assertEqual(settings.google_sheets_id, "")
        self.assertEqual(settings.google_service_account_file, "")
        self.assertEqual(settings.google_sheets_tabs_prefix, "")
        self.assertEqual(settings.telegram_bot_token, "")
        self.assertEqual(settings.telegram_chat_id, "")
        self.assertEqual(settings.telegram_base_url, "https://api.telegram.org")
        self.assertEqual(settings.fb_page_id, "")
        self.assertEqual(settings.fb_page_token, "")
        self.assertEqual(settings.fb_api_version, "v21.0")
        self.assertEqual(settings.artifacts_dir, root / "artifacts")

    def test_from_env_reads_explicit_values(self) -> None:
        root = Path(__file__).resolve().parents[1]
        env = {
            "LLM_PROVIDER": "openai-compatible",
            "LLM_MODEL": "gpt-test",
            "LLM_MODEL_CANDIDATES": "model-a, model-b ,model-c",
            "LLM_MAX_TOKENS": "900",
            "LLM_BASE_URL": "https://example.test/v1",
            "LLM_API_KEY": "dummy",
            "STORE_BACKEND": "google",
            "GOOGLE_SHEETS_ID": "sheet-123",
            "GOOGLE_SERVICE_ACCOUNT_FILE": "/tmp/service-account.json",
            "GOOGLE_SHEETS_TABS_PREFIX": "fp",
            "TELEGRAM_BOT_TOKEN": "bot-token",
            "TELEGRAM_CHAT_ID": "123456",
            "TELEGRAM_BASE_URL": "https://telegram.example",
            "FB_PAGE_ID": "page-123",
            "FB_PAGE_TOKEN": "token-abc",
            "FB_API_VERSION": "v22.0",
            "ARTIFACTS_DIR": str(root / "tmp-artifacts"),
        }
        settings = Settings.from_env(env=env, root_dir=root, load_dotenv=False)

        self.assertEqual(settings.llm_provider, "openai-compatible")
        self.assertEqual(settings.llm_model, "gpt-test")
        self.assertEqual(settings.llm_model_candidates, ["model-a", "model-b", "model-c"])
        self.assertEqual(settings.llm_max_tokens, 900)
        self.assertEqual(settings.llm_base_url, "https://example.test/v1")
        self.assertEqual(settings.llm_api_key, "dummy")
        self.assertEqual(settings.store_backend, "google")
        self.assertEqual(settings.google_sheets_id, "sheet-123")
        self.assertEqual(settings.google_service_account_file, "/tmp/service-account.json")
        self.assertEqual(settings.google_sheets_tabs_prefix, "fp")
        self.assertEqual(settings.telegram_bot_token, "bot-token")
        self.assertEqual(settings.telegram_chat_id, "123456")
        self.assertEqual(settings.telegram_base_url, "https://telegram.example")
        self.assertEqual(settings.fb_page_id, "page-123")
        self.assertEqual(settings.fb_page_token, "token-abc")
        self.assertEqual(settings.fb_api_version, "v22.0")
        self.assertEqual(settings.artifacts_dir, root / "tmp-artifacts")

    def test_from_env_loads_root_dotenv_without_overriding_explicit_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "LLM_PROVIDER=openai-compatible\n"
                "LLM_MODEL=google/gemma-3-27b-it:free\n"
                "LLM_MODEL_CANDIDATES=meta-llama/llama-3.3-8b-instruct:free,qwen/qwen3-14b:free\n"
                "LLM_BASE_URL=https://openrouter.ai/api/v1\n"
                "LLM_API_KEY=test-openrouter-key\n"
                "ARTIFACTS_DIR=custom-artifacts\n",
                encoding="utf-8",
            )
            settings = Settings.from_env(env={"LLM_MODEL": "openai/gpt-4.1-mini"}, root_dir=root, load_dotenv=True)

        self.assertEqual(settings.llm_provider, "openai-compatible")
        self.assertEqual(settings.llm_model, "openai/gpt-4.1-mini")
        self.assertEqual(
            settings.llm_model_candidates,
            ["meta-llama/llama-3.3-8b-instruct:free", "qwen/qwen3-14b:free"],
        )
        self.assertEqual(settings.llm_max_tokens, 1200)
        self.assertEqual(settings.llm_base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(settings.llm_api_key, "test-openrouter-key")
        self.assertEqual(settings.artifacts_dir, Path("custom-artifacts"))


if __name__ == "__main__":
    unittest.main()
