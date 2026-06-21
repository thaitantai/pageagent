from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_main_does_not_import_legacy_cli() -> None:
    assert "from fanpage_agent.legacy_cli import" not in _read("fanpage_agent/main.py")


def test_public_cli_modules_do_not_pull_shared_constants_from_main() -> None:
    for path in [
        "fanpage_cli/approval.py",
        "fanpage_cli/deliver.py",
        "fanpage_cli/ops.py",
        "fanpage_cli/plan.py",
        "fanpage_cli/triage.py",
    ]:
        assert "from fanpage_agent.main import" not in _read(path)


def test_main_does_not_define_status_cli_helpers_inline() -> None:
    main_text = _read("fanpage_agent/main.py")
    assert "def _run_harness_status(" not in main_text
    assert "def _normalize_roadmap_text(" not in main_text
    assert "def _run_roadmap_status(" not in main_text


def test_main_does_not_define_memory_or_research_helpers_inline() -> None:
    main_text = _read("fanpage_agent/main.py")
    for name in [
        "_run_backup",
        "_run_restore",
        "_run_list_backups",
        "_run_check_db",
        "_run_research_standalone",
        "_run_page_status",
        "_run_competitor_learn",
    ]:
        assert f"def {name}(" not in main_text


def test_main_does_not_define_runtime_pipeline_or_dispatcher_inline() -> None:
    main_text = _read("fanpage_agent/main.py")
    for name in [
        "_load_pages",
        "create_pipeline",
        "run_tick",
        "run_status",
        "cli",
    ]:
        assert f"def {name}(" not in main_text
