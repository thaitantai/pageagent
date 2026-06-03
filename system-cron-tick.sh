#!/usr/bin/env bash
# System cron wrapper — fully independent of Hermes.
set -euo pipefail

cd /home/tantai/.hermes/fanpage-agent

# Load environment (FB token, LLM config, etc.)
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

LOG_DIR="/home/tantai/.hermes/fanpage-agent/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/agent-tick-$(date +%Y%m%d-%H%M).log"

VENV_PYTHON="/home/tantai/.hermes/hermes-agent/venv/bin/python"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting agent-tick..." >> "$LOG_FILE"
$VENV_PYTHON -m fanpage_agent.main agent-tick --max-actions 5 >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Finished (exit=$EXIT_CODE)" >> "$LOG_FILE"

# Keep last 30 log files
ls -t "$LOG_DIR"/agent-tick-*.log 2>/dev/null | tail -n +31 | xargs -r rm -f

exit $EXIT_CODE
