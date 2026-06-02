#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

BRAND_FILE="${BRAND_FILE:-data/sample/brand_profile.json}"
CALENDAR_FILE="${CALENDAR_FILE:-data/content_calendar.csv}"
HISTORY_FILE="${HISTORY_FILE:-data/post_history.csv}"
METRICS_FILE="${METRICS_FILE:-data/post_metrics.csv}"
COMMENT_FILE="${COMMENT_FILE:-data/comment_inbox.csv}"
CAMPAIGN_FILE="${CAMPAIGN_FILE:-data/campaign_notes.json}"
RUN_DATE="${RUN_DATE:-$(date +%F)}"

STORE_ARGS=()
if [[ -n "${STORE_BACKEND:-}" ]]; then
  STORE_ARGS=(--store-backend "$STORE_BACKEND")
fi

# Try real LLM first
if python3 -m fanpage_agent.main weekly-report \
  --brand-file "$BRAND_FILE" \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --metrics-file "$METRICS_FILE" \
  --comment-file "$COMMENT_FILE" \
  --campaign-file "$CAMPAIGN_FILE" \
  --run-date "$RUN_DATE" \
  --save \
  "${STORE_ARGS[@]}" 2>/dev/null; then
  exit 0
fi

echo "[WARN] Real LLM unavailable, falling back to mock-local provider" >&2
LLM_PROVIDER=mock-local LLM_MODEL=mock-local \
python3 -m fanpage_agent.main weekly-report \
  --brand-file "$BRAND_FILE" \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --metrics-file "$METRICS_FILE" \
  --comment-file "$COMMENT_FILE" \
  --campaign-file "$CAMPAIGN_FILE" \
  --run-date "$RUN_DATE" \
  --save \
  "${STORE_ARGS[@]}"
