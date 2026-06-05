#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

STORE_BACKEND="${STORE_BACKEND:-local}"
STORE_ARGS=(--store-backend "$STORE_BACKEND")

exec python -m fanpage_agent.main deliver-operator-digest --save "${STORE_ARGS[@]}" "$@"
