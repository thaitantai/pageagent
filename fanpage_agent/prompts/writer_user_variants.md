# Write Variants

## Context

- **Thương hiệu:** {brand_id}
- **Chủ đề:** {topic}
- **Pillar:** {pillar}
- **Số lượng variant:** {count}
- **Page context:** {page_context_str}

## Research Evidence

Bắt buộc bám theo:

```
{evidence_text}
```

## Each Variant Must Use

Mỗi variant phải dùng **đúng TONE PERSONA** được chỉ định:

```
{persona_section}
```

## Output Format

```json
{{
  "variants": [
    {{
      "topic": "{topic}",
      "pillar": "{pillar}",
      "caption": "caption hoàn chỉnh (2-3 câu, có emoji, kết câu hỏi)",
      "hook": "câu mở đầu thu hút (1 câu)",
      "cta": "kêu gọi hành động (1 câu ngắn)",
      "format": "text_image|carousel|reel",
      "tone_tags": ["tone_persona_used", "keyword"],
      "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3"],
      "visual_brief": "mô tả ngắn visual style cho ảnh/carousel/reel — mood, màu sắc, cách bố trí, phong cách ảnh"
    }}
  ]
}}
```
