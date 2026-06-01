# Community Triage Cron

## Mục tiêu
Quét comment/inbox batch, persist triage state, rồi gửi digest Telegram chỉ cho các item cần xử lý theo filter vận hành.

## Command cơ bản
```bash
python3 -m fanpage_agent.main triage-community \
  --brand-file data/sample/brand_profile.json \
  --comment-file data/comment_inbox.csv \
  --triage-file data/comment_triage.csv \
  --write-store
```

## Gửi digest từ store đã persist
```bash
python3 -m fanpage_agent.main deliver-triage-community \
  --brand-file data/sample/brand_profile.json \
  --triage-file data/comment_triage.csv \
  --from-store \
  --status new \
  --limit 5 \
  --save
```

## Filter hữu ích
```bash
# chỉ item urgent mới
python3 -m fanpage_agent.main deliver-triage-community \
  --brand-file data/sample/brand_profile.json \
  --triage-file data/comment_triage.csv \
  --from-store \
  --status new \
  --priority urgent

# chỉ item đang reopen cho reviewer cụ thể
python3 -m fanpage_agent.main deliver-triage-community \
  --brand-file data/sample/brand_profile.json \
  --triage-file data/comment_triage.csv \
  --from-store \
  --status reopened \
  --assigned-to qa-reviewer
```

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
- 1 message: Community Triage digest
- có `categories`, `priorities`, `statuses`
- có top item với `triage_id`, `status`, `message`, `recommended_action`

## Cron mapping (Hermes)
- Job 1: ingest + persist triage đều đặn mỗi 15-30 phút
- Job 2: gửi digest queue `new` hoặc `urgent` mỗi 30-60 phút
- Job 3: gửi queue `reopened` cho reviewer vào đầu ngày

Ví dụ mapping logic:
- `triage-community --write-store` chạy thường xuyên để cập nhật store
- `deliver-triage-community --from-store --status new --priority urgent` chạy cho queue nóng
- `deliver-triage-community --from-store --status reopened --assigned-to qa-reviewer` chạy cho reviewer queue

## Verify
- command exit code = 0
- JSON output có `summary.total_items > 0` khi queue có dữ liệu
- JSON output có `summary.by_status`
- JSON output có `delivery.sent_count = 1`
- triage rows persist trong `data/comment_triage.csv` hoặc tab Google Sheets `comment_triage`
- message Telegram không chứa item ngoài filter đã chọn
