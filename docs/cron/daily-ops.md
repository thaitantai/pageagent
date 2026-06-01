# Daily Ops Cron

## Mục tiêu
Chạy packet vận hành hằng ngày, sinh plan + caption preview, rồi gửi cả 2 message lên Telegram.

## Command

Cron-safe wrapper:

```bash
scripts/run_daily_packet.sh
```

Equivalent command:

```bash
python3 -m fanpage_agent.main deliver-daily-packet \
  --brand-file data/sample/brand_profile.json \
  --run-date "$(date +%F)" \
  --days 1 \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --comment-file data/comment_inbox.csv \
  --campaign-file data/campaign_notes.json \
  --write-calendar \
  --save \
  --store-backend local
```

## Store backend note

Wrapper does not force `--store-backend`; it lets the app read `.env` by default. Set shell `STORE_BACKEND=local` or `STORE_BACKEND=google` only when you intentionally want to override `.env` for one run.

## Env tối thiểu
```bash
export STORE_BACKEND=local
export TELEGRAM_BOT_TOKEN=your-bot-token
export TELEGRAM_CHAT_ID=your-chat-id
```

Nếu dùng Google Sheets:
```bash
export STORE_BACKEND=google
export GOOGLE_SHEETS_ID=your-sheet-id
export GOOGLE_SERVICE_ACCOUNT_FILE=/absolute/path/to/service-account.json
export GOOGLE_SHEETS_TABS_PREFIX=fp
```

## Telegram output
- Message 1: Weekly Plan preview
- Message 2: Caption Package preview

## Cron mapping (Hermes)
No-agent script job, save scheduler output locally to avoid duplicate Telegram messages:

```text
Schedule: 0 1 * * *   # 08:00 Vietnam time when scheduler uses UTC
Script: /home/tantai/.hermes/fanpage-agent/scripts/run_daily_packet.sh
Deliver: local
Workdir: /home/tantai/.hermes/fanpage-agent
```

## Verify
- command exit code = 0
- wrapper smoke test with fake Telegram returns `delivery.sent_count = 2`
- JSON output có `delivery.sent_count = 2`
- calendar được update nếu bật `--write-calendar`
- artifact được lưu ở `artifacts/ops/`
