# Approval Audit Cron

Purpose: report approval workflow health so stale pending captions do not sit unnoticed.

## What it checks

- Total calendar rows
- Pending caption count
- Overdue pending captions based on `--sla-days`
- Approved/rejected counts
- Recent rejection notes
- Compact `Next:` section with copy/paste approve/reject commands for overdue pending captions

## Local command

```bash
python3 -m fanpage_agent.main approval-audit \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --as-of 2026-06-24 \
  --sla-days 2 \
  --limit 5 \
  --save \
  --store-backend local
```

## Telegram delivery command

```bash
python3 -m fanpage_agent.main deliver-approval-audit \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --as-of 2026-06-24 \
  --sla-days 2 \
  --limit 5 \
  --save
```

## Required Telegram env

```bash
export TELEGRAM_BOT_TOKEN='[REDACTED]'
export TELEGRAM_CHAT_ID='[REDACTED]'

# optional for tests/smoke
export TELEGRAM_BASE_URL='https://api.telegram.org'
```

## Google Sheets backend

Use the existing project `.env` or export:

```bash
export STORE_BACKEND=google
export GOOGLE_SHEETS_ID='[REDACTED]'
export GOOGLE_SERVICE_ACCOUNT_FILE='[REDACTED]'
export GOOGLE_SHEETS_TABS_PREFIX='fanpage_agent'
```

Do not paste credentials into chat/logs.

## Expected output

- CLI prints JSON with `summary`, `overdue_items`, `recent_rejections`.
- Delivery sends 1 compact Telegram message focused on the next overdue approval actions.
- `--save` writes `artifacts/approvals/approval-audit.json`.
- `ops-status` includes the saved `approval_audit` artifact.

## Preview saved artifact

```bash
python3 -m fanpage_agent.main preview-telegram \
  --artifact-type approval_audit \
  --input-file artifacts/approvals/approval-audit.json
```

## Hermes cron mapping

Use a no-agent script wrapper so the app sends Telegram itself and Hermes does not duplicate delivery.

Example wrapper under `~/.hermes/scripts/fanpage-agent-approval-audit.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /home/tantai/.hermes/fanpage-agent
python3 -m fanpage_agent.main deliver-approval-audit \
  --as-of "$(date +%F)" \
  --sla-days 2 \
  --limit 5 \
  --save
```

Suggested schedule: daily morning Vietnam time.

## Verification checklist

```bash
python3 -m unittest tests.test_approval_audit_cli tests.test_approval_audit_delivery_cli -v
python3 -m unittest tests.test_telegram_formatter tests.test_telegram_preview_cli tests.test_ops_status_cli -v
python3 -m unittest discover -s tests -v
```
