"""Pure strategy helpers shared by StrategistTool and StrategistAgent.

Single source of truth for the Vietnamese keyword → pillar matching, the
default posting cadence, pillar-mix math, strategy-variant scoring, and
content-angle selection. No LLM calls, no I/O — every function here is
deterministic and unit-testable.

The two strategists use DIFFERENT pillar taxonomies (StrategistTool follows
the brand-profile pillar names; StrategistAgent follows its template keys),
so ``infer_pillar`` takes a taxonomy and both vocabularies live here side
by side instead of drifting apart in two files.
"""

from __future__ import annotations

import re
from typing import Any

# ── Keyword groups (semantic signal → keywords) ─────────────────────
# Unified from the two previous _infer_pillar implementations. Where they
# disagreed, the newer agents/strategist.py wording wins: bare "sáng"/"tối"
# were dropped (too loose — "buổi sáng"/"buổi tối" stay), bare "thật" was
# dropped from the myth group.
KEYWORD_GROUPS: dict[str, list[str]] = {
    "routine": ["routine", "buổi sáng", "buổi tối", "layer", "bước"],
    "ingredient": [
        "vitamin", "retinol", "niacinamide", "bha", "aha", "thành phần", "ingredient",
    ],
    "myth": ["myth", "lầm tưởng", "sai lầm"],
    "review": ["review", "so sánh", "top", "sản phẩm", "đáng mua", "giá"],
    "viet_brand": ["việt", "cocoon", "thuần việt", "nội địa"],
    "lifestyle": ["genz", "sinh viên", "văn phòng", "du lịch"],
}

# Ordered (group → pillar name) per consumer. Order matters: first match wins
# (e.g. "Mỹ phẩm thuần Việt nào đáng mua" must hit viet_brand, not review).
TOOL_PILLAR_TAXONOMY: list[tuple[str, str]] = [
    ("routine", "routine_guide"),
    ("viet_brand", "viet_brand_spotlight"),
    ("ingredient", "education"),
    ("myth", "myth_busting"),
    ("review", "product_review"),
]
TOOL_PILLAR_DEFAULT = "education"

AGENT_PILLAR_TAXONOMY: list[tuple[str, str]] = [
    ("routine", "skincare_routine"),
    ("ingredient", "ingredient_deepdive"),
    ("myth", "myth_busting"),
    ("review", "product_review"),
    ("lifestyle", "genz_lifestyle"),
]
AGENT_PILLAR_DEFAULT = "medical_reference"

DEFAULT_POSTING_TIMES: list[str] = ["09:00", "12:00", "20:00"]


def infer_pillar(
    text: str,
    taxonomy: list[tuple[str, str]],
    default: str,
) -> str:
    """Map free text to a pillar name using the shared keyword groups."""
    lowered = text.lower()
    for group, pillar in taxonomy:
        if any(keyword in lowered for keyword in KEYWORD_GROUPS[group]):
            return pillar
    return default


# ── Pillar mix ───────────────────────────────────────────────────────


def compute_pillar_mix(
    pillar_names: list[str],
    default_mix: dict[str, float],
    recommended_pillars: list[str] | None = None,
) -> dict[str, float]:
    """Distribute pillar percentages from a default mix + research boosts.

    Keeps only pillars present in ``pillar_names``, splits the remainder
    evenly over extra pillars, boosts up to three research-recommended
    pillars, and normalizes to 1.0.
    """
    if not pillar_names:
        return dict(default_mix)

    mix = {k: v for k, v in default_mix.items() if k in pillar_names}

    extra_pillars = [p for p in pillar_names if p not in mix]
    if extra_pillars:
        remainder = 1.0 - sum(mix.values())
        each = remainder / len(extra_pillars)
        for p in extra_pillars:
            mix[p] = round(each, 2)

    total = sum(mix.values())
    if total > 0:
        mix = {k: round(v / total, 2) for k, v in mix.items()}

    for p in (recommended_pillars or [])[:3]:
        if p in mix:
            mix[p] = min(mix[p] + 0.10, 0.50)

    total = sum(mix.values())
    if total > 0:
        mix = {k: round(v / total, 2) for k, v in mix.items()}

    return mix


