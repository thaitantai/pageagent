import json
import math
from pathlib import Path

from fanpage_agent.adapters.sqlite_store import UnifiedStore
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

    predictor_store = UnifiedStore(db_path=memory_db.parent / "predictor.db")
    summary = enrich_items_with_variant_scores(
        items, memory_db, predictor_store=predictor_store
    )

    assert summary["scored_items"] == 1
    assert summary["skipped_items"] == 0
    assert summary["predictor_status"] == "untrained"
    assert items[0]["recommended_variant"]["variant_id"] == "B"
    scores = {score["variant_id"]: score["score"] for score in items[0]["variant_scores"]}
    assert scores["B"] > scores["A"]
    assert list(scores) == ["A", "B"]
    # Untrained predictor: quality block present, prediction null, no crash.
    quality = items[0]["quality"]
    assert quality["predictor_status"] == "untrained"
    assert quality["predicted_engagement"] is None
    assert quality["variant_score"] == scores["B"]


def _seeded_predictor_store(tmp_path: Path, slope: float, intercept: float) -> UnifiedStore:
    store = UnifiedStore(db_path=tmp_path / "predictor.db")
    store.save_predictor_state(
        {
            "params": {"slope": slope, "intercept": intercept},
            "metrics": {"mae": 1.0, "mape": 0.1, "r2": 0.9},
            "drift": False,
            "sample_count": 12,
            "trained_at": "2026-06-01T00:00:00+00:00",
        }
    )
    return store


def test_enrich_attaches_engagement_prediction_when_predictor_trained(tmp_path):
    memory_db = tmp_path / "memory.db"
    _record_pattern(memory_db, "education", "strong", engagements=120)

    caption_file = tmp_path / "caption.json"
    caption_file.write_text(
        json.dumps(
            {
                "topic": "Routine cap am",
                "variants": [
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
    slope, intercept = 2.0, 1.0
    predictor_store = _seeded_predictor_store(tmp_path, slope, intercept)

    summary = enrich_items_with_variant_scores(
        items, memory_db, predictor_store=predictor_store
    )

    assert summary["predictor_status"] == "trained"
    quality = items[0]["quality"]
    assert quality["predictor_status"] == "trained"
    winning_score = items[0]["recommended_variant"]["score"]
    normalized = min(1.0, winning_score / 100.0) if winning_score > 1.0 else winning_score
    expected = round(max(0, math.exp(slope * min(1.0, max(0.0, normalized)) + intercept) - 1), 1)
    assert quality["predicted_engagement"] == expected
    assert quality["prediction_confidence"] in {"high", "medium", "low"}


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


def test_approval_queue_formatter_shows_quality_block():
    formatter = TelegramFormatterTool()
    base_item = {
        "date": "2026-06-24",
        "topic": "Routine cap am",
        "calendar_id": "cal-1",
        "status": "draft",
        "approval_status": "pending",
        "pillar": "education",
        "draft_caption_ref": "caption.json",
        "recommended_variant": {"variant_id": "B", "score": 84.5},
    }
    trained = dict(base_item)
    trained["quality"] = {
        "variant_score": 84.5,
        "predicted_engagement": 142.0,
        "prediction_confidence": "medium",
        "predictor_status": "trained",
        "evidence_status": "ready",
    }
    untrained = dict(base_item)
    untrained["calendar_id"] = "cal-2"
    untrained["quality"] = {
        "variant_score": None,
        "predicted_engagement": None,
        "prediction_confidence": None,
        "predictor_status": "untrained",
    }
    untrained["needs_human_review"] = True

    message = formatter.format_approval_queue(
        {"summary": {"total_items": 2}, "items": [trained, untrained]}
    )

    assert "predicted engagement: ~142.0 (medium)" in message
    assert "evidence: ready" in message
    assert "predicted engagement: — (predictor untrained)" in message
    assert "⚠️ needs human review" in message
