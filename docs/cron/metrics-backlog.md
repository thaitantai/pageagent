# Metrics Backlog Cron

## Mục tiêu
Tìm các bài đã publish nhưng chưa được nhập metrics thật, rồi gửi digest Telegram để người vận hành biết post nào cần cập nhật `reach / engagements / leads`.

## Command cơ bản
```bash
python3 -m fanpage_agent.main deliver-metrics-backlog \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --status published \
  --metrics-pending \
  --limit 5
```

## Hành vi
- đọc `content_calendar`
- lọc row có:
  - `status = published`
  - đã có `published_at` hoặc `permalink`
  - `reach <= 0`
- render digest Telegram compact
- gửi 1 message với các item cần nhập metrics

## Khi dùng
- chạy mỗi sáng hoặc cuối ngày sau khi team đã publish bài
- dùng như queue follow-up trước khi chạy `record-post-metrics`

## Command follow-up
```bash
python3 -m fanpage_agent.main record-post-metrics \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --calendar-id <CALENDAR_ID> \
  --reach 1800 \
  --engagements 126 \
  --leads 11 \
  --recorded-at 2026-06-29T08:00:00
```

## Verify checklist
- `deliver-metrics-backlog` chỉ show bài published chưa có metrics
- item đã chạy `record-post-metrics` không còn nằm trong backlog
- Telegram digest có `calendar_id` + `permalink` để operator tra nhanh
