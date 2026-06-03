#!/usr/bin/env bash
# fanpage-agent-wrapper — generate dashboard and deliver via Telegram
# Style: no-agent script, paused during content freeze, silent on success
set -euo pipefail
cd /home/tantai/.hermes/fanpage-agent
. .env 2>/dev/null || true

OUTPUT=$(poetry run python -m fanpage_agent.main deliver-dashboard --store-backend local --chat-id 6380392986 2>&1) || {
    echo "❌ Dashboard generation failed: $OUTPUT"
    exit 1
}
echo "$OUTPUT"
