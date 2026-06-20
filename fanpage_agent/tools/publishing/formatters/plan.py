from __future__ import annotations


class _PlanMixin:
    """Formatters for weekly planning and caption package generation."""

    def format_weekly_plan(self, payload: dict) -> str:
        lines = [
            "## Weekly Plan",
            f"plan: {payload.get('plan_title', '-')}",
            self._format_verification(payload.get("verification")),
            "",
        ]
        for index, day in enumerate(payload.get("days", []), start=1):
            lines.extend(
                [
                    f"{index}. {day.get('date', '-')} — {day.get('topic', '-')}",
                    f"   pillar: {day.get('pillar', '-')} | objective: {day.get('objective', '-')}",
                    f"   hook: {day.get('hook', '-')}",
                    f"   cta: {day.get('cta', '-')}",
                ]
            )
        strategy_notes = payload.get("strategy_notes", [])
        if strategy_notes:
            lines.append("")
            lines.append("strategy notes:")
            lines.extend([f"- {item}" for item in strategy_notes])
        return "\n".join(lines).strip()

    def format_caption_package(self, payload: dict) -> str:
        lines = [
            "## Caption Package",
            f"topic: {payload.get('topic', '-')}",
            self._format_verification(payload.get("verification")),
            "",
        ]
        for variant in payload.get("variants", []):
            lines.extend(
                [
                    f"Variant {variant.get('label', '-')}",
                    f"- hook: {variant.get('hook', '-')}",
                    f"- caption: {variant.get('caption', '-')}",
                    f"- cta: {variant.get('cta', '-')}",
                    f"- visual: {variant.get('visual_brief', '-')}",
                    "",
                ]
            )
        dos = payload.get("dos", [])
        if dos:
            lines.append("dos:")
            lines.extend([f"- {item}" for item in dos])
        donts = payload.get("donts", [])
        if donts:
            lines.append("don'ts:")
            lines.extend([f"- {item}" for item in donts])
        return "\n".join(lines).strip()
