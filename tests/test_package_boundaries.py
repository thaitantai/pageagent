from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "fanpage_agent"


def test_package_has_no_runtime_data_directories() -> None:
    forbidden_dirs = [
        PACKAGE_ROOT / "data",
        PACKAGE_ROOT / "artifacts",
    ]

    assert [path for path in forbidden_dirs if path.exists()] == []


def test_package_has_no_local_runtime_or_secret_files() -> None:
    forbidden_patterns = [
        "*.db",
        "*.db-shm",
        "*.db-wal",
        ".env",
        ".env.*",
        "*encoded-*.json",
    ]

    offenders: list[Path] = []
    for pattern in forbidden_patterns:
        offenders.extend(PACKAGE_ROOT.rglob(pattern))

    assert offenders == []


def test_package_boundary_documentation_exists() -> None:
    package_readme = PACKAGE_ROOT / "README.md"
    content = package_readme.read_text(encoding="utf-8")

    assert "Runtime Data Boundary" in content
    assert "Runtime code should write to `data/` or `artifacts/`" in content