def compute_weekly_frequency(fanpage_goals: list[str]) -> int:
    """Posting cadence from brand goals: reach+engagement → daily, else 5/week."""
    goals = {g.lower() for g in fanpage_goals}
    if "reach" in goals and "engagement" in goals:
        return 7
    if "lead" in goals:
        return 5
    return 5


# ── Strategy variant scoring ─────────────────────────────────────────


def score_strategy_variants(
    item: dict[str, Any],
    feedback_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Score the three canonical content-strategy variants for a schedule item.

    Inputs are the schedule item's angle/safety fields plus optional
    performance-feedback signals; output is sorted best-first.
    """
    angle = str(item.get("content_angle") or "education")
    safe_use = str(item.get("safe_use") or "public_draft")
    review_required = bool(item.get("review_required"))
    candidates = [
        {
            "name": "community_education",
            "format": "text_image",
            "hook_style": "relatable_problem",
            "score": 0.62,
            "why": "An toan cho noi dung giao duc va de duyet.",
        },
        {
            "name": "checklist_carousel",
            "format": "carousel",
            "hook_style": "saveable_checklist",
            "score": 0.66,
            "why": "Phu hop khi can nhieu dieu kien, uu-nhuoc diem hoac review nguon.",
        },
        {
            "name": "soft_buying_guide",
            "format": "carousel",
            "hook_style": "decision_helper",
            "score": 0.58,
            "why": "Chi dung khi evidence du manh va van giu CTA mem.",
        },
    ]
    signals = (feedback_context or {}).get("signals", [])
    preferred_formats = {
        str(signal.get("format"))
        for signal in signals
        if isinstance(signal, dict) and signal.get("format")
    }
    for candidate in candidates:
        if candidate["format"] in preferred_formats:
            candidate["score"] += 0.07
        if angle in {"checklist", "fair_comparison"} and candidate["name"] == "checklist_carousel":
            candidate["score"] += 0.18
        if angle == "guarded_buying_guide" and candidate["name"] == "soft_buying_guide":
            candidate["score"] += 0.22
        if angle == "cautionary_post" and candidate["name"] == "community_education":
            candidate["score"] += 0.16
        if safe_use != "public_draft" and candidate["name"] == "soft_buying_guide":
            candidate["score"] -= 0.3
        if review_required and candidate["name"] == "checklist_carousel":
            candidate["score"] += 0.08
        candidate["score"] = round(max(0, min(1, candidate["score"])), 2)
    return sorted(candidates, key=lambda value: value["score"], reverse=True)


def select_content_angle(topic: dict[str, Any], safe_use: str) -> str:
    """Classify a research topic into a content angle given its safety tier."""
    text = str(topic.get("topic", "")).lower()
    codes = {str(code) for code in topic.get("reason_codes", [])}
    score = float(topic.get("total_score") or 0)
    if "comparison" in text or "so sánh" in text:
        return "fair_comparison"
    if "sai lầm" in text or "myth" in text or "lầm tưởng" in text:
        return "cautionary_post"
    if "checklist" in text or safe_use == "human_review_only":
        return "checklist"
    if any(code.startswith("affiliate") or code.startswith("product") for code in codes):
        return "guarded_buying_guide" if score >= 0.8 and safe_use == "public_draft" else "checklist"
    if any(word in text for word in ["review", "top", "sản phẩm", "san pham"]):
        return "fair_comparison"
    return "education"


# ── LLM output parsing ───────────────────────────────────────────────


def extract_json(text: str) -> str:
    """Extract JSON from an LLM response (handles markdown code fences)."""
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text.strip()
