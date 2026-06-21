import json
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tests.test_env import isolated_subprocess_env


def _run_blocked_import_probe(*blocked: str, modules: list[str]) -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    script = textwrap.dedent(
        """
        import builtins
        import importlib
        import json
        import sys

        blocked = set(sys.argv[1].split(",")) if sys.argv[1] else set()
        modules = [item for item in sys.argv[2].split(",") if item]
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in blocked or any(name.startswith(prefix + ".") for prefix in blocked):
                raise ImportError(f"blocked {name}")
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = fake_import
        results = {}
        for mod in modules:
            for key in list(sys.modules):
                if key == mod or key.startswith(mod + "."):
                    sys.modules.pop(key, None)
            try:
                imported = importlib.import_module(mod)
                payload = {"ok": True}
                if mod == "fanpage_agent.scraping.source_collector":
                    payload["fetcher_is_none"] = getattr(imported, "Fetcher", "missing") is None
                if mod == "fanpage_agent.adapters.google_sheets_store":
                    payload["credentials_is_none"] = getattr(imported, "Credentials", "missing") is None
                    payload["build_is_none"] = getattr(imported, "build", "missing") is None
                results[mod] = payload
            except Exception as exc:
                results[mod] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        print(json.dumps(results, ensure_ascii=False))
        """
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            ",".join(blocked),
            ",".join(modules),
        ],
        cwd=root,
        env=isolated_subprocess_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


class OptionalDependencyImportTest(unittest.TestCase):
    def test_scrapling_optional_imports_do_not_break_module_import(self) -> None:
        payload = _run_blocked_import_probe(
            "scrapling.fetchers",
            modules=[
                "fanpage_agent.scraping.source_collector",
                "fanpage_agent.scraping.trend_scraper",
            ],
        )

        self.assertTrue(payload["fanpage_agent.scraping.source_collector"]["ok"])
        self.assertTrue(payload["fanpage_agent.scraping.source_collector"]["fetcher_is_none"])
        self.assertTrue(payload["fanpage_agent.scraping.trend_scraper"]["ok"])

    def test_google_client_optional_imports_do_not_break_google_store_module(self) -> None:
        payload = _run_blocked_import_probe(
            "google.oauth2.service_account",
            "googleapiclient.discovery",
            modules=["fanpage_agent.adapters.google_sheets_store"],
        )

        self.assertTrue(payload["fanpage_agent.adapters.google_sheets_store"]["ok"])
        self.assertTrue(payload["fanpage_agent.adapters.google_sheets_store"]["credentials_is_none"])
        self.assertTrue(payload["fanpage_agent.adapters.google_sheets_store"]["build_is_none"])

    def test_tools_package_imports_when_optional_dependencies_are_missing(self) -> None:
        payload = _run_blocked_import_probe(
            "scrapling.fetchers",
            "google.oauth2.service_account",
            "googleapiclient.discovery",
            modules=["fanpage_agent.tools"],
        )

        self.assertTrue(payload["fanpage_agent.tools"]["ok"], payload["fanpage_agent.tools"])
