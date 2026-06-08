from __future__ import annotations

from pathlib import Path

from fanpage_agent.core.types import ContentPackage, ContentVariant
from fanpage_agent.memory import PerformanceMemory
from fanpage_agent.tools.research.variant_scorer import VariantScorer


def _record_pattern(memory: PerformanceMemory, package_id: str, variant: ContentVariant, engagements: int) -> None:
    pkg = ContentPackage(package_id=package_id, brand_id="brand", scheduled_date="2026-06-10")
    pkg.variants = [variant]
    memory.record_publish(pkg, variant.variant_id, reach=1000, engagements=engagements, permalink="")


def test_variant_scorer_selects_variant_matching_stronger_patterns(tmp_path: Path) -> None:
    memory = PerformanceMemory(tmp_path / "memory.db")

    for idx in range(4):
        _record_pattern(
            memory,
            f"high-{idx}",
            ContentVariant(
                variant_id=f"high-{idx}",
                topic="routine",
                pillar="education",
                caption="caption",
                hook="Start with one simple skincare habit",
                cta="Save this",
                format="carousel",
                tone_tags=["practical"],
            ),
            engagements=80,
        )
    for idx in range(4):
        _record_pattern(
            memory,
            f"low-{idx}",
            ContentVariant(
                variant_id=f"low-{idx}",
                topic="sale",
                pillar="promotion",
                caption="caption",
                hook="Flash sale for everyone today",
                cta="Buy now",
                format="text_image",
                tone_tags=["urgent"],
            ),
            engagements=10,
        )

    package = ContentPackage(package_id="pkg", brand_id="brand", scheduled_date="2026-06-11")
    package.variants = [
        ContentVariant(
            variant_id="a",
            topic="routine",
            pillar="education",
            caption="caption",
            hook="Start with one simple skincare habit",
            cta="Save this",
            format="carousel",
            tone_tags=["practical"],
        ),
        ContentVariant(
            variant_id="b",
            topic="sale",
            pillar="promotion",
            caption="caption",
            hook="Flash sale for everyone today",
            cta="Buy now",
            format="text_image",
            tone_tags=["urgent"],
        ),
    ]

    breakdowns = VariantScorer(memory).score_package(package)

    assert package.winning_variant is not None
    assert package.winning_variant.variant_id == "a"
    assert package.variants[0].score is not None
    assert package.variants[1].score is not None
    assert package.variants[0].score > package.variants[1].score
    assert breakdowns[0].matched_patterns


def test_variant_scorer_uses_fallback_without_memory() -> None:
    package = ContentPackage(package_id="pkg", brand_id="brand", scheduled_date="2026-06-11")
    package.variants = [
        ContentVariant(
            variant_id="a",
            topic="topic",
            pillar="education",
            caption="caption",
            hook="hook",
            cta="cta",
            format="carousel",
        )
    ]

    breakdowns = VariantScorer().score_package(package)

    assert package.winning_variant is package.variants[0]
    assert package.variants[0].score == 50.0
    assert breakdowns[0].matched_patterns == []
