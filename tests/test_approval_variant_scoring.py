import json
from pathlib import Path

from fanpage_agent.core.types import ContentPackage, ContentVariant
from fanpage_agent.cli_commands.content import enrich_items_with_variant_scores
from fanpage_agent.memory import PerformanceMemory
from fanpage_agent.tools.publishing.telegram_formatter import TelegramFormatterTool


def _record_pattern(memory_db: Path, pillar: str, variant_id: str, engagements: int) -> None:
    package = ContentPackage(
        package_id=f"pkg-{variant_id}",
        brand_id="brand",
        scheduled_date="2026-06-24",
        variants=[
            ContentVariant(
                variant_id=variant_id,
                topic="Routine cap am",
                pillar=pillar,
                caption="Caption",
                hook="Hook tot cho da kho",
                cta="Nhan tin de duoc tu van",
                format="post_short",
                tone_tags=["practical"],
            )
        ],
    )
    PerformanceMemory(memory_db).record_publish(
        package,
        variant_id=variant_id,
        reach=1000,
        engagements=engagements,
        permalink=f"https://example.test/{variant_id}",
    )


def test_enrich_items_with_variant_scores_recommends_best_caption_variant(tmp_path):
    memory_db = tmp_path / "memory.db"
    _record_pattern(memory_db, "education", "strong", engagements=120)
    _record_pattern(memory_db, "promo", "weak", engagements=10)

    caption_file = tmp_path / "caption.json"
    caption_file.write_text(
        json.dumps(
            {
                "topic": "Routine cap am",
                "variants": [
                    {
                        "label": "A",
                        "hook": "Hook thuong",
                        "caption": "Caption A",
                        "cta": "Nhan tin",
                        "tone_tags": ["practical"],
                        "visual_brief": "Brief A",
                    },
                    {
                        "label": "B",
                        "hook": "Hook tot cho da kho",
                        "caption": "Caption B",
                        "cta": "Nhan tin",
                        "tone_tags": ["practical"],
                        "visual_brief": "Brief B",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    items = [
        {
            "calendar_id": "cal-1",
            "brand_id": "brand",
            "date": "2026-06-24",
            "topic": "Routine cap am",
            "pillar": "education",
            "draft_caption_ref": str(caption_file),
        }
    ]

    summary = enrich_items_with_variant_scores(items, memory_db)

    assert summary == {"scored_items": 1, "skipped_items": 0}
    assert items[0]["recommended_variant"]["variant_id"] == "B"
    scores = {score["variant_id"]: score["score"] for score in items[0]["variant_scores"]}
    assert scores["B"] > scores["A"]
    assert list(scores) == ["A", "B"]


def test_approval_queue_formatter_shows_variant_scores():
    message = TelegramFormatterTool().format_approval_queue(
        {
            "summary": {"total_items": 1},
            "items": [
                {
                    "date": "2026-06-24",
                    "topic": "Routine cap am",
                    "calendar_id": "cal-1",
                    "status": "draft",
                    "approval_status": "pending",
                    "pillar": "education",
                    "draft_caption_ref": "caption.json",
                    "recommended_variant": {"variant_id": "B", "score": 84.5},
                    "variant_scores": [
                        {"variant_id": "A", "score": 62.0},
                        {"variant_id": "B", "score": 84.5},
                    ],
                }
            ],
        }
    )

    assert "recommended variant: B (score 84.5)" in message
    assert "variant scores: A: 62.0, B: 84.5" in message
