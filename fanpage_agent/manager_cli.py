#!/usr/bin/env python3
"""Fanpage Manager — management CLI for config, connect, status, help.

Usage:
    fanpage-manager config            Show current configuration
    fanpage-manager config check      Validate configuration
    fanpage-manager connect           Test all connections
    fanpage-manager connect fb        Test Facebook API
    fanpage-manager connect telegram  Test Telegram bot
    fanpage-manager connect llm       Test LLM provider
    fanpage-manager status            Full system health overview
    fanpage-manager help              Show this help
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT_DIR = HERE.parent


def _find_dotenv() -> dict[str, str]:
    """Load .env file if it exists (no external deps needed)."""
    dotenv_path = ROOT_DIR / ".env"
    if not dotenv_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"").strip()
        if key:
            values[key] = value
    return values


def _colored(text: str, color: str) -> str:
    colors = {"green": "32", "red": "31", "yellow": "33", "cyan": "36", "bold": "1"}
    code = colors.get(color, "0")
    return f"\033[{code}m{text}\033[0m"


def _check(value: str | None, label: str) -> tuple[str, bool]:
    if value and value.strip() and value != "" and value != "your-":
        return _colored("✓", "green"), True
    return _colored("✗", "red"), False


# ── config ──────────────────────────────────────────────────────────


def cmd_config_show(args: argparse.Namespace) -> int:
    dotenv = _find_dotenv()
    env = {**dotenv, **dict(os.environ)}

    sections = {
        "LLM": {
            "LLM_PROVIDER": "Provider",
            "LLM_MODEL": "Model",
            "LLM_BASE_URL": "Base URL",
            "LLM_MAX_TOKENS": "Max tokens",
        },
        "Store": {
            "STORE_BACKEND": "Backend",
            "GOOGLE_SHEETS_ID": "Sheets ID",
            "GOOGLE_SERVICE_ACCOUNT_FILE": "Service account",
            "GOOGLE_SHEETS_TABS_PREFIX": "Tabs prefix",
        },
        "Facebook": {
            "FB_PAGE_ID": "Page ID",
            "FB_PAGE_TOKEN": "Page token",
            "FB_API_VERSION": "API version",
        },
        "Telegram": {
            "TELEGRAM_BOT_TOKEN": "Bot token",
            "TELEGRAM_CHAT_ID": "Chat ID",
            "TELEGRAM_BASE_URL": "Base URL",
        },
        "Image Gen": {
            "IMG_PROVIDER": "Provider",
            "IMG_MODEL": "Model",
        },
    }

    print("╔══════════════════════════════════════╗")
    print("║   Fanpage Agent — Config Overview    ║")
    print("╚══════════════════════════════════════╝")
    print()

    for section, fields in sections.items():
        print(f"  {_colored(section, 'cyan')}:")
        for key, label in fields.items():
            val = env.get(key, "") or ""
            if "TOKEN" in key or "API_KEY" in key or "SECRET" in key or "PASSWORD" in key:
                safe = val[:6] + "…" + val[-4:] if len(val) > 12 else "(empty)"
            elif "FILE" in key:
                safe = val if val else "(empty)"
                if val and not Path(val).exists():
                    safe += f" {_colored('[not found]', 'red')}"
            else:
                safe = val if val else _colored("(empty)", "yellow")
            icon, ok = _check(val, key)
            status = icon if ok else icon
            print(f"    {status} {label}: {safe}")
        print()

    # Sources
    print(f"  {_colored('Sources', 'cyan')}:")
    print(f"    .env file: {'✓' if dotenv else '✗ (not found)'}")
    print(f"    Env vars:  {len([k for k in env if k.startswith(('LLM_','FB_','TELEGRAM_','STORE_','IMG_'))])} active")
    print()

    required = ["LLM_PROVIDER", "FB_PAGE_ID", "FB_PAGE_TOKEN", "TELEGRAM_BOT_TOKEN"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        print(f"  {_colored('⚠ Missing required', 'yellow')}: {', '.join(missing)}")
    else:
        print(f"  {_colored('✓ All required fields present', 'green')}")
    return 0 if not missing else 1


def cmd_config_check(args: argparse.Namespace) -> int:
    ret = cmd_config_show(args)
    return ret


# ── connect ─────────────────────────────────────────────────────────


def _test_fb() -> list[str]:
    errors: list[str] = []
    try:
        from fanpage_agent.adapters.facebook_client import FacebookClient
        from fanpage_agent.config import Settings

        settings = Settings.from_env(root_dir=ROOT_DIR)
        fb = FacebookClient(settings)
        posts = fb.get_page_posts(limit=1)
        print(f"    ✓ Facebook API — {len(posts)} post(s) fetched")
        if posts:
            print(f"      Latest post: {posts[0].get('id', '?')}")
    except Exception as e:
        msg = f"    ✗ Facebook API — {e}"
        errors.append(msg)
        print(msg)
    return errors


def _test_telegram() -> list[str]:
    errors: list[str] = []
    try:
        from fanpage_agent.adapters.telegram_client import TelegramClient
        from fanpage_agent.config import Settings

        settings = Settings.from_env(root_dir=ROOT_DIR)
        tg = TelegramClient(settings)
        # Try sending a simple ping message to verify connectivity
        result = tg.send_message("🔧 Fanpage Manager — connection test", chat_id=settings.telegram_chat_id)
        chat_id_shown = settings.telegram_chat_id or result.get("chat_id", "?")
        print(f"    ✓ Telegram bot — chat {chat_id_shown}")
    except Exception as e:
        msg = f"    ✗ Telegram — {e}"
        errors.append(msg)
        print(msg)
    return errors


def _test_llm() -> list[str]:
    errors: list[str] = []
    try:
        from fanpage_agent.adapters.llm import build_llm_client
        from fanpage_agent.config import Settings
        from fanpage_agent.tools.publishing.planner import PlannerTool

        settings = Settings.from_env(root_dir=ROOT_DIR)
        llm = build_llm_client(settings)
        provider_name = getattr(llm, "provider", type(llm).__name__)
        print(f"    ✓ LLM — provider={provider_name}")
        # Quick ping: generate 1 topic
        from fanpage_agent.loaders.brand_loader import load_brand_profile

        brand_file = ROOT_DIR / "data" / "real" / "brand_profile.json"
        if not brand_file.exists():
            brand_file = ROOT_DIR / "data" / "brand_profile.json"
        if brand_file.exists():
            profile = load_brand_profile(str(brand_file))
            planner = PlannerTool(llm_client=llm)
            plan = planner.plan_week(profile, start_date="2030-01-01", days=1)
            print(f"    ✓ LLM generated plan OK — {plan.plan_title}")
    except Exception as e:
        msg = f"    ✗ LLM — {e}"
        errors.append(msg)
        print(msg)
    return errors


def _test_store() -> list[str]:
    errors: list[str] = []
    try:
        from fanpage_agent.adapters.store_factory import build_store
        from fanpage_agent.config import Settings

        settings = Settings.from_env(root_dir=ROOT_DIR)
        store = build_store(settings=settings)
        items = store.list_calendar_items(limit=3)
        print(f"    ✓ Store ({settings.store_backend}) — {len(items)} calendar item(s)")
    except Exception as e:
        msg = f"    ✗ Store — {e}"
        errors.append(msg)
        print(msg)
    return errors


def cmd_connect(args: argparse.Namespace) -> int:
    all_errors: list[str] = []
    scope = args.scope or "all"

    print("╔══════════════════════════════════════╗")
    print("║     Connection Tests                  ║")
    print("╚══════════════════════════════════════╝")
    print()

    if scope in ("all", "fb"):
        print(f"  {_colored('Facebook', 'cyan')}:")
        all_errors += _test_fb()
        print()

    if scope in ("all", "telegram"):
        print(f"  {_colored('Telegram', 'cyan')}:")
        all_errors += _test_telegram()
        print()

    if scope in ("all", "llm"):
        print(f"  {_colored('LLM', 'cyan')}:")
        all_errors += _test_llm()
        print()

    if scope in ("all", "store"):
        print(f"  {_colored('Store', 'cyan')}:")
        all_errors += _test_store()
        print()

    if all_errors:
        print(f"  {_colored(f'⚠ {len(all_errors)} test(s) failed', 'red')}")
        for err in all_errors:
            print(f"    {err}")
        return 1

    print(f"  {_colored('✓ All connections OK', 'green')}")
    return 0


# ── status ──────────────────────────────────────────────────────────


def cmd_status(args: argparse.Namespace) -> int:
    print("╔══════════════════════════════════════╗")
    print("║   System Status                       ║")
    print("╚══════════════════════════════════════╝")
    print()

    # 1. Config health
    print(f"  {_colored('1. Configuration', 'cyan')}:")
    dotenv = ROOT_DIR / ".env"
    print(f"     .env file: {'✓' if dotenv.exists() else _colored('✗ missing', 'red')}")
    if dotenv.exists():
        from fanpage_agent.config import Settings
        try:
            s = Settings.from_env(root_dir=ROOT_DIR)
            print(f"     LLM: {s.llm_provider}/{s.llm_model}")
            print(f"     Store: {s.store_backend}")
            print(f"     FB: {'✓ configured' if s.fb_page_id and s.fb_page_token else _colored('✗ incomplete', 'yellow')}")
            print(f"     Telegram: {'✓ configured' if s.telegram_bot_token else _colored('✗ incomplete', 'yellow')}")
        except Exception as e:
            print(f"     {_colored(f'✗ Load error: {e}', 'red')}")
    print()

    # 2. Data files
    print(f"  {_colored('2. Data Files', 'cyan')}:")
    data_dir = ROOT_DIR / "data"
    if data_dir.exists():
        files = sorted(data_dir.rglob("*.csv")) + sorted(data_dir.rglob("*.json"))
        for f in files:
            rel = f.relative_to(ROOT_DIR)
            size = f.stat().st_size
            icon = "✓" if size > 0 else _colored("✗", "yellow")
            print(f"     {icon} {rel} ({size:,} bytes)")
    else:
        print(f"     {_colored('✗ data/ not found', 'red')}")
    print()

    # 3. Artifacts
    print(f"  {_colored('3. Artifacts', 'cyan')}:")
    art_dir = ROOT_DIR / "artifacts"
    if art_dir.exists():
        total = sum(1 for _ in art_dir.rglob("*") if _.is_file())
        size = sum(_.stat().st_size for _ in art_dir.rglob("*") if _.is_file())
        print(f"     {total} file(s), {size:,} bytes")
    else:
        print(f"     {_colored('(empty — no artifacts generated yet)', 'yellow')}")
    print()

    # 4. Version
    print(f"  {_colored('4. Project', 'cyan')}:")
    try:
        from importlib.metadata import version

        ver = version("fanpage-agent")
    except Exception:
        ver = "0.15.0 (dev)"
    print(f"     Version: {ver}")
    print(f"     Python: {sys.version.split()[0]}")
    print(f"     CWD: {ROOT_DIR}")
    print()

    print(f"  {_colored('✓ Status report complete', 'green')}")
    return 0


# ── help ────────────────────────────────────────────────────────────


def cmd_help(args: argparse.Namespace) -> int:
    print("╔══════════════════════════════════════╗")
    print("║   Fanpage Manager — CLI Reference    ║")
    print("╚══════════════════════════════════════╝")
    print()
    print("  fanpage-manager {command} [options]")
    print()
    print("  Commands:")
    print("    config               Show current .env / env configuration")
    print("    config check         Validate configuration (alias for config)")
    print("    connect              Test Facebook + Telegram + LLM + Store")
    print("    connect fb           Test Facebook API only")
    print("    connect telegram     Test Telegram bot only")
    print("    connect llm          Test LLM provider only")
    print("    status               Full system health overview")
    print("    help                 Show this help")
    print()
    print("  Example .env:")
    print("    LLM_PROVIDER=openai-compatible")
    print("    LLM_BASE_URL=https://openrouter.ai/api/v1")
    print("    LLM_API_KEY=sk-xxx")
    print("    LLM_MODEL=google/gemma-3-27b-it:free")
    print("    FB_PAGE_ID=123456789")
    print("    FB_PAGE_TOKEN=EAAx...")
    print("    TELEGRAM_BOT_TOKEN=123:ABC")
    print("    TELEGRAM_CHAT_ID=-1001234567890")
    print()
    print("  All commands respect .env and environment variables.")
    print("  Store env vars in .env (or pass as -e to Docker).")
    return 0


# ── parser ──────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fanpage-manager",
        description="Fanpage Agent — management CLI for config, connect, status",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_config = sub.add_parser("config", help="Show or validate configuration")
    p_config.add_argument("action", nargs="?", default="show", choices=["show", "check"])
    p_config.set_defaults(_handler=cmd_config_show)

    p_connect = sub.add_parser("connect", help="Test connections")
    p_connect.add_argument(
        "scope", nargs="?", default="all", choices=["all", "fb", "telegram", "llm", "store"]
    )
    p_connect.set_defaults(_handler=cmd_connect)

    p_status = sub.add_parser("status", help="Full system health overview")
    p_status.set_defaults(_handler=cmd_status)

    p_help = sub.add_parser("help", help="Show CLI reference")
    p_help.set_defaults(_handler=cmd_help)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.print_help()
        return 2

    # Dispatch with correct handler for config
    if args.command == "config" and args.action == "check":
        return cmd_config_check(args)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
