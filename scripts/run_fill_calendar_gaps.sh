#!/usr/bin/env bash
# Auto-fill gaps in content calendar — run after daily-packet
set -euo pipefail
cd "$(dirname "$0")/.."

BRAND_FILE="data/real/brand_profile.json"
CALENDAR_FILE="data/real/content_calendar.csv"
HISTORY_FILE="data/real/post_history.csv"

python3 -m fanpage_agent.main fill-calendar-gaps \
  --brand-file "$BRAND_FILE" \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --lookahead-days 3 \
  --max-items 3 \
  --json 2>&1
