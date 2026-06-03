"""Configuration — project-wide Settings and agent-specific AgentConfig.

Maintains the original fanpage_agent.config.Settings interface
for backward compatibility, plus the agent dataclass.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


# ── helper ──────────────────────────────────────────────────────


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


# ── project-wide settings ───────────────────────────────────────


class Settings(BaseModel):
    """Project-wide configuration — LLM, Telegram, Facebook, image, store."""

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
    fb_page_id: str = ""
    fb_page_token: str = ""
    fb_api_version: str = "v21.0"
    img_provider: str = "mock"  # mock | openai | url
    img_api_key: str = ""
    img_base_url: str = ""
    img_model: str = "dall-e-3"
    artifacts_dir: Path = Path("artifacts")

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        root_dir: Path | None = None,
        load_dotenv: bool | None = None,
    ) -> Settings:
        """Build Settings from environment variables (and optional .env).

        Priority: explicit ``env`` dict > .env file > os.environ.
        """
        sources: dict[str, str] = {}
        # 1. .env file (optional, only if root_dir is provided)
        if load_dotenv is False:
            pass  # skip dotenv when explicitly disabled
        elif root_dir is not None:
            dotenv = _load_root_dotenv(root_dir)
            sources.update(dotenv)
        elif load_dotenv is True:
            # Auto-discover from cwd / parents
            cwd = Path.cwd()
            for ancestor in [cwd] + list(cwd.parents):
                dotenv_path = ancestor / ".env"
                if dotenv_path.exists():
                    sources.update(_load_root_dotenv(ancestor))
                    break
        # 2. explicit env overrides .env
        if env is not None:
            sources.update(env)
        # 3. real env overrides everything
        for key in os.environ:
            sources[key] = os.environ[key]

        kwargs: dict = {}
        for field_name in cls.model_fields:
            env_key = field_name.upper()
            raw = sources.get(env_key)
            if raw is None:
                continue
            field_info = cls.model_fields[field_name]
            if field_info.annotation is list or "list" in str(field_info.annotation):
                kwargs[field_name] = _parse_csv_list(raw)
            elif field_info.annotation is Path:
                kwargs[field_name] = Path(raw)
            elif field_info.annotation is bool or field_info.annotation == bool:
                kwargs[field_name] = raw.lower() in ("true", "1", "yes")
            else:
                kwargs[field_name] = raw

        if root_dir is not None:
            kwargs.setdefault("artifacts_dir", root_dir / "artifacts")
            for key in ("google_service_account_file",):
                if key in kwargs:
                    p = Path(kwargs[key])
                    if not p.is_absolute():
                        kwargs[key] = root_dir / p

        return cls(**kwargs)

    def model_post_init(self, _context) -> None:
        if self.llm_model_candidates is None:
            self.llm_model_candidates = []


# ── agent-specific config ───────────────────────────────────────


@dataclass
class AgentConfig:
    """Configuration for the standalone Fanpage Agent.

    Merged into orchestrator alongside project ``Settings``.
    """

    mode: Literal["daemon", "tick"] = "tick"
    tick_interval_seconds: int = 7200  # 2 hours
    max_actions_per_tick: int = 5
    max_tick_calls: int = 15

    check_approvals: bool = True
    check_community: bool = True
    check_calendar_gaps: bool = True
    check_metrics: bool = True

    deliver_telegram: bool = True
    system_prompt_prefix: str = ""

    allowed_actions: list[str] = field(default_factory=lambda: [
        "ops_status",
        "list_calendar_items",
        "list_triage_items",
        "triage_community",
        "approve_triage_reply",
        "reject_triage_reply",
        "approve_calendar_item",
        "reject_calendar_item",
        "write_caption",
        "run_daily",
        "scheduled_publish",
        "record_post_metrics",
        "fetch_fb_comments",
        "send_telegram_message",
    ])

    @classmethod
    def default(cls) -> AgentConfig:
        return cls()
