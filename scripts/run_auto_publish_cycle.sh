#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

BRAND_FILE="${BRAND_FILE:-data/real/brand_profile.json}"
CALENDAR_FILE="${CALENDAR_FILE:-data/real/content_calendar.csv}"
HISTORY_FILE="${HISTORY_FILE:-data/real/post_history.csv}"
REFERENCE_DATE="${REFERENCE_DATE:-$(date +%F)}"

echo "=== Auto-approval cycle: $(date -u +%F_%H:%M:%S) ==="
echo ""
echo "--- Phase 1: Auto-approve pending items ---"
python3 -m fanpage_agent.main process-pending \
  --brand-file "$BRAND_FILE" \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --skip-ban \
  --skip-duplicate \
  2>&1

echo ""
echo "--- Phase 2: Publish due items ---"
python3 -m fanpage_agent.main scheduled-publish \
  --brand-file "$BRAND_FILE" \
  --calendar-file "$CALENDAR_FILE" \
  --history-file "$HISTORY_FILE" \
  --reference-date "$REFERENCE_DATE" \
  2>&1

echo ""
echo "=== Cycle complete: $(date -u +%F_%H:%M:%S) ==="
