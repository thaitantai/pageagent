#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

CALENDAR_FILE="${CALENDAR_FILE:-data/real/content_calendar.csv}"
HISTORY_FILE="${HISTORY_FILE:-data/real/post_history.csv}"
METRICS_FILE="${METRICS_FILE:-data/real/post_metrics.csv}"
APPROVAL_STATUS="${APPROVAL_STATUS:-pending}"
LIMIT="${LIMIT:-5}"

STORE_ARGS=()
if [[ -n "${STORE_BACKEND:-}" ]]; then
  STORE_ARGS=(--store-backend "$STORE_BACKEND")
fi

python3 -m fanpage_agent.main deliver-approval-queue \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --metrics-file "$METRICS_FILE" \
  --approval-status "$APPROVAL_STATUS" \
  --limit "$LIMIT" \
  --save \
  "${STORE_ARGS[@]}"
