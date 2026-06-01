# Fanpage Agent V1 Local Scaffold

Local scaffold cho Fanpage Agent V1.

## Setup OpenRouter để test thật
1. Copy env template:
```bash
cp .env.example .env
```

2. Điền `LLM_API_KEY` thật của OpenRouter vào `.env`.

3. Đặt `LLM_MODEL` là model ưu tiên, và `LLM_MODEL_CANDIDATES` là danh sách fallback, ví dụ:
```env
LLM_MODEL=google/gemma-3-27b-it:free
LLM_MODEL_CANDIDATES=meta-llama/llama-3.3-8b-instruct:free,mistralai/mistral-small-3.2-24b-instruct:free,qwen/qwen3-14b:free
LLM_MAX_TOKENS=900
# nếu account có credit, có thể dùng:
# LLM_MODEL=openai/gpt-4.1-mini
# LLM_MODEL_CANDIDATES=
# LLM_MAX_TOKENS=1200
```

4. Repo giờ tự đọc `.env`, nên không cần `source .env` thủ công nữa. Khi model đầu fail kiểu `No endpoints found`, `404`, `402 insufficient credits`, client sẽ tự thử model kế tiếp trong `LLM_MODEL_CANDIDATES`. `LLM_MAX_TOKENS` cho phép hạ request size khi account credit thấp.

## Chạy test
```bash
python3 -m unittest discover -s tests -v
```

## Sinh weekly plan
```bash
python3 -m fanpage_agent.main plan-week \
  --brand-file data/sample/brand_profile.json \
  --start-date 2026-06-01 \
  --days 3 \
  --save
```

## Sinh caption package
```bash
python3 -m fanpage_agent.main write-caption \
  --brand-file data/sample/brand_profile.json \
  --topic "5 dấu hiệu da đang thiếu nước" \
  --pillar education \
  --objective engagement \
  --format post_short \
  --save
```

## Gửi preview Telegram thật
```bash
export TELEGRAM_BOT_TOKEN=your-bot-token
export TELEGRAM_CHAT_ID=your-chat-id
python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type plan \
  --input-file artifacts/plans/weekly-plan-brand_abc-2026-06-30.json

python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type approval \
  --input-file artifacts/approvals/approval-queue.json

python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type metrics \
  --input-file artifacts/metrics/metrics-backlog.json

python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type research \
  --input-file artifacts/research/research-brief.json

python3 -m fanpage_agent.main deliver-research-brief \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --comment-file data/comment_inbox.csv \
  --campaign-file data/campaign_notes.json \
  --save
```

## Approval queue từ calendar
```bash
python3 -m fanpage_agent.main list-calendar-items \
  --calendar-file data/content_calendar.csv \
  --approval-status pending

python3 -m fanpage_agent.main deliver-approval-queue \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --approval-status pending \
  --limit 5
```

`run-daily --write-calendar --save` và `deliver-daily-packet --write-calendar --save`
sẽ lưu thêm `artifacts.caption_package` và ghi `draft_caption_ref` vào row calendar để người duyệt mở artifact rồi gọi `approve-caption` / `reject-caption`.

## Ghi metric thật sau publish
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

## Metrics backlog để follow-up bài đã publish
```bash
python3 -m fanpage_agent.main list-calendar-items \
  --calendar-file data/content_calendar.csv \
  --status published \
  --metrics-pending

python3 -m fanpage_agent.main deliver-metrics-backlog \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --status published \
  --metrics-pending \
  --limit 5
```

## Community triage + state workflow
```bash
python3 -m fanpage_agent.main triage-community \
  --brand-file data/sample/brand_profile.json \
  --comment-file data/comment_inbox.csv \
  --triage-file data/comment_triage.csv \
  --write-store

python3 -m fanpage_agent.main approve-triage-reply \
  --triage-file data/comment_triage.csv \
  --triage-id <TRIAGE_ID> \
  --approved-by Tai \
  --approved-at 2026-06-24T09:00:00 \
  --assigned-to closer-1

python3 -m fanpage_agent.main mark-triage-reply-sent \
  --triage-file data/comment_triage.csv \
  --triage-id <TRIAGE_ID> \
  --sent-at 2026-06-24T09:15:00 \
  --reply-permalink https://facebook.com/comment/123 \
  --assigned-to closer-1

python3 -m fanpage_agent.main resolve-triage-item \
  --triage-file data/comment_triage.csv \
  --triage-id <TRIAGE_ID> \
  --resolved-at 2026-06-24T10:00:00 \
  --assigned-to closer-1

python3 -m fanpage_agent.main list-triage-items \
  --triage-file data/comment_triage.csv \
  --status reopened \
  --assigned-to qa-reviewer

python3 -m fanpage_agent.main deliver-triage-community \
  --brand-file data/sample/brand_profile.json \
  --triage-file data/comment_triage.csv \
  --from-store \
  --status new \
  --limit 3
```

## Hermes cron deployment

Cron jobs thật đang được triển khai qua Hermes no-agent script jobs để tránh gửi trùng Telegram:

```bash
hermes cron list
python3 -m fanpage_agent.main hermes-cron-status
python3 -m fanpage_agent.main ops-status
python3 -m fanpage_agent.main ops-status --fail-on-stale
```

Chi tiết mapping job/schedule/wrapper/runbook xem: [`docs/cron/hermes-jobs.md`](docs/cron/hermes-jobs.md).

## Next implementation tasks

- **P0:** Theo dõi lần chạy tự động đầu tiên của 9 cron jobs, kiểm tra `last_status`, output local và artifact freshness.
- **P0:** Nếu job nào lỗi, pause job đó, đọc output/error, sửa wrapper hoặc dữ liệu nguồn rồi resume.
- **P2:** Thêm dashboard HTML/Markdown local tổng hợp cron health + artifact health.

## Ghi chú
- Bản này đã có lane OpenAI-compatible thật.
- Đã có eval-all tối thiểu.
- Đã có Telegram delivery thật cho artifact preview.
- Đã có triage persistence + approve/reject/mark-replied/resolve/reopen workflow.
- Đã có store-backed triage digest delivery với filter theo status/priority/assigned_to.
- Đã verify Google Sheets live read/write/readback cho calendar; triage state path có local + Google adapter parity.
