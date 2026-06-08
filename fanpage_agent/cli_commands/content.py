from __future__ import annotations

import argparse
import json
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


def _content_package_from_caption_item(
    item: dict,
    variants_json_path: str | Path | None = None,
) -> ContentPackage:
    """Build a ContentPackage from a calendar item (which may be a CaptionItem or dict).

    Expects the item to have fields matching ContentPackage schema:
      topic, pillar, objective, brand_id, format, variants
    """
    package_data = {
        "topic": item.get("topic", ""),
        "pillar": item.get("pillar", ""),
        "objective": item.get("objective", ""),
        "brand_id": item.get("brand_id", "skincare_genz"),
        "format": item.get("format", "post_short"),
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

    variants = []
    for i, v in enumerate(variants_data):
        if isinstance(v, ContentVariant):
            variants.append(v)
            continue
        variant_data = {
            "variant_id": v.get("variant_id", f"v{i}"),
            "caption_text": v.get("caption_text", v.get("text", v.get("caption", ""))),
            "hashtags": v.get("hashtags", []),
            "visual_brief": v.get("visual_brief", ""),
            "relevance_score": v.get("relevance_score", None),
            "variant_scores": v.get("variant_scores", None),
            "style": v.get("style", "casual"),
            "tone": v.get("tone", "friendly"),
        }
        variants.append(ContentVariant(**variant_data))
    package_data["variants"] = variants
    return ContentPackage(**package_data)


def enrich_items_with_variant_scores(
    items: list[dict],
    memory_db: str | Path | None = None,
) -> list[dict]:
    """Calculate variant quality scores and attach to each item's variants."""
    if not items:
        return items

    from fanpage_agent.memory import PerformanceMemory
    from fanpage_agent.tools.research.variant_scorer import VariantScorer

    memory = PerformanceMemory(Path(memory_db) if memory_db else None)
    scorer = VariantScorer(memory)

    enriched = []
    for item in items:
        package = _content_package_from_caption_item(item)
        scored_variants = scorer.score_variants(package)
        score_map = {
            sv.variant_id: {
                "variant_id": sv.variant_id,
                "score": sv.score,
                "grade": sv.grade,
                "explanation": sv.explanation,
            }
            for sv in scored_variants
        }
        item = dict(item)
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
        enriched.append(item)

    return enriched


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
