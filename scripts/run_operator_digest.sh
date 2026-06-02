#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

CALENDAR_FILE="${CALENDAR_FILE:-data/real/content_calendar.csv}"
HISTORY_FILE="${HISTORY_FILE:-data/real/post_history.csv}"
METRICS_FILE="${METRICS_FILE:-data/real/post_metrics.csv}"
TRIAGE_FILE="${TRIAGE_FILE:-data/real/comment_triage.csv}"
LIMIT="${LIMIT:-5}"

STORE_ARGS=()
if [[ -n "${STORE_BACKEND:-}" ]]; then
  STORE_ARGS=(--store-backend "$STORE_BACKEND")
fi

python3 -m fanpage_agent.main deliver-operator-digest \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --metrics-file "$METRICS_FILE" \
  --triage-file "$TRIAGE_FILE" \
  --limit "${LIMIT:-5}" \
  --skip-empty \
  --save \
  "${STORE_ARGS[@]}"
