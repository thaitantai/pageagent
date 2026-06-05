"""PageRegistry — manage multiple Facebook page configurations.

Thread-safe singleton that maps ``page_id`` → ``PageConfig``.
Reads from ``Settings.pages`` (from ``FB_PAGES`` env var or config file).
Falls back to the legacy single-page config (fb_page_id / fb_page_token).

Usage::

    from fanpage_agent.v2.adapters.settings import get_settings
    registry = PageRegistry(get_settings())
    config = registry.get("883890888134656")  # specific page
    config = registry.get()                    # default page
"""

from __future__ import annotations

import logging
from typing import Any

from config import PageConfig, Settings

logger = logging.getLogger(__name__)


class PageRegistry:
    """Registry of Facebook page configurations.

    Maintains a cache of ``PageConfig`` instances keyed by ``page_id``.
    The first page in ``settings.pages`` (or the legacy ``fb_page_id``)
    is treated as the **default**.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pages: dict[str, PageConfig] = {}
        self._default_id: str | None = None
        self._load()

    # ── public API ────────────────────────────────────────────────

    def get(self, page_id: str | None = None) -> PageConfig:
        """Get a page config by ID, or the default if omitted."""
        if page_id and page_id in self._pages:
            return self._pages[page_id]
        if self._default_id and self._default_id in self._pages:
            return self._pages[self._default_id]
        # Fallback — construct from settings defaults
        return PageConfig(
            page_id=self._settings.fb_page_id,
            page_token=self._settings.fb_page_token,
            name="default",
            brand_id=self._settings.fb_page_id,
            api_version=self._settings.fb_api_version,
            is_default=True,
        )

    @property
    def default_page_id(self) -> str | None:
        return self._default_id

    @property
    def all_page_ids(self) -> list[str]:
        return list(self._pages.keys())

    @property
    def page_count(self) -> int:
        return len(self._pages)

    def list_pages(self) -> list[dict[str, Any]]:
        """Return a summary of all registered pages."""
        return [
            {
                "page_id": cfg.page_id,
                "name": cfg.name or "(unnamed)",
                "is_default": cfg.is_default,
                "brand_id": cfg.brand_id,
            }
            for cfg in self._pages.values()
        ]

    # ── internal ─────────────────────────────────────────────────

    def _load(self) -> None:
        """Load page configs from Settings."""
        self._pages.clear()
        self._default_id = None

        # 1. Load from FB_PAGES list
        for pdata in getattr(self._settings, "pages", []):
            if isinstance(pdata, dict) and pdata.get("page_id") and pdata.get("page_token"):
                cfg = PageConfig(
                    page_id=pdata["page_id"],
                    page_token=pdata["page_token"],
                    name=pdata.get("name", ""),
                    brand_id=pdata.get("brand_id", pdata["page_id"]),
                    api_version=pdata.get("api_version", self._settings.fb_api_version),
                )
                self._pages[pdata["page_id"]] = cfg

        # 2. Always register the legacy single-page config
        if self._settings.fb_page_id and self._settings.fb_page_token:
            legacy_id = self._settings.fb_page_id
            if legacy_id not in self._pages:
                cfg = PageConfig(
                    page_id=legacy_id,
                    page_token=self._settings.fb_page_token,
                    name="default",
                    brand_id=legacy_id,
                    api_version=self._settings.fb_api_version,
                    is_default=True,
                )
                self._pages[legacy_id] = cfg

        # 3. Determine default
        if not self._pages:
            logger.warning("No Facebook pages configured — FB features will be unavailable")
            return

        # Prefer the first FB_PAGES entry as default, else legacy
        if self._settings.fb_page_id and self._settings.fb_page_id in self._pages:
            self._default_id = self._settings.fb_page_id
        else:
            self._default_id = next(iter(self._pages.keys()))

        # Mark the default
        if self._default_id and self._default_id in self._pages:
            self._pages[self._default_id].is_default = True

        logger.info(
            "PageRegistry loaded %d page(s), default=%s",
            self.page_count,
            self._default_id,
        )


# Module-level cache for convenience
_registry_cache: PageRegistry | None = None


def get_registry(settings: Settings | None = None) -> PageRegistry:
    """Return a cached PageRegistry."""
    global _registry_cache
    if _registry_cache is None:
        if settings is None:
            from fanpage_agent.v2.adapters.settings import get_settings

            settings = get_settings()
        _registry_cache = PageRegistry(settings)
    return _registry_cache
