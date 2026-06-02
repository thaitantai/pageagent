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
        # Run tone checks and merge issues
        tone_result = self.verify_tone_consistency(profile, package)
        issues.extend(tone_result.issues)
        return VerificationResult(passed=not issues, issues=issues)

    def verify_tone_consistency(self, profile: BrandProfile, package: CaptionPackage) -> VerificationResult:
        """Kiểm tra từng variant có trung thành với giọng văn của brand không."""
        issues: list[str] = []
        traits = profile.tone_of_voice.brand_traits
        avoid = profile.tone_of_voice.things_to_avoid
        rules = profile.tone_of_voice.writing_rules

        for variant in package.variants:
            label = variant.label

            # 1. tone_tags alignment — mỗi tag nên khớp với brand_traits
            for tag in variant.tone_tags:
                if tag not in traits:
                    issues.append(
                        f"Variant {label}: tone_tag '{tag}' không nằm trong brand_traits {traits}"
                    )

            # 2. things_to_avoid — caption/hook không được chứa
            lower_caption = (variant.caption + " " + variant.hook).lower()
            for phrase in avoid:
                if phrase.lower() in lower_caption:
                    issues.append(
                        f"Variant {label}: caption chứa nội dung cần tránh: '{phrase}'"
                    )

            # 3. writing_rules compliance (heuristic — check pattern-based rules)
            for rule in rules:
                lower_rule = rule.lower()
                # Quy tắc phủ định: "Không X, tránh Y, đừng Z"
                if lower_rule.startswith(("không", "tránh", "đừng", "chớ")):
                    forbidden_word = rule.split(" ", 1)[1] if " " in rule else ""
                    if forbidden_word and forbidden_word.lower() in lower_caption:
                        issues.append(
                            f"Variant {label}: vi phạm writing_rule: '{rule}'"
                        )

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
