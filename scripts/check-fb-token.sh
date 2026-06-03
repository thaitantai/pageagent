#!/usr/bin/env bash
# FB Token Expiry Monitor
# Usage: bash scripts/check-fb-token.sh
# Returns JSON with token status + days_remaining
# Cron: no-agent script — stdout delivered verbatim if non-empty

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Load .env silently
export $(grep -v '^#' .env | xargs 2>/dev/null) || true

if [ -z "${FB_PAGE_TOKEN:-}" ]; then
  echo '{"ok": false, "error": "FB_PAGE_TOKEN not set in .env"}'
  exit 1
fi

# Call debug_token endpoint
RESPONSE=$(curl -s -w "\n%{http_code}" \
  "https://graph.facebook.com/v22.0/debug_token?input_token=${FB_PAGE_TOKEN}&access_token=${FB_PAGE_TOKEN}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" != "200" ]; then
  echo "{\"ok\": false, \"error\": \"HTTP $HTTP_CODE\", \"body\": $(echo "$BODY" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}"
  exit 1
fi

# Parse with Python for accuracy
python3 -c "
import json, sys, time, datetime

data = json.load(sys.stdin)['data']
now = time.time()

is_valid = data.get('is_valid', False)
expires_at = data.get('expires_at', 0)
data_access_expires_at = data.get('data_access_expires_at', 0)
issued_at = data.get('issued_at', 0)
scopes = data.get('scopes', [])
token_type = data.get('type', 'UNKNOWN')
app_id = data.get('app_id', '')
profile_id = data.get('profile_id', '')

# Convert to human-readable
def ts_to_str(ts):
    if ts == 0:
        return 'never'
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

# Calculate remaining days
if expires_at == 0:
    expires_days = -1  # never
    expires_str = 'never'
else:
    expires_days = max(0, int((expires_at - now) / 86400))
    expires_str = f'{expires_days} days'

if data_access_expires_at == 0:
    data_access_days = -1
    data_access_str = 'never'
else:
    data_access_days = max(0, int((data_access_expires_at - now) / 86400))
    data_access_str = f'{data_access_days} days'

# Determine alerts
alerts = []
if not is_valid:
    alerts.append('INVALID')
if expires_days >= 0 and expires_days < 7:
    alerts.append('TOKEN_EXPIRING_SOON')
if expires_days >= 0 and expires_days < 30:
    alerts.append('TOKEN_EXPIRING')
if data_access_days >= 0 and data_access_days < 7:
    alerts.append('DATA_ACCESS_EXPIRING_SOON')
if data_access_days >= 0 and data_access_days < 30:
    alerts.append('DATA_ACCESS_EXPIRING')

result = {
    'ok': True,
    'is_valid': is_valid,
    'token_type': token_type,
    'expires_at': expires_at,
    'expires_at_human': expires_str,
    'data_access_expires_at': data_access_expires_at,
    'data_access_expires_at_human': data_access_str,
    'issued_at': issued_at,
    'issued_at_human': ts_to_str(issued_at),
    'scopes': scopes,
    'profile_id': profile_id,
    'app_id': app_id,
    'alerts': alerts,
    'healthy': len(alerts) == 0
}

# Silent if healthy (no-agent cron delivers only non-empty stdout)
if result['healthy']:
    sys.exit(0)  # empty stdout = no delivery
else:
    print(json.dumps(result, indent=2))
" <<< "$BODY"
