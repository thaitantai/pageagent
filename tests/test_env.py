import os

APP_ENV_KEYS = [
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "STORE_BACKEND",
    "GOOGLE_SHEETS_ID",
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    "GOOGLE_SHEETS_TABS_PREFIX",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_BASE_URL",
    "ARTIFACTS_DIR",
]


def isolated_subprocess_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env["FANPAGE_AGENT_DISABLE_DOTENV"] = "1"
    for key in APP_ENV_KEYS:
        env.pop(key, None)
    env.update(overrides)
    return env
