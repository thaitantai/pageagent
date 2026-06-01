#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

CALENDAR_FILE="${CALENDAR_FILE:-data/content_calendar.csv}"
HISTORY_FILE="${HISTORY_FILE:-data/post_history.csv}"
METRICS_FILE="${METRICS_FILE:-data/post_metrics.csv}"
STATUS="${STATUS:-published}"
LIMIT="${LIMIT:-5}"

STORE_ARGS=()
if [[ -n "${STORE_BACKEND:-}" ]]; then
  STORE_ARGS=(--store-backend "$STORE_BACKEND")
fi

python3 -m fanpage_agent.main deliver-metrics-backlog \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --metrics-file "$METRICS_FILE" \
  --status "$STATUS" \
  --metrics-pending \
  --limit "$LIMIT" \
  --save \
  "${STORE_ARGS[@]}"
