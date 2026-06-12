from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from fanpage_agent.config import Settings
from fanpage_agent.core.types import ContentPackage, ContentVariant
from fanpage_agent.loaders.brand_loader import load_brand_profile
from fanpage_agent.adapters.llm import build_llm_client
from fanpage_agent.tools.content.writer import WriterTool
from fanpage_agent.tools.content.hashtag import HashtagTool
from fanpage_agent.tools.publishing.telegram_formatter import TelegramFormatterTool
from fanpage_agent.utils import dump_json

from .parser import ROOT_DIR

logger = logging.getLogger(__name__)


def _content_package_from_caption_item(
    item: dict,
    variants_json_path: str | Path | None = None,
) -> ContentPackage:
    """Build a ContentPackage from a calendar item (which may be a CaptionItem or dict).

    Expects the item to have fields matching ContentPackage schema:
      topic, pillar, objective, brand_id, format, variants
    """
    package_data = {
        "package_id": item.get("calendar_id", item.get("package_id", "")),
        "brand_id": item.get("brand_id", "skincare_genz"),
        "topic": item.get("topic", ""),
        "scheduled_date": item.get("date", item.get("scheduled_date", "")),
        "page_context": {"pillar": item.get("pillar", ""), "objective": item.get("objective", ""), "format": item.get("format", "post_short")},
    }
    # Extract variants from caption_ideas if present (CaptionItem)
    variants_data = item.get("variants", [])
    if not variants_data and "caption_ideas" in item:
        variants_data = item["caption_ideas"]

    # Try loading from variants_json_path first (final approved variants)
    if variants_json_path and os.path.isfile(variants_json_path):
        with open(variants_json_path, encoding="utf-8") as f:
            loaded_variants = json.load(f)
            if isinstance(loaded_variants, list):
                variants_data = loaded_variants
            elif isinstance(loaded_variants, dict):
                file_variants = loaded_variants.get("variants") or loaded_variants.get("caption_ideas") or []
                if file_variants:
                    variants_data = file_variants

    variants = []
    for i, v in enumerate(variants_data):
        if isinstance(v, ContentVariant):
            variants.append(v)
            continue
        variant_data = {
            "variant_id": v.get("variant_id") or v.get("label", f"v{i}"),
            "topic": v.get("topic") or item.get("topic", ""),
            "pillar": v.get("pillar") or item.get("pillar", ""),
            "caption": v.get("caption_text") or v.get("caption", ""),
            "hook": v.get("hook", ""),
            "cta": v.get("cta", ""),
            "format": v.get("format") or item.get("format", "post_short"),
            "tone_tags": v.get("tone_tags", []),
            "visual_brief": v.get("visual_brief", ""),
        }
        variants.append(ContentVariant(**variant_data))
    package_data["variants"] = variants
    return ContentPackage(**package_data)


def _build_predictor(predictor_store=None):
    """Best-effort engagement predictor — approval delivery never blocks on it."""
    import sqlite3

    try:
        from fanpage_agent.adapters.sqlite_store import UnifiedStore
        from fanpage_agent.tools.research.learning_predictor import PerformancePredictor

        predictor = PerformancePredictor(
            predictor_store if predictor_store is not None else UnifiedStore()
        )
        return predictor, predictor.get_quality().get("status", "untrained")
    except (ImportError, OSError, sqlite3.Error) as exc:
        logger.warning("Engagement predictor unavailable for scoring: %s", exc)
        return None, "untrained"


def enrich_items_with_variant_scores(
    items: list[dict],
    memory_db: str | Path | None = None,
    predictor_store=None,
) -> dict:
    """Calculate variant quality scores + engagement prediction per item.

    Mutates items in-place (``variant_scores``, ``recommended_variant``,
    ``quality``) and returns a summary dict. The ``quality`` block carries
    the winning variant score, the PerformancePredictor estimate, and the
    predictor status — see docs/plans/2026-06-13-expansion-plan.md §A.
    """
    if not items:
        return {"scored_items": 0, "skipped_items": 0, "predictor_status": "untrained"}

    from fanpage_agent.memory import PerformanceMemory
    from fanpage_agent.tools.research.learning_predictor import quality_block
    from fanpage_agent.tools.research.variant_scorer import VariantScorer

    memory = PerformanceMemory(Path(memory_db) if memory_db else None)
    scorer = VariantScorer(memory)
    predictor, predictor_status = _build_predictor(predictor_store)

    scored = 0
    for item in items:
        caption_ref = item.get("draft_caption_ref") or item.get("caption_file")
        package = _content_package_from_caption_item(item, variants_json_path=caption_ref)
        if not package.variants:
            continue
        scored_variants = scorer.score_package(package)
        score_map = {
            sv.variant_id: {
                "variant_id": sv.variant_id,
                "score": sv.score,
                "matched_patterns": len(sv.matched_patterns),
            }
            for sv in scored_variants
        }
        item["variant_scores"] = list(score_map.values())
        new_variants = []
        for v in (item.get("variants") or item.get("caption_ideas") or []):
            v = dict(v) if isinstance(v, dict) else {"text": str(v)}
            vid = v.get("variant_id", v.get("id", ""))
            if vid in score_map:
                v["variant_scores"] = score_map[vid]
            new_variants.append(v)
        if "variants" in item:
            item["variants"] = new_variants
        elif "caption_ideas" in item:
            item["caption_ideas"] = new_variants
        winning_score = None
        if package.winning_variant:
            winning_score = next(
                (s.score for s in scored_variants if s.variant_id == package.winning_variant.variant_id),
                None,
            )
            item["recommended_variant"] = {
                "variant_id": package.winning_variant.variant_id,
                "score": winning_score,
            }
        item["quality"] = quality_block(winning_score, predictor=predictor)
        scored += 1

    return {
        "scored_items": scored,
        "skipped_items": len(items) - scored,
        "predictor_status": predictor_status,
    }


def cmd_write_caption(args: argparse.Namespace) -> int:
    """Write a multi-variant caption and save caption package to JSON."""
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    writer = WriterTool(llm_client=build_llm_client(settings))
    package = writer.write_caption(profile=profile, topic=args.topic, pillar=args.pillar, objective=args.objective, fmt=args.format)
    payload = package.model_dump(mode="json")
    if args.save:
        dump_json(settings.artifacts_dir / "captions" / f"caption-{args.topic[:30].replace(' ', '_')}.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_generate_hashtags(args: argparse.Namespace) -> int:
    settings = Settings.from_env(root_dir=ROOT_DIR)
    profile = load_brand_profile(args.brand_file)
    llm_client = build_llm_client(settings) if settings.llm_provider != "mock-local" or not args.no_llm else None
    service = HashtagTool(llm_client=llm_client, settings=settings)

    result = service.generate(
        topic=args.topic,
        pillar=args.pillar,
        objective=args.objective,
        angle=args.angle,
        brand_id=profile.brand_id,
        use_llm=not args.no_llm,
    )

    # Convert to serializable dict
    output = {
        "content_topic": result.content_topic,
        "pillar": result.pillar,
        "objective": result.objective,
        "suggestions": [
            {"tag": s.tag, "tier": s.tier, "relevance_score": s.relevance_score, "reason": s.reason}
            for s in result.suggestions
        ],
        "recommended": result.recommended,
    }

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        formatter = TelegramFormatterTool()
        print(formatter.format_hashtag_set(output))

    return 0
