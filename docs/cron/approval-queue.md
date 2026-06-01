# Approval Queue Cron

## Mục tiêu
Lấy các bài trong content calendar đang chờ duyệt và gửi digest Telegram để người vận hành mở artifact caption rồi approve/reject bằng CLI.

## Command cơ bản
```bash
python3 -m fanpage_agent.main deliver-approval-queue \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --approval-status pending \
  --limit 5
```

## Điều kiện để queue hữu ích
- trước đó đã chạy `run-daily --write-calendar --save` hoặc `deliver-daily-packet --write-calendar --save`
- mỗi row calendar sẽ có `draft_caption_ref`
- người duyệt dùng path đó để mở artifact caption rồi quyết định:
  - `approve-caption`
  - `reject-caption`

## Output Telegram
Digest 1 message gồm:
- tổng số item pending
- breakdown theo status / approval status / pillar
- top items với:
  - `calendar_id`
  - `topic`
  - `draft_caption_ref`
  - copy/paste command để duyệt:
    - `approve-caption --calendar-id ... --caption-file ...`
    - `reject-caption --calendar-id ... --reason ...`

## Local env tối thiểu
```bash
export STORE_BACKEND=local
export TELEGRAM_BOT_TOKEN=your-bot-token
export TELEGRAM_CHAT_ID=your-chat-id
```

## Google Sheets env bổ sung
```bash
export STORE_BACKEND=google
export GOOGLE_SHEETS_ID=your-sheet-id
export GOOGLE_SERVICE_ACCOUNT_FILE=/absolute/path/to/service-account.json
export GOOGLE_SHEETS_TABS_PREFIX=fp
```

## Hermes cron mapping
```text
0 8 * * * python3 -m fanpage_agent.main deliver-approval-queue \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --approval-status pending \
  --limit 5
```

## Verify checklist
- chạy `run-daily --write-calendar --save`
- chạy `list-calendar-items --approval-status pending`
- confirm row có `draft_caption_ref`
- chạy `deliver-approval-queue`
- confirm Telegram digest có `calendar_id` và path artifact
- confirm Telegram digest có sẵn command approve/reject cho từng pending caption
