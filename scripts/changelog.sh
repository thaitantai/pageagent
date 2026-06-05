#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION=""
WRITE=0
LATEST=0
RANGE=""

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/changelog.sh <version> [--write]
  scripts/changelog.sh <version> --latest [--write]
  scripts/changelog.sh <version> --range <git-range> [--write]

Examples:
  scripts/changelog.sh v0.2.0
  scripts/changelog.sh v0.2.0 --write
  scripts/changelog.sh v0.2.0 --latest --write
  scripts/changelog.sh v0.2.0 --range v0.1.0..HEAD --write
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 2
fi

VERSION="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --write)
      WRITE=1
      shift
      ;;
    --latest)
      LATEST=1
      shift
      ;;
    --range)
      RANGE="${2:-}"
      if [[ -z "$RANGE" ]]; then
        echo "Missing value for --range" >&2
        usage
        exit 2
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

cd "$ROOT_DIR"

run_cliff() {
  local args=(--config cliff.toml --tag "$VERSION")

  if [[ "$LATEST" -eq 1 ]]; then
    args+=(--latest)
  elif [[ -z "$RANGE" ]]; then
    args+=(--unreleased)
  fi

  if command -v git-cliff >/dev/null 2>&1; then
    git-cliff "${args[@]}" "$@" ${RANGE:+"$RANGE"}
  elif git cliff --version >/dev/null 2>&1; then
    git cliff "${args[@]}" "$@" ${RANGE:+"$RANGE"}
  elif command -v docker >/dev/null 2>&1; then
    docker run --rm -v "$ROOT_DIR:/repo" -w /repo orhunp/git-cliff:latest \
      "${args[@]}" "$@" ${RANGE:+"$RANGE"}
  else
    echo "git-cliff is not installed and Docker is unavailable." >&2
    echo "Install with: cargo install git-cliff" >&2
    exit 1
  fi
}

if [[ "$WRITE" -eq 1 ]]; then
  if [[ -f CHANGELOG.md ]]; then
    run_cliff --prepend CHANGELOG.md
  else
    run_cliff --output CHANGELOG.md
  fi
  echo "Updated CHANGELOG.md for $VERSION"
else
  run_cliff
fi
