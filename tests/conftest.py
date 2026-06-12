"""Test isolation fixtures.

Keep the suite independent from the developer's real .env, tokens, and stores.
"""

import os

APP_ENV_KEYS = [
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_MODEL_CANDIDATES",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "STORE_BACKEND",
    "GOOGLE_SHEETS_ID",
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    "GOOGLE_SHEETS_TABS_PREFIX",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_BASE_URL",
    "FB_PAGE_ID",
    "FB_PAGE_TOKEN",
    "FB_API_VERSION",
    "FB_PAGES",
    "ARTIFACTS_DIR",
]


def _clear_app_env() -> None:
    os.environ["FANPAGE_AGENT_DISABLE_DOTENV"] = "1"
    for key in APP_ENV_KEYS:
        os.environ.pop(key, None)


def pytest_configure() -> None:
    _clear_app_env()


import pytest


@pytest.fixture(autouse=True)
def isolate_app_env():
    _clear_app_env()
    yield
    _clear_app_env()
