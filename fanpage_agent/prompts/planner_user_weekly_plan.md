{{
  "task": "generate_weekly_plan",
  "start_date": "{start_date}",
  "requested_day_count": {days},
  "brand_context": {brand_context},
  "research_brief": {research_brief},

  "requirements": {{
    "plan_title_format": "weekly-plan-{brand_id}-{start_date}",
    "one_plan_day_per_requested_day": true,
    "days_output_must_be_array": "Return days as a JSON array of day objects, never as a number.",
    "return_json_only": true,

    "day_fields": [
      "date",
      "pillar",
      "objective",
      "topic",
      "angle",
      "format",
      "hook",
      "cta",
      "visual_brief",
      "risk_notes"
    ],

    "top_level_fields": [
      "plan_title",
      "days",
      "strategy_notes",
      "gaps_or_assumptions"
    ]
  }}
}}
