from __future__ import annotations


class _ResearchMixin:
    """Formatters for research briefs and hashtag packages."""

    def format_research_brief(self, payload: dict) -> str:
        if isinstance(payload.get("brief"), dict):
            payload = payload["brief"]
        evidence = payload.get("evidence") or []
        source_documents = payload.get("source_documents") or []
        quality_warnings = payload.get("quality_warnings") or []
        confidence = payload.get("confidence_score", payload.get("confidence", 0))
        lines = [
            "## Research Brief",
            f"confidence: {confidence}",
            f"sources: {len(source_documents)} | evidence: {len(evidence)} | warnings: {len(quality_warnings)}",
        ]
        if payload.get("recommended_objectives"):
            lines.append(f"objective focus: {payload['recommended_objectives'][0]}")
        if payload.get("recommended_pillars"):
            lines.append(f"pillar focus: {payload['recommended_pillars'][0]}")
        if payload.get("campaign_focus"):
            lines.append(f"campaign focus: {', '.join(payload['campaign_focus'][:3])}")
        if payload.get("top_performing_topics"):
            lines.append(f"top topic: {payload['top_performing_topics'][0]}")
        if source_documents:
            top_sources = ", ".join(
                f"{item.get('name') or item.get('title') or item.get('source_id', '-') } ({item.get('trust_score', 0)})"
                for item in source_documents[:3]
            )
            lines.append(f"top sources: {top_sources}")
        lines.append("")
        source_claims = [item for item in evidence if item.get("evidence_type") in {"source_claim", "external_source"}]
        if source_claims:
            lines.append("source-backed insights:")
            for item in source_claims[:3]:
                source = item.get("source") or item.get("source_id") or "-"
                confidence_hint = item.get("confidence", "-")
                lines.append(f"- {item.get('claim', '-')} ({source}, {confidence_hint})")
        if payload.get("frequent_questions"):
            lines.append("frequent questions:")
            lines.extend([f"- {item}" for item in payload["frequent_questions"][:3]])
        if payload.get("next_angles"):
            lines.append("next angles:")
            lines.extend([f"- {item}" for item in payload["next_angles"][:3]])
        if payload.get("recommendations"):
            lines.append("recommendations:")
            lines.extend([f"- {item}" for item in payload["recommendations"][:3]])
        if quality_warnings:
            lines.append("quality warnings:")
            lines.extend([f"- {item}" for item in quality_warnings[:3]])
        if payload.get("overused_topics"):
            lines.append("watchouts:")
            lines.extend([f"- overused topic: {item}" for item in payload["overused_topics"][:3]])
        return "\n".join(lines).strip()

    def format_hashtag_set(self, payload: dict) -> str:
        content_topic = payload.get("content_topic", "")
        pillar = payload.get("pillar", "")
        objective = payload.get("objective", "")
        suggestions = payload.get("suggestions", [])
        recommended = payload.get("recommended", [])

        lines = [
            "## Hashtag Package",
            f"topic: {content_topic}",
            f"pillar: {pillar} | objective: {objective}",
            "",
        ]

        # Group by tier
        tiers = {"high_volume": "High Volume", "medium_volume": "Medium Volume",
                 "low_volume": "Low Volume", "branded": "Branded"}
        for tier_key, tier_label in tiers.items():
            tier_tags = [s for s in suggestions if s.get("tier") == tier_key]
            if not tier_tags:
                continue
            lines.append(f"**{tier_label}:**")
            for s in tier_tags:
                tag = s.get("tag", "")
                score = s.get("relevance_score", 0)
                reason = s.get("reason", "")
                badge = " \u2705" if tag in recommended else ""
                lines.append(f"  #{tag} ({score:.0%}){badge} — {reason}")
            lines.append("")

        if recommended:
            lines.append("**Recommended:** " + " ".join(f"#{t}" for t in recommended))

        return "\n".join(lines).strip()
