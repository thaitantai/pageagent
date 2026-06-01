#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

TRIAGE_FILE="${TRIAGE_FILE:-data/comment_triage.csv}"
STATUS="${STATUS:-approved}"
LIMIT="${LIMIT:-5}"

STORE_ARGS=()
if [[ -n "${STORE_BACKEND:-}" ]]; then
  STORE_ARGS=(--store-backend "$STORE_BACKEND")
fi

python3 -m fanpage_agent.main deliver-approved-triage-replies \
  --triage-file "$TRIAGE_FILE" \
  --status "$STATUS" \
  --limit "$LIMIT" \
  --save \
  "${STORE_ARGS[@]}"
