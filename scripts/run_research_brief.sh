#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

CALENDAR_FILE="${CALENDAR_FILE:-data/content_calendar.csv}"
HISTORY_FILE="${HISTORY_FILE:-data/post_history.csv}"
METRICS_FILE="${METRICS_FILE:-data/post_metrics.csv}"
COMMENT_FILE="${COMMENT_FILE:-data/comment_inbox.csv}"
CAMPAIGN_FILE="${CAMPAIGN_FILE:-data/campaign_notes.json}"

STORE_ARGS=()
if [[ -n "${STORE_BACKEND:-}" ]]; then
  STORE_ARGS=(--store-backend "$STORE_BACKEND")
fi

python3 -m fanpage_agent.main deliver-research-brief \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --metrics-file "$METRICS_FILE" \
  --comment-file "$COMMENT_FILE" \
  --campaign-file "$CAMPAIGN_FILE" \
  --save \
  "${STORE_ARGS[@]}"
