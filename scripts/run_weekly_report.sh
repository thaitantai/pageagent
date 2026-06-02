#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

BRAND_FILE="${BRAND_FILE:-data/real/brand_profile.json}"
CALENDAR_FILE="${CALENDAR_FILE:-data/real/content_calendar.csv}"
HISTORY_FILE="${HISTORY_FILE:-data/real/post_history.csv}"
METRICS_FILE="${METRICS_FILE:-data/real/post_metrics.csv}"
COMMENT_FILE="${COMMENT_FILE:-data/real/comment_inbox.csv}"
CAMPAIGN_FILE="${CAMPAIGN_FILE:-data/real/campaign_notes.json}"
RUN_DATE="${RUN_DATE:-$(date +%F)}"

STORE_ARGS=()
if [[ -n "${STORE_BACKEND:-}" ]]; then
  STORE_ARGS=(--store-backend "$STORE_BACKEND")
fi

python3 -m fanpage_agent.main deliver-weekly-report \
  --brand-file "$BRAND_FILE" \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --metrics-file "$METRICS_FILE" \
  --comment-file "$COMMENT_FILE" \
  --campaign-file "$CAMPAIGN_FILE" \
  --run-date "$RUN_DATE" \
  --save \
  "${STORE_ARGS[@]}"
