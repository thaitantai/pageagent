#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

BRAND_FILE="${BRAND_FILE:-data/real/brand_profile.json}"
COMMENT_FILE="${COMMENT_FILE:-data/real/comment_inbox.csv}"
TRIAGE_FILE="${TRIAGE_FILE:-data/real/comment_triage.csv}"
STATUS="${STATUS:-new}"
LIMIT="${LIMIT:-5}"

STORE_ARGS=()
if [[ -n "${STORE_BACKEND:-}" ]]; then
  STORE_ARGS=(--store-backend "$STORE_BACKEND")
fi

python3 -m fanpage_agent.main deliver-triage-community \
  --brand-file "$BRAND_FILE" \
  --comment-file "$COMMENT_FILE" \
  --triage-file "$TRIAGE_FILE" \
  --from-store \
  --status "$STATUS" \
  --limit "$LIMIT" \
  --save \
  "${STORE_ARGS[@]}"
