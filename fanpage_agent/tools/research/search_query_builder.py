"""Smart search query builder for ResearchTool.

Generates diverse, intent-driven search queries by leveraging
all available context instead of hardcoded Vietnamese templates.

Sources (in priority order):
  1. override_queries — explicit human override (unchanged)
  2. product_topic.research_query — already generated with product+pain+benefit+angle
  3. campaign_focus + intent templates
  4. brand profile pain points / objections
  5. frequent questions from comments/inbox
  6. top_performing_topics — continue exploring what works
  7. industry_focus — fallback only when nothing else exists
"""

from __future__ import annotations

from typing import Any

# ──────────────────────────────────────────────
# Intent templates cho campaign_focus items
# Không chỉ "xu hướng" + "review" + "mẹo" — mở rộng
# sang nhiều góc nhìn để DDG trả kết quả đa dạng hơn
# ──────────────────────────────────────────────
_INTENT_TEMPLATES: list[tuple[str, str]] = [
    ("trend", "xu hướng {t} 2026"),
    ("review", "{t} review"),
    ("how_to", "cách {t}"),
    ("danger", "tác hại {t}"),
    ("comparison", "{t} vs"),
    ("myth", "hiểu lầm về {t}"),
    ("ingredient", "thành phần {t}"),
    ("faq", "{t} có tốt không"),
    ("science", "{t} nghiên cứu"),
    ("routine", "routine {t}"),
    ("dau_hieu", "dấu hiệu {t}"),
    ("chon", "cách chọn {t}"),
]

# Giới hạn query đầu ra
_MAX_QUERIES = 12


def build_search_queries(
    campaign_focus: list[str],
    top_performing_topics: list[str],
    override_queries: list[str] | None = None,
    product_topics: list | None = None,
    frequent_questions: list[str] | None = None,
    page_context: dict[str, Any] | None = None,
    industry_focus: str | None = None,
) -> list[str]:
    """Generate search queries from all available context.

    Priority chain (higher = used first):
      1. override_queries (explicit human input)
      2. product_topic.research_query  (richest, already intent-aware)
      3. campaign_focus + intent templates  (broad coverage)
      4. brand pain points / objections     (real customer language)
      5. frequent_questions from comments    (real customer questions)
      6. top_performing_topics               (double down on what works)
      7. industry_focus fallback             (last resort)

    Returns deduplicated list, max ``_MAX_QUERIES`` items.
    """
    if override_queries:
        return override_queries[:_MAX_QUERIES]

    seen: set[str] = set()
    queries: list[str] = []

    # ── Tier 1: Product topic research_queries (already angle-aware) ──
    if product_topics:
        for pt in product_topics:
            rq = _get_attr(pt, "research_query", "")
            if rq and rq not in seen:
                seen.add(rq)
                queries.append(rq)
                if len(queries) >= _MAX_QUERIES:
                    return queries

            # Cũng sinh thêm các biến thể từ topic name + angle
            topic_name = _get_attr(pt, "topic", "")
            angle = _get_attr(pt, "angle", "")
            if topic_name and angle:
                variants = _angle_to_queries(topic_name, angle)
                for v in variants:
                    if v not in seen:
                        seen.add(v)
                        queries.append(v)
                        if len(queries) >= _MAX_QUERIES:
                            return queries

    # ── Tier 2: Campaign focus + intent templates ──
    if campaign_focus:
        for cf in campaign_focus:
            clean = cf.lower().strip()
            if not clean:
                continue
            for _intent, template in _INTENT_TEMPLATES:
                q = template.format(t=clean)
                if q not in seen:
                    seen.add(q)
                    queries.append(q)
                    if len(queries) >= _MAX_QUERIES:
                        return queries

    # ── Tier 3: Brand pain points from page_context ──
    if page_context:
        pain_queries = _pain_point_queries(page_context, seen)
        for q in pain_queries:
            queries.append(q)
            if len(queries) >= _MAX_QUERIES:
                return queries

    # ── Tier 4: Frequent questions from comments ──
    if frequent_questions:
        for q in frequent_questions:
            clean_q = q.strip().lower()
            if not clean_q:
                continue
            # Limit length to avoid noise
            if 8 < len(clean_q) < 200:
                if clean_q not in seen:
                    seen.add(clean_q)
                    queries.append(clean_q)
                    if len(queries) >= _MAX_QUERIES:
                        return queries

    # ── Tier 5: Top performing topics ──
    if top_performing_topics:
        for t in top_performing_topics:
            clean = t.strip().lower()
            if not clean:
                continue
            variants = [
                clean,
                f"xu hướng {clean} 2026",
            ]
            for v in variants:
                if v not in seen:
                    seen.add(v)
                    queries.append(v)
                    if len(queries) >= _MAX_QUERIES:
                        return queries

    # ── Fallback: industry_focus ──
    if not queries:
        industry = (industry_focus or "").strip()
        if industry:
            fallbacks = [
                f"xu hướng {industry} 2026",
                f"{industry} mới nhất",
                f"mẹo {industry} hiệu quả",
            ]
            for fb in fallbacks:
                if fb not in seen:
                    seen.add(fb)
                    queries.append(fb)

    return queries[:_MAX_QUERIES]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _get_attr(obj: Any, attr: str, default: str = "") -> str:
    """Get attribute or dict key safely."""
    if isinstance(obj, dict):
        return str(obj.get(attr, default) or default)
    return str(getattr(obj, attr, default) or default)


def _angle_to_queries(topic: str, angle: str) -> list[str]:
    """Map a product topic's angle to search query variants."""
    angle_queries: dict[str, list[str]] = {
        "education": [topic, f"kiến thức {topic}"],
        "myth_busting": [f"hiểu lầm về {topic}", f"sự thật về {topic}"],
        "how_to": [f"cách {topic}", f"hướng dẫn {topic}"],
        "comparison": [f"so sánh {topic}", f"{topic} hay"],
        "faq": [f"câu hỏi về {topic}", f"{topic} có tốt không"],
        "buying_guide": [f"cách chọn {topic}", f"mua {topic}"],
        "checklist": [f"lưu ý khi {topic}", f"cần biết về {topic}"],
        "red_flags": [f"dấu hiệu {topic}", f"tránh {topic}"],
        "review": [f"{topic} review", f"đánh giá {topic}"],
    }
    return angle_queries.get(angle, [topic])


def _pain_point_queries(
    page_context: dict[str, Any],
    seen: set[str],
) -> list[str]:
    """Extract real customer pain points / objections as search queries."""
    queries: list[str] = []
    audiences = page_context.get("target_audiences", []) or page_context.get("audiences", [])
    if isinstance(audiences, dict):
        audiences = [audiences]

    for segment in audiences:
        if not isinstance(segment, dict):
            continue
        for key in ("pain_points", "objections"):
            items = segment.get(key, [])
            if isinstance(items, str):
                items = [items]
            for item in items:
                clean = str(item).strip().lower()
                if clean and clean not in seen and 5 < len(clean) < 150:
                    seen.add(clean)
                    queries.append(clean)

    # Also extract from products_services do_not_claim
    products = page_context.get("products_services", []) or page_context.get("products", [])
    if isinstance(products, dict):
        products = [products]
    for prod in products:
        if not isinstance(prod, dict):
            continue
        for key in ("do_not_claim", "benefits"):
            items = prod.get(key, [])
            if isinstance(items, str):
                items = [items]
            for item in items:
                clean = str(item).strip().lower()
                if clean and clean not in seen and 5 < len(clean) < 150:
                    seen.add(clean)
                    queries.append(clean)

    return queries
