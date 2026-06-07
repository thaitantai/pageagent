# Research Brief Delivery

## Mục tiêu
Build research brief từ history + metrics + comment inbox + campaign notes rồi gửi thẳng Telegram trong một lệnh, đồng thời lưu artifact để audit hoặc dùng lại cho preview/send thủ công.

## Command
```bash
python3 -m fanpage_agent.main deliver-research-brief \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --comment-file data/comment_inbox.csv \
  --campaign-file data/campaign_notes.json \
  --save
```

## Output
- stdout: JSON payload của research brief kèm `delivery`
- artifact: `artifacts/research/research-brief.json`
- Telegram: 1 message dạng `Research Brief`

## Verify
- `delivery.sent_count == 1`
- `delivery.results[0].result.message_id` có giá trị
- artifact `artifacts/research/research-brief.json` tồn tại
- message có `Research Brief`
- message có ít nhất 1 frequent question và 1 recommendation

## Notes
- Nếu chỉ muốn render lại artifact đã có, dùng:
```bash
python3 -m fanpage_agent.main preview-telegram \
  --artifact-type research \
  --input-file artifacts/research/research-brief.json
```

- Nếu muốn gửi lại artifact đã có mà không rebuild, dùng:
```bash
python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type research \
  --input-file artifacts/research/research-brief.json
```
