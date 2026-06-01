# Weekly Report Cron

## Mục tiêu

Tạo weekly analytics report từ metrics store và gửi 1 message summary lên Telegram.

## Command

Cron-safe wrapper:

```bash
scripts/run_weekly_report.sh
```

Equivalent command:

```bash
python3 -m fanpage_agent.main deliver-weekly-report \
  --brand-file data/sample/brand_profile.json \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --save \
  --store-backend local
```

Runtime overrides supported by wrapper:

```bash
BRAND_FILE=data/sample/brand_profile.json
CALENDAR_FILE=data/content_calendar.csv
HISTORY_FILE=data/post_history.csv
METRICS_FILE=data/post_metrics.csv
STORE_BACKEND=local  # optional shell override; omit to let app read .env
```

## Env tối thiểu

```bash
export STORE_BACKEND=local
export TELEGRAM_BOT_TOKEN=your-bot-token
export TELEGRAM_CHAT_ID=your-chat-id
```

Google Sheets backend:

```bash
export STORE_BACKEND=google
export GOOGLE_SHEETS_ID='[REDACTED]'
export GOOGLE_SERVICE_ACCOUNT_FILE='[REDACTED]'
export GOOGLE_SHEETS_TABS_PREFIX='fanpage_agent'
```

## Telegram output

- 1 message: Weekly Report

## Artifact

With `--save`, writes:

```text
artifacts/reports/weekly-report.json
```

## Cron mapping (Hermes)

No-agent script job, save scheduler output locally to avoid duplicate Telegram messages:

```text
Schedule: 0 2 * * 1   # 09:00 Monday Vietnam time when scheduler uses UTC
Script: /home/tantai/.hermes/fanpage-agent/scripts/run_weekly_report.sh
Deliver: local
Workdir: /home/tantai/.hermes/fanpage-agent
```

Use `deliver=local` because the script itself sends Telegram via fanpage-agent; this avoids duplicate scheduler messages.

## Verify

- command exit code = 0
- wrapper smoke test with fake Telegram returns `delivery.sent_count = 1`
- JSON output có `delivery.sent_count = 1`
- artifact được lưu ở `artifacts/reports/weekly-report.json`
