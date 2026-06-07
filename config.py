"""Configuration — project-wide Settings and agent-specific AgentConfig.

Maintains the original fanpage_agent.config.Settings interface
for backward compatibility, plus the agent dataclass.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# ── multi-page support ──────────────────────────────────────────


@dataclass
class PageConfig:
    """Configuration for a single Facebook page in a multi-page setup."""

    page_id: str
    page_token: str
    name: str = ""
    brand_id: str = ""
    topic_focus: str = ""
    audience: str = ""
    community_value: str = ""
    tone: str = ""
    industry_focus: str = ""
    customer_pain_points: list[str] = field(default_factory=list)
    products_services: list[dict] = field(default_factory=list)
    affiliate_offers: list[dict] = field(default_factory=list)
    content_policy: dict = field(default_factory=dict)
    banned_topics: list[str] = field(default_factory=list)
    research_sources: list[str] = field(default_factory=list)
    competitor_pages: list[str] = field(default_factory=list)
    api_version: str = "v21.0"
    is_default: bool = False


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

    # Multi-page support: list of PageConfig dicts
    pages: list[dict] = Field(default_factory=list, exclude=True)

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
        env_source = env if env is not None else os.environ
        dotenv_disabled = env_source.get("FANPAGE_AGENT_DISABLE_DOTENV", "").lower() in (
            "1", "true", "yes"
        )

        # 1. .env file (optional, only if root_dir is provided)
        if load_dotenv is False or dotenv_disabled:
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
        # 2. real env overrides .env
        for key in os.environ:
            sources[key] = os.environ[key]
        # 3. explicit env overrides everything for tests/CLI callers
        if env is not None:
            sources.update(env)

        kwargs: dict = {}
        for field_name in cls.model_fields:
            env_key = field_name.upper()
            raw = sources.get(env_key)
            if raw is None:
                continue
            field_info = cls.model_fields[field_name]
            if field_name == "pages":
                # JSON env var: FB_PAGES='[{"page_id":"...","page_token":"...","name":"..."}]'
                import json as _json
                try:
                    parsed = _json.loads(raw)
                    if isinstance(parsed, list):
                        kwargs["pages"] = parsed
                except (_json.JSONDecodeError, TypeError):
                    pass
            elif field_info.annotation is list or "list" in str(field_info.annotation):
                kwargs[field_name] = _parse_csv_list(raw)
            elif field_info.annotation is Path:
                kwargs[field_name] = Path(raw)
            elif field_info.annotation is bool:
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

    def get_page_config(self, page_id: str | None = None) -> PageConfig:
        """Return PageConfig for a given page_id.

        If page_id is None or empty, returns the default page (from fb_page_id/fb_page_token).

        Returns a PageConfig with the matching page_id, or the default if not found.
        """
        # Find in pages list
        for pdata in self.pages:
            if isinstance(pdata, dict) and pdata.get("page_id") == page_id:
                return PageConfig(
                    page_id=pdata["page_id"],
                    page_token=pdata["page_token"],
                    name=pdata.get("name", ""),
                    brand_id=pdata.get("brand_id", pdata.get("page_id", "")),
                    topic_focus=pdata.get("topic_focus", ""),
                    audience=pdata.get("audience", ""),
                    community_value=pdata.get("community_value", ""),
                    tone=pdata.get("tone", ""),
                    industry_focus=pdata.get("industry_focus", ""),
                    customer_pain_points=list(pdata.get("customer_pain_points", [])),
                    products_services=list(pdata.get("products_services", [])),
                    affiliate_offers=list(pdata.get("affiliate_offers", [])),
                    content_policy=dict(pdata.get("content_policy", {})),
                    banned_topics=list(pdata.get("banned_topics", [])),
                    research_sources=list(pdata.get("research_sources", [])),
                    competitor_pages=list(pdata.get("competitor_pages", [])),
                    api_version=pdata.get("api_version", self.fb_api_version),
                )
        # Fallback to default
        return PageConfig(
            page_id=self.fb_page_id,
            page_token=self.fb_page_token,
            name="default",
            brand_id=self.fb_page_id,
            api_version=self.fb_api_version,
            is_default=True,
        )

    @property
    def page_ids(self) -> list[str]:
        """Return all configured page IDs (including the default)."""
        ids = {self.fb_page_id}
        for pdata in self.pages:
            if isinstance(pdata, dict) and pdata.get("page_id"):
                ids.add(pdata["page_id"])
        return list(ids)


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
        "fill_calendar_gaps",
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
        "content_stats",
    ])

    @classmethod
    def default(cls) -> AgentConfig:
        return cls()
