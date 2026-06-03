"""Hashtag Strategy Module (P3).

Generates tiered hashtags based on content, brand, and trending signals.
Supports LLM-powered generation with rule-based fallback, plus optional
performance tracking.

Tiers:
  - high_volume: broad, competitive (e.g. #skincare)
  - medium_volume: niche, topical (e.g. #skincaretips)
  - low_volume: long-tail, specific (e.g. #acnefreeroutine)
  - branded: brand-specific (e.g. #OutfitNhaGau)
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fanpage_agent.adapters.llm_client import build_llm_client
from fanpage_agent.config import Settings


# ---------------------------------------------------------------------------
#  Data models
# ---------------------------------------------------------------------------


@dataclass
class HashtagSuggestion:
    """A single hashtag suggestion with metadata."""

    tag: str
    tier: str  # high_volume | medium_volume | low_volume | branded
    relevance_score: float  # 0.0 – 1.0
    reason: str = ""


@dataclass
class HashtagSet:
    """Complete hashtag package for a piece of content."""

    content_topic: str
    pillar: str
    objective: str
    suggestions: list[HashtagSuggestion]
    recommended: list[str] = field(default_factory=list)  # selected tags
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_topic": self.content_topic,
            "pillar": self.pillar,
            "objective": self.objective,
            "suggestions": [
                {"tag": s.tag, "tier": s.tier, "relevance_score": s.relevance_score, "reason": s.reason}
                for s in self.suggestions
            ],
            "recommended": self.recommended,
            "generated_at": self.generated_at or datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> HashtagSet:
        return cls(
            content_topic=d.get("content_topic", ""),
            pillar=d.get("pillar", ""),
            objective=d.get("objective", ""),
            suggestions=[
                HashtagSuggestion(**s)
                for s in d.get("suggestions", [])
            ],
            recommended=d.get("recommended", []),
            generated_at=d.get("generated_at", ""),
        )


# ---------------------------------------------------------------------------
#  HashtagTracker — persists hashtag usage + performance
# ---------------------------------------------------------------------------


HASHTAG_TRACKER_COLUMNS = [
    "tracked_at",
    "content_topic",
    "pillar",
    "objective",
    "hashtag",
    "tier",
    "relevance_score",
    "is_recommended",
    "included_in_post",
    "permalink",
    "reach",
    "engagements",
]


class HashtagTracker:
    """CSV-backed hashtag usage log for performance analysis."""

    def __init__(self, tracker_path: str | Path | None = None) -> None:
        self.path = Path(tracker_path) if tracker_path else Path("data/hashtag_tracker.csv")

    def log(
        self,
        tag: str,
        tier: str,
        relevance_score: float,
        is_recommended: bool,
        content_topic: str = "",
        pillar: str = "",
        objective: str = "",
        included_in_post: bool = False,
        permalink: str = "",
        reach: int = 0,
        engagements: int = 0,
    ) -> None:
        row = {
            "tracked_at": datetime.now(timezone.utc).isoformat(),
            "content_topic": content_topic,
            "pillar": pillar,
            "objective": objective,
            "hashtag": tag,
            "tier": tier,
            "relevance_score": str(relevance_score),
            "is_recommended": "1" if is_recommended else "0",
            "included_in_post": "1" if included_in_post else "0",
            "permalink": permalink,
            "reach": str(reach),
            "engagements": str(engagements),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.path.exists()
        with self.path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=HASHTAG_TRACKER_COLUMNS)
            if not exists:
                writer.writeheader()
            writer.writerow(row)

    def log_set(self, hs: HashtagSet, *, included_tag_count: int = 0, permalink: str = "") -> None:
        """Log all recommended hashtags from a set."""
        for idx, tag_obj in enumerate(hs.suggestions):
            is_rec = tag_obj.tag in hs.recommended
            inc = idx < included_tag_count if included_tag_count > 0 else is_rec
            self.log(
                tag=tag_obj.tag,
                tier=tag_obj.tier,
                relevance_score=tag_obj.relevance_score,
                is_recommended=is_rec,
                content_topic=hs.content_topic,
                pillar=hs.pillar,
                objective=hs.objective,
                included_in_post=inc,
                permalink=permalink,
            )

    def read_performance(self, limit: int = 100) -> list[dict[str, str]]:
        """Read tracked hashtag rows (most recent first)."""
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        return rows[-limit:][::-1]

    def top_performing(self, tier: str | None = None, min_uses: int = 2) -> list[dict]:
        """Aggregate by hashtag, return avg engagement + total reach."""
        rows = self.read_performance(limit=5000)
        if not rows:
            return []

        agg: dict[str, dict] = {}
        for r in rows:
            if tier and r.get("tier") != tier:
                continue
            tag = r.get("hashtag", "")
            if not tag:
                continue
            if tag not in agg:
                agg[tag] = {"tag": tag, "tier": r.get("tier", ""), "uses": 0, "total_reach": 0, "total_engagements": 0}
            agg[tag]["uses"] += 1
            agg[tag]["total_reach"] += int(r.get("reach", 0) or 0)
            agg[tag]["total_engagements"] += int(r.get("engagements", 0) or 0)

        result = [v for v in agg.values() if v["uses"] >= min_uses]
        result.sort(key=lambda x: (x["total_engagements"], x["total_reach"]), reverse=True)
        return result

    def best_hashtags(self, limit: int = 10) -> list[str]:
        """Return top-N hashtags by engagement."""
        top = self.top_performing(min_uses=1)[:limit]
        return [t["tag"] for t in top if t["total_engagements"] > 0]


# ---------------------------------------------------------------------------
#  Rule-based fallback hashtag pools
# ---------------------------------------------------------------------------


DEFAULT_HIGH_VOLUME = [
    "#skincare", "#skincareroutine", "#beauty", "#skincaretips",
    "#glowingskin", "#facial", "#skincarecommunity", "#beautytips",
]

DEFAULT_MEDIUM_VOLUME = [
    "#skincaretipsforbeginners", "#acnefreeroutine", "#skincaresecrets",
    "#koreanskincare", "#skinbarrier", "#glassskin", "#hydrationstation",
    "#sunscreeneveryday", "#skincareobsessed", "#morningroutine",
]

DEFAULT_LOW_VOLUME = [
    "#skincaresimplified", "#dermatologistapproved", "#skinimalism",
    "#nontoxicbeauty", "#cleanbeautyproducts", "#skincarescience",
    "#skincareformom", "#affordableskincare", "#vitamincserum",
    "#retinolbeginner", "#sensitivekincare", "#multisteproutine",
]

DEFAULT_BRANDED = [
    "#OutfitNhaGau",
]


# ---------------------------------------------------------------------------
#  HashtagService
# ---------------------------------------------------------------------------


class HashtagService:
    """Generate tiered hashtags for content.

    Uses LLM when available, falls back to rule-based pools matched to pillar/topic.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: Any | None = None,
        tracker: HashtagTracker | None = None,
    ) -> None:
        self.settings = settings
        self.llm_client = llm_client
        self.tracker = tracker

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        topic: str,
        pillar: str = "",
        objective: str = "",
        angle: str = "",
        brand_id: str = "",
        use_llm: bool = True,
    ) -> HashtagSet:
        """Generate hashtags for a content topic.

        Args:
            topic: The main content topic.
            pillar: Content pillar (e.g. "education", "entertainment").
            objective: Content objective (e.g. "awareness", "conversion").
            angle: Content angle / hook.
            brand_id: Optional brand filter for branded tags.
            use_llm: If True and LLM available, try LLM first.

        Returns:
            HashtagSet with tiered suggestions + recommended slice.
        """
        if self.llm_client and use_llm:
            assert self.llm_client is not None  # narrow type for static analysis
            try:
                return self._generate_via_llm(topic, pillar, objective, angle, brand_id)
            except Exception:
                pass  # fall through to rule-based

        if self.tracker:
            best = self.tracker.best_hashtags(limit=5)
            if best:
                return self._generate_with_history(topic, pillar, objective, angle, brand_id, best)

        return self._generate_rule_based(topic, pillar, objective, brand_id)

    def append_hashtags(self, caption: str, hashtags: list[str], max_count: int = 5) -> str:
        """Append hashtags to a caption, limiting to max_count."""
        selected = hashtags[:max_count]
        tag_block = " ".join(selected)
        # Remove existing hashtags at the end to avoid duplication
        clean = re.sub(r"\s+#\w+", "", caption).strip()
        return f"{clean}\n\n{tag_block}"

    # ------------------------------------------------------------------
    #  LLM-based generation
    # ------------------------------------------------------------------

    def _generate_via_llm(
        self,
        topic: str,
        pillar: str,
        objective: str,
        angle: str,
        brand_id: str,
    ) -> HashtagSet:
        prompt = f"""You are a social media hashtag strategist for a skincare/healthcare GenZ brand.

Generate 15–18 hashtags ranked by relevance for the following content:

TOPIC: {topic}
PILLAR: {pillar or 'general'}
OBJECTIVE: {objective or 'awareness'}
ANGLE: {angle or 'educational'}

Organise into exactly four tiers:
- high_volume (3–4 broad, competitive tags)
- medium_volume (4–5 niche, topical tags)
- low_volume (4–5 long-tail, specific tags)
- branded (1–2 brand-specific tags)

Return ONLY valid JSON with this schema (no markdown, no extra text):
{{
  "suggestions": [
    {{"tag": "#...", "tier": "high_volume", "relevance_score": 0.95, "reason": "explanation"}},
    ...
  ]
}}

Then derive a "recommended" array of the top 5–8 tags (mix of all tiers, best fit).
Include both "suggestions" and "recommended" keys.
"""
        response = self.llm_client.complete(prompt, max_tokens=2000)
        raw = self._extract_json(response)
        data = json.loads(raw) if isinstance(raw, str) else raw

        suggestions = [
            HashtagSuggestion(
                tag=s["tag"].lstrip("#"),
                tier=s["tier"],
                relevance_score=float(s.get("relevance_score", 0.5)),
                reason=s.get("reason", ""),
            )
            for s in data.get("suggestions", [])
        ]
        # Ensure tags have # prefix
        recommended = [t.lstrip("#") for t in data.get("recommended", [])]

        return HashtagSet(
            content_topic=topic,
            pillar=pillar,
            objective=objective,
            suggestions=suggestions,
            recommended=recommended,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _extract_json(raw: str) -> str:
        """Extract JSON from LLM response (strip markdown fences)."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove first and last code fence
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    # ------------------------------------------------------------------
    #  Rule-based generation
    # ------------------------------------------------------------------

    def _generate_rule_based(
        self,
        topic: str,
        pillar: str,
        objective: str,
        brand_id: str,
    ) -> HashtagSet:
        """Fallback: pick from pools based on topic keywords."""
        topic_lower = topic.lower()

        # Score relevance from pools
        suggestions: list[HashtagSuggestion] = []
        seen: set[str] = set()

        for pool_tags, tier, base_score in [
            (DEFAULT_HIGH_VOLUME, "high_volume", 0.7),
            (DEFAULT_MEDIUM_VOLUME, "medium_volume", 0.6),
            (DEFAULT_LOW_VOLUME, "low_volume", 0.5),
        ]:
            for tag in pool_tags:
                clean_tag = tag.lstrip("#").lower()
                if clean_tag in seen:
                    continue
                seen.add(clean_tag)

                score = base_score
                # Boost if topic keyword appears in tag
                for kw in topic_lower.split():
                    if kw in clean_tag:
                        score = min(1.0, score + 0.15)
                # Boost for pillar match
                if pillar and pillar.lower() in clean_tag:
                    score = min(1.0, score + 0.1)

                suggestions.append(HashtagSuggestion(
                    tag=clean_tag,
                    tier=tier,
                    relevance_score=round(score, 2),
                    reason="pool match" if score == base_score else "keyword match",
                ))

        # Add branded tags
        for tag in DEFAULT_BRANDED:
            clean_tag = tag.lstrip("#")
            if clean_tag not in seen:
                suggestions.append(HashtagSuggestion(
                    tag=clean_tag,
                    tier="branded",
                    relevance_score=0.9,
                    reason="brand hashtag",
                ))
                seen.add(clean_tag)

        # Top 8 by score
        suggestions.sort(key=lambda s: s.relevance_score, reverse=True)
        recommended = [s.tag for s in suggestions[:8]]

        return HashtagSet(
            content_topic=topic,
            pillar=pillar,
            objective=objective,
            suggestions=suggestions,
            recommended=recommended,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _generate_with_history(
        self,
        topic: str,
        pillar: str,
        objective: str,
        angle: str,
        brand_id: str,
        best_from_history: list[str],
    ) -> HashtagSet:
        """Start with best-performing tags, fill gaps with rule-based."""
        suggestions: list[HashtagSuggestion] = []
        seen: set[str] = set()

        for tag in best_from_history:
            clean = tag.lstrip("#")
            if clean in seen:
                continue
            seen.add(clean)
            suggestions.append(HashtagSuggestion(
                tag=clean,
                tier="medium_volume",
                relevance_score=0.85,
                reason="top performer from history",
            ))

        # Fill to 10 minimum with rule-based
        for pool_tags, tier, base_score in [
            (DEFAULT_HIGH_VOLUME, "high_volume", 0.7),
            (DEFAULT_MEDIUM_VOLUME, "medium_volume", 0.55),
            (DEFAULT_LOW_VOLUME, "low_volume", 0.45),
        ]:
            if len(suggestions) >= 12:
                break
            for tag in pool_tags:
                clean = tag.lstrip("#")
                if clean in seen:
                    continue
                seen.add(clean)
                suggestions.append(HashtagSuggestion(
                    tag=clean,
                    tier=tier,
                    relevance_score=base_score,
                    reason="pool fill",
                ))

        suggestions.sort(key=lambda s: s.relevance_score, reverse=True)
        recommended = [s.tag for s in suggestions[:8]]

        return HashtagSet(
            content_topic=topic,
            pillar=pillar,
            objective=objective,
            suggestions=suggestions,
            recommended=recommended,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
