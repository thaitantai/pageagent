from __future__ import annotations

from fanpage_agent.models import BrandProfile, CaptionPackage, PostHistoryEntry, VerificationResult, WeeklyPlan


class VerifierService:
    def verify_plan(
        self,
        profile: BrandProfile,
        plan: WeeklyPlan,
        history: list[PostHistoryEntry] | None = None,
    ) -> VerificationResult:
        issues: list[str] = []
        history = history or []
        recent_topics = {self._normalize(item.topic) for item in history}
        recent_hooks = {self._normalize(item.hook) for item in history}
        for item in plan.days:
            self._check_banned_phrases(profile, item.topic, issues)
            self._check_banned_phrases(profile, item.hook, issues)
            if not item.cta:
                issues.append(f"Missing CTA for {item.date}")
            if self._normalize(item.topic) in recent_topics:
                issues.append(f"Duplicate topic with recent history: {item.topic}")
            if self._normalize(item.hook) in recent_hooks:
                issues.append(f"Duplicate hook with recent history: {item.hook}")
        return VerificationResult(passed=not issues, issues=issues)

    def verify_caption_package(self, profile: BrandProfile, package: CaptionPackage) -> VerificationResult:
        issues: list[str] = []
        for variant in package.variants:
            self._check_banned_phrases(profile, variant.hook, issues)
            self._check_banned_phrases(profile, variant.caption, issues)
            if not variant.visual_brief:
                issues.append(f"Variant {variant.label} missing visual brief")
        return VerificationResult(passed=not issues, issues=issues)

    @staticmethod
    def _check_banned_phrases(profile: BrandProfile, text: str, issues: list[str]) -> None:
        lower = text.lower()
        for phrase in profile.banned_phrases:
            if phrase.lower() in lower:
                issues.append(f"Contains banned phrase: {phrase}")

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().split())
