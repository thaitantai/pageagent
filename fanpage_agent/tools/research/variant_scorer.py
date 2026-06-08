"""Score content variants with learned performance patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from fanpage_agent.core.types import ContentPackage, ContentVariant, PerformancePattern
from fanpage_agent.memory import PerformanceMemory


@dataclass(frozen=True)
class VariantScoreBreakdown:
    """Explain why a variant received its score."""

    variant_id: str
    score: float
    matched_patterns: list[dict[str, object]] = field(default_factory=list)


class VariantScorer:
    """Ranks A/B variants using performance memory.

    The scorer is deterministic and local-only. It does not call an LLM; it uses
    patterns learned from published posts so publisher/reviewer code can choose a
    default winner while still letting humans override it.
    """

    DEFAULT_WEIGHTS = {
        "pillar": 0.35,
        "format": 0.25,
        "tone": 0.20,
        "hook_style": 0.20,
    }

    def __init__(
        self,
        memory: PerformanceMemory | None = None,
        *,
        weights: dict[str, float] | None = None,
        fallback_score: float = 50.0,
    ) -> None:
        self.memory = memory
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        self.fallback_score = fallback_score

    def score_package(self, package: ContentPackage) -> list[VariantScoreBreakdown]:
        """Score all package variants and set package.winning_variant."""

        patterns = self._load_patterns()
        breakdowns: list[VariantScoreBreakdown] = []
        for variant in package.variants:
            breakdown = self.score_variant(variant, patterns=patterns)
            variant.score = breakdown.score
            breakdowns.append(breakdown)

        package.winning_variant = package.best_variant()
        return breakdowns

    def score_variant(
        self,
        variant: ContentVariant,
        *,
        patterns: Iterable[PerformancePattern] | None = None,
    ) -> VariantScoreBreakdown:
        """Return a score and explanation for one variant."""

        pattern_list = list(patterns) if patterns is not None else self._load_patterns()
        if not pattern_list:
            return VariantScoreBreakdown(variant_id=variant.variant_id, score=self.fallback_score)

        max_engagement = max((p.avg_engagement for p in pattern_list), default=0.0)
        if max_engagement <= 0:
            return VariantScoreBreakdown(variant_id=variant.variant_id, score=self.fallback_score)

        matches: list[dict[str, object]] = []
        weighted_score = 0.0
        total_weight = 0.0

        for pattern in pattern_list:
            if not self._matches(pattern, variant):
                continue
            weight = self.weights.get(pattern.pattern_type, 0.0)
            if weight <= 0:
                continue
            normalized = pattern.avg_engagement / max_engagement
            contribution = normalized * pattern.confidence * weight * 100
            weighted_score += contribution
            total_weight += weight
            matches.append(
                {
                    "pattern_type": pattern.pattern_type,
                    "value": pattern.value,
                    "avg_engagement": pattern.avg_engagement,
                    "confidence": pattern.confidence,
                    "contribution": round(contribution, 2),
                }
            )

        if total_weight <= 0:
            return VariantScoreBreakdown(variant_id=variant.variant_id, score=self.fallback_score)

        score = min(100.0, max(0.0, weighted_score / total_weight))
        return VariantScoreBreakdown(
            variant_id=variant.variant_id,
            score=round(score, 2),
            matched_patterns=matches,
        )

    def _load_patterns(self) -> list[PerformancePattern]:
        if self.memory is None:
            return []
        return self.memory.get_patterns(limit=200)

    def _matches(self, pattern: PerformancePattern, variant: ContentVariant) -> bool:
        if pattern.pattern_type == "pillar":
            return variant.pillar == pattern.value
        if pattern.pattern_type == "format":
            return variant.format == pattern.value
        if pattern.pattern_type == "tone":
            return pattern.value in variant.tone_tags
        if pattern.pattern_type == "hook_style":
            hook_style = " ".join(variant.hook.split()[:8])
            return hook_style == pattern.value
        return False
