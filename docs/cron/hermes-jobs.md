# Hermes Cron Jobs

## Purpose

Fanpage-agent delivery commands are deployed as Hermes `no_agent` script jobs. The project command itself handles Telegram delivery, so every Hermes cron job uses:

- `deliver=local`
- `no_agent=true`
- `workdir=/home/tantai/.hermes/fanpage-agent`
- wrapper script under `~/.hermes/scripts/`

This prevents duplicate Telegram messages from the scheduler.

## Deployed jobs

- `fanpage-agent research brief`
  - schedule: `30 0 * * *`
  - wrapper: `fanpage-agent-research-brief.sh`
  - project script: `scripts/run_research_brief.sh`

- `fanpage-agent daily packet`
  - schedule: `0 1 * * *`
  - wrapper: `fanpage-agent-daily-packet.sh`
  - project script: `scripts/run_daily_packet.sh`

- `fanpage-agent approval queue`
  - schedule: `30 1 * * *`
  - wrapper: `fanpage-agent-approval-queue.sh`
  - project script: `scripts/run_approval_queue.sh`

- `fanpage-agent operator digest`
  - schedule: `0 2 * * *`
  - wrapper: `fanpage-agent-operator-digest.sh`
  - project script: `scripts/run_operator_digest.sh`

- `fanpage-agent weekly report`
  - schedule: `0 2 * * 1`
  - wrapper: `fanpage-agent-weekly-report.sh`
  - project script: `scripts/run_weekly_report.sh`

- `fanpage-agent approval audit`
  - schedule: `0 3 * * *`
  - wrapper: `fanpage-agent-approval-audit.sh`
  - project script: `scripts/run_approval_audit.sh`

- `fanpage-agent metrics backlog`
  - schedule: `30 3 * * *`
  - wrapper: `fanpage-agent-metrics-backlog.sh`
  - project script: `scripts/run_metrics_backlog.sh`

- `fanpage-agent triage community`
  - schedule: `0 */2 * * *`
  - wrapper: `fanpage-agent-triage-community.sh`
  - project script: `scripts/run_triage_community.sh`

- `fanpage-agent approved triage replies`
  - schedule: `15 */2 * * *`
  - wrapper: `fanpage-agent-approved-triage-replies.sh`
  - project script: `scripts/run_approved_triage_replies.sh`

## Wrapper contract

Each Hermes wrapper is intentionally tiny:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec /home/tantai/.hermes/fanpage-agent/scripts/run_<lane>.sh
```

Project scripts keep the real command flags, including `--save`, and read backend/runtime config from `.env`.

## Inspect jobs

```bash
hermes cron list
```

Expected job settings:

```text
no_agent: true
deliver: local
workdir: /home/tantai/.hermes/fanpage-agent
```

## Manual run examples

Run project wrappers directly:

```bash
cd /home/tantai/.hermes/fanpage-agent
scripts/run_daily_packet.sh
scripts/run_operator_digest.sh
scripts/run_weekly_report.sh
```

Run a Hermes cron job by ID after listing jobs:

```bash
hermes cron list
hermes cron run <job_id>
```

## Verify deployment

```bash
cd /home/tantai/.hermes/fanpage-agent
bash -n scripts/run_*.sh
python3 -m unittest tests.test_cron_wrapper_scripts -v
python3 -m fanpage_agent.main ops-status
hermes cron list
```

## Runtime prerequisites

Populate `.env` locally; do not paste secrets into chat.

Required for Telegram delivery:

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

For Google Sheets backend:

```bash
STORE_BACKEND=google
GOOGLE_SHEETS_ID=...
GOOGLE_SERVICE_ACCOUNT_FILE=/absolute/path/to/service-account.json
GOOGLE_SHEETS_TABS_PREFIX=fanpage_agent
```

For real LLM generation:

```bash
LLM_PROVIDER=...
LLM_MODEL=...
LLM_API_KEY=...
# optional
LLM_BASE_URL=...
```
