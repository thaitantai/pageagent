# Extract Findings

## Source Content

```
{truncated}
```

## Task

Trích xuất tối đa **5 findings** (chủ đề / thành phần / xu hướng) quan trọng nhất từ nội dung trên.

## Output Format

```json
{{
  "findings": [
    {{
      "pillar": "{pillar}",
      "topic": "chủ đề ngắn gọn (tối đa 100 ký tự)",
      "key_points": "1-2 câu tóm tắt nội dung chính",
      "relevance": 1,
      "source_type": "trend|ingredient|tip|myth|product"
    }}
  ]
}}
```

### Field Rules

| Field | Yêu cầu |
|-------|---------|
| `topic` | Tối đa 100 ký tự |
| `key_points` | 1-2 câu tóm tắt nội dung chính |
| `relevance` | 1-5 (mức độ liên quan đến skincare GenZ, 5 là cao nhất) |
| `source_type` | Một trong: `trend`, `ingredient`, `tip`, `myth`, `product` |

## Output Constraint

Chỉ trả về JSON, không markdown.
