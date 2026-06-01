#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

BRAND_FILE="${BRAND_FILE:-data/sample/brand_profile.json}"
CALENDAR_FILE="${CALENDAR_FILE:-data/content_calendar.csv}"
HISTORY_FILE="${HISTORY_FILE:-data/post_history.csv}"
METRICS_FILE="${METRICS_FILE:-data/post_metrics.csv}"

STORE_ARGS=()
if [[ -n "${STORE_BACKEND:-}" ]]; then
  STORE_ARGS=(--store-backend "$STORE_BACKEND")
fi

python3 -m fanpage_agent.main deliver-weekly-report \
  --brand-file "$BRAND_FILE" \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --metrics-file "$METRICS_FILE" \
  --save \
  "${STORE_ARGS[@]}"
