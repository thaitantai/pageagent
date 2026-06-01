from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


def _parse_csv_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_root_dotenv(root: Path) -> dict[str, str]:
    dotenv_path = root / ".env"
    if not dotenv_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


class Settings(BaseModel):
    llm_provider: str = "mock-local"
    llm_model: str = "mock-local"
    llm_model_candidates: list[str] = []
    llm_max_tokens: int = 1200
    llm_base_url: str = ""
    llm_api_key: str = ""
    store_backend: str = "local"
    google_sheets_id: str = ""
    google_service_account_file: str = ""
    google_sheets_tabs_prefix: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_base_url: str = "https://api.telegram.org"
    artifacts_dir: Path

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        root_dir: Path | None = None,
        load_dotenv: bool | None = None,
    ) -> "Settings":
        root = root_dir or Path(__file__).resolve().parents[1]
        should_load_dotenv = load_dotenv
        if should_load_dotenv is None:
            should_load_dotenv = os.environ.get("FANPAGE_AGENT_DISABLE_DOTENV", "").lower() not in {"1", "true", "yes"}
        merged = _load_root_dotenv(root) if should_load_dotenv else {}
        merged.update(os.environ if env is None else env)
        artifacts = Path(merged.get("ARTIFACTS_DIR", str(root / "artifacts")))
        return cls(
            llm_provider=merged.get("LLM_PROVIDER", "mock-local"),
            llm_model=merged.get("LLM_MODEL", "mock-local"),
            llm_model_candidates=_parse_csv_list(merged.get("LLM_MODEL_CANDIDATES", "")),
            llm_max_tokens=int(merged.get("LLM_MAX_TOKENS", "1200")),
            llm_base_url=merged.get("LLM_BASE_URL", ""),
            llm_api_key=merged.get("LLM_API_KEY", ""),
            store_backend=merged.get("STORE_BACKEND", "local"),
            google_sheets_id=merged.get("GOOGLE_SHEETS_ID", ""),
            google_service_account_file=merged.get("GOOGLE_SERVICE_ACCOUNT_FILE", ""),
            google_sheets_tabs_prefix=merged.get("GOOGLE_SHEETS_TABS_PREFIX", ""),
            telegram_bot_token=merged.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=merged.get("TELEGRAM_CHAT_ID", ""),
            telegram_base_url=merged.get("TELEGRAM_BASE_URL", "https://api.telegram.org"),
            artifacts_dir=artifacts,
        )
