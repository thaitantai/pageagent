# Post Metrics Recording

## Mục tiêu
Sau khi bài đã được publish, cập nhật metric thật vào content calendar và `post_metrics` store để weekly report và research loop đọc được dữ liệu mới nhất.

## Command cơ bản
```bash
python3 -m fanpage_agent.main record-post-metrics \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --calendar-id weekly-plan-brand_abc-2026-06-25-1 \
  --reach 1800 \
  --engagements 126 \
  --leads 11 \
  --recorded-at 2026-06-26T08:00:00
```

## Hành vi
- tìm row `calendar_id` trong content calendar
- cập nhật:
  - `reach`
  - `engagement_rate = engagements / reach`
  - `last_updated`
- upsert 1 row vào `post_metrics` dựa trên `published_at + topic`
- trả JSON gồm:
  - `calendar`
  - `metric`

## Rule vận hành
- nên chạy sau `publish-post`
- `published_at` và `permalink` nên có trước khi record metrics
- command này không gửi Telegram; nó làm giàu store để research/report dùng lại

## Verify checklist
- `publish-post` đã chạy thành công
- `record-post-metrics` trả `reach`, `engagement_rate`, `engagements`, `leads` đúng
- `weekly-report` đọc thấy row metric mới
