#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

RUN_DATE="${RUN_DATE:-$(date +%F)}"
DAYS="${DAYS:-1}"
BRAND_FILE="${BRAND_FILE:-data/real/brand_profile.json}"

CALENDAR_FILE="${CALENDAR_FILE:-data/real/content_calendar.csv}"
HISTORY_FILE="${HISTORY_FILE:-data/real/post_history.csv}"
METRICS_FILE="${METRICS_FILE:-data/real/post_metrics.csv}"
COMMENT_FILE="${COMMENT_FILE:-data/real/comment_inbox.csv}"
CAMPAIGN_FILE="${CAMPAIGN_FILE:-data/real/campaign_notes.json}"

STORE_ARGS=()
if [[ -n "${STORE_BACKEND:-}" ]]; then
  STORE_ARGS=(--store-backend "$STORE_BACKEND")
fi

# Try real LLM first, fall back to mock if proxy is down
if python3 -m fanpage_agent.main deliver-daily-packet \
  --brand-file "$BRAND_FILE" \
  --run-date "$RUN_DATE" \
  --days "$DAYS" \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --metrics-file "$METRICS_FILE" \
  --comment-file "$COMMENT_FILE" \
  --campaign-file "$CAMPAIGN_FILE" \
  --write-calendar \
  --save \
  "${STORE_ARGS[@]}" 2>/dev/null; then
  exit 0
fi

echo "[WARN] Real LLM unavailable, falling back to mock-local provider" >&2
LLM_PROVIDER=mock-local LLM_MODEL=mock-local \
python3 -m fanpage_agent.main deliver-daily-packet \
  --brand-file "$BRAND_FILE" \
  --run-date "$RUN_DATE" \
  --days "$DAYS" \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --metrics-file "$METRICS_FILE" \
  --comment-file "$COMMENT_FILE" \
  --campaign-file "$CAMPAIGN_FILE" \
  --write-calendar \
  --save \
  "${STORE_ARGS[@]}"
