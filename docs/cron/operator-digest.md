# Daily operator digest cron

## Purpose

Send one Telegram digest that combines the three daily follow-up queues operators need most:

1. pending captions that need approval
2. approved triage replies that need to be copy/pasted to fanpage/inbox
3. published posts that still need metrics recorded

This is the lightweight daily control panel before building any autonomous posting/replying.

## Command

```bash
scripts/run_operator_digest.sh
```

Equivalent command:

```bash
python3 -m fanpage_agent.main deliver-operator-digest \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --triage-file data/comment_triage.csv \
  --limit 5 \
  --skip-empty \
  --save \
  --store-backend local
```

Defaults:

```text
pending captions: calendar status=planned, approval_status=pending
approved replies: triage status=approved
metrics backlog: calendar status=published, metrics_pending=true
```

Optional filters:

```bash
--calendar-status planned
--approval-status pending
--triage-status approved
--metrics-status published
--date 2026-06-24
--chat-id <telegram_chat_id_override>
--skip-empty
```

`--skip-empty` prevents Telegram noise when all three queues are empty. The command still writes the artifact and returns:

```json
{
  "delivery": {
    "sent_count": 0,
    "results": [],
    "skipped": true,
    "reason": "empty_digest"
  }
}
```

## Required env

```bash
export TELEGRAM_BOT_TOKEN='***'
export TELEGRAM_CHAT_ID='[REDACTED]'
```

Optional:

```bash
export TELEGRAM_BASE_URL='https://api.telegram.org'
export ARTIFACTS_DIR='artifacts'
export STORE_BACKEND='local'  # optional shell override; omit to let app read .env
```

Wrapper does not force `--store-backend`; it lets the app read `.env` by default.

Google Sheets backend:

```bash
export STORE_BACKEND='google'
export GOOGLE_SHEETS_ID='[REDACTED]'
export GOOGLE_SERVICE_ACCOUNT_FILE='[REDACTED]'
export GOOGLE_SHEETS_TABS_PREFIX='fanpage_agent'
```

## Expected Telegram output

Sends 1 compact, next-action focused message with:

- `Pending captions: N`
- `Approved replies: N`
- `Metrics backlog: N`
- `Next:` section with the first pending caption approve/reject command
- first approved reply follow-up as `reply <triage_id>`
- first metrics follow-up as `record metrics for <calendar_id>`

The formatter intentionally avoids verbose per-queue dumps so the Telegram digest is scannable on mobile.

## Artifact

With `--save`, writes:

```text
artifacts/ops/operator-digest.json
```

Preview saved artifact:

```bash
python3 -m fanpage_agent.main preview-telegram \
  --artifact-type operator \
  --input-file artifacts/ops/operator-digest.json
```

Send saved artifact:

```bash
python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type operator \
  --input-file artifacts/ops/operator-digest.json
```

## Hermes cron mapping

```text
Schedule: 0 2 * * *   # 09:00 Vietnam time when scheduler uses UTC
Script: /home/tantai/.hermes/fanpage-agent/scripts/run_operator_digest.sh
Deliver: local
Workdir: /home/tantai/.hermes/fanpage-agent
```

Use `deliver=local` because the script itself sends Telegram via fanpage-agent; this avoids duplicate scheduler messages.

## Verification checklist

- Command appears in `python3 -m fanpage_agent.main --help`
- Fake Telegram smoke test sends exactly 1 message when at least one queue has work
- `--skip-empty` returns `delivery.sent_count=0`, `delivery.skipped=true`, and does not require Telegram env when all queues are empty
- Saved artifact exists when `--save` is used
- Message contains all three sections: Pending captions, Approved replies, Metrics backlog
- `preview-telegram --artifact-type operator` renders the artifact
- Full unittest suite passes
