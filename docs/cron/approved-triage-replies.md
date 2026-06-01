# Approved triage replies cron

## Purpose

Deliver a Telegram digest of community triage items whose reply drafts have already been approved but have not been marked as sent yet.

Use this as the operator handoff queue: copy/paste approved replies to Facebook comments/inbox, then mark each item as replied with the real permalink.

## Command

```bash
python3 -m fanpage_agent.main deliver-approved-triage-replies \
  --triage-file data/comment_triage.csv \
  --status approved \
  --limit 5 \
  --save \
  --store-backend local
```

Optional filters:

```bash
--priority high
--assigned-to closer-1
--chat-id <telegram_chat_id_override>
```

## Required env

```bash
export TELEGRAM_BOT_TOKEN='[REDACTED]'
export TELEGRAM_CHAT_ID='[REDACTED]'
```

Optional:

```bash
export TELEGRAM_BASE_URL='https://api.telegram.org'
export ARTIFACTS_DIR='artifacts'
export STORE_BACKEND='local'
```

Google Sheets backend:

```bash
export STORE_BACKEND='google'
export GOOGLE_SHEETS_ID='[REDACTED]'
export GOOGLE_SERVICE_ACCOUNT_FILE='[REDACTED]'
export GOOGLE_SHEETS_TABS_PREFIX='fanpage_agent'
```

## Expected Telegram output

Sends 1 message containing:

- total approved reply items
- status and priority counts
- top approved replies with `triage_id`, source, priority, original message, and `draft_reply`
- follow-up command template for `mark-triage-reply-sent`

## Artifact

With `--save`, writes:

```text
artifacts/community/approved-triage-replies.json
```

Preview saved artifact:

```bash
python3 -m fanpage_agent.main preview-telegram \
  --artifact-type approved_replies \
  --input-file artifacts/community/approved-triage-replies.json
```

Send saved artifact:

```bash
python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type approved_replies \
  --input-file artifacts/community/approved-triage-replies.json
```

## After sending replies manually

For each reply actually sent on Facebook/Inbox, record it:

```bash
python3 -m fanpage_agent.main mark-triage-reply-sent \
  --triage-file data/comment_triage.csv \
  --triage-id <TRIAGE_ID> \
  --sent-at 2026-06-24T09:15:00 \
  --reply-permalink https://facebook.com/comment/123 \
  --assigned-to closer-1
```

## Hermes cron mapping

```text
Schedule: every 2h
Prompt: Run fanpage-agent approved triage replies delivery from the project root. Use the existing .env. Command: python3 -m fanpage_agent.main deliver-approved-triage-replies --triage-file data/comment_triage.csv --status approved --limit 5 --save --store-backend local. Return the JSON summary and mention whether delivery.sent_count is 1.
Workdir: /home/tantai/.hermes/fanpage-agent
```

## Verification checklist

- Command appears in `python3 -m fanpage_agent.main --help`
- Fake Telegram smoke test sends exactly 1 message
- Saved artifact exists when `--save` is used
- Message contains `triage_id`, `draft_reply`, and `mark-triage-reply-sent`
- `preview-telegram --artifact-type approved_replies` renders the artifact
- Full unittest suite passes
