{{
  "task": "generate_caption_package",
  "topic": "{topic}",
  "pillar": "{pillar}",
  "objective": "{objective}",
  "format": "{fmt}",
  "brand_context": {brand_context},

  "requirements": {{
    "minimum_variants": 1,
    "return_json_only": true,

    "variant_fields": [
      "label",
      "hook",
      "caption",
      "cta",
      "tone_tags",
      "visual_brief"
    ],

    "top_level_fields": [
      "topic",
      "variants",
      "dos",
      "donts"
    ]
  }}
}}
