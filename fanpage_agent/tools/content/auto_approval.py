from __future__ import annotations

from dataclasses import dataclass, field

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.models import BrandProfile
from fanpage_agent.tools.content.verifier import VerifierTool


@dataclass
class AutoApprovalConfig:
    """Rules that control what qualifies for auto-approval."""

    skip_banned_phrases: bool = True
    skip_duplicate_topics: bool = True
    require_verification_pass: bool = True


@dataclass
class AutoApprovalResult:
    """Summary of what happened during a process-pending run."""

    auto_approved: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)

    @property
    def auto_approved_count(self) -> int:
        return len(self.auto_approved)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    def to_dict(self) -> dict[str, object]:
        return {
            "auto_approved_count": self.auto_approved_count,
            "skipped_count": self.skipped_count,
            "auto_approved": self.auto_approved,
            "skipped": self.skipped,
        }


class AutoApprovalEngine:
    """Evaluates pending calendar items against rules and auto-approves eligible ones."""

    def __init__(
        self,
        brand_profile: BrandProfile,
        store: LocalSheetStore,
        verifier: VerifierTool,
        config: AutoApprovalConfig | None = None,
    ) -> None:
        self.profile = brand_profile
        self.store = store
        self.verifier = verifier
        self.config = config or AutoApprovalConfig()

    def process_pending(self) -> AutoApprovalResult:
        """Scan all calendar rows and auto-approve eligible pending items."""
        rows = self.store._read_calendar_rows()
        history = self.store.read_post_history() if self.store.history_csv else []
        result = AutoApprovalResult()

        for row in rows:
            calendar_id = row.get("calendar_id", "")
            approval_status = row.get("approval_status", "pending")
            status = row.get("status", "planned")

            # Skip already-finalised items
            if approval_status in ("approved", "auto_approved") or status == "published":
                reason_code = "already_published" if status == "published" else "already_finalized"
                result.skipped.append({
                    "calendar_id": calendar_id,
                    "reason": f"Already {approval_status if approval_status != 'pending' else 'published'}",
                    "reason_code": reason_code,
                    "status": status,
                    "approval_status": approval_status,
                })
                continue

            # Must have a caption
            if not row.get("draft_caption_ref", "").strip():
                result.skipped.append({
                    "calendar_id": calendar_id,
                    "reason": "No draft caption ref",
                    "reason_code": "missing_draft_caption_ref",
                    "status": status,
                    "approval_status": approval_status,
                    "next_step": "Generate or attach a draft caption before process-pending.",
                })
                continue

            # Check banned phrases
            if self.config.skip_banned_phrases:
                banned_issues: list[str] = []
                for field_name in ("hook", "topic", "cta"):
                    val = row.get(field_name, "")
                    for phrase in self.profile.banned_phrases:
                        if phrase.lower() in val.lower():
                            banned_issues.append(f"Contains banned phrase: {phrase}")
                if banned_issues:
                    result.skipped.append({
                        "calendar_id": calendar_id,
                        "reason": "; ".join(banned_issues),
                        "reason_code": "banned_phrase_detected",
                        "status": status,
                        "approval_status": approval_status,
                    })
                    continue

            # Check duplicate topics against history
            if self.config.skip_duplicate_topics and history:
                normalized_topic = VerifierTool._normalize(row.get("topic", ""))
                recent_topics = {VerifierTool._normalize(h.topic) for h in history}
                if normalized_topic in recent_topics:
                    result.skipped.append({
                        "calendar_id": calendar_id,
                        "reason": f"Duplicate topic with recent history: {row.get('topic', '')}",
                        "reason_code": "duplicate_topic",
                        "status": status,
                        "approval_status": approval_status,
                    })
                    continue

            # Verification check
            if self.config.require_verification_pass:
                # Build a minimal plan/caption context for the verifier
                from fanpage_agent.models import PlanDay, WeeklyPlan

                day = PlanDay(
                    date=row.get("date", ""),
                    pillar=row.get("pillar", ""),
                    objective=row.get("objective", ""),
                    topic=row.get("topic", ""),
                    angle=row.get("angle", ""),
                    format=row.get("format", ""),
                    hook=row.get("hook", ""),
                    cta=row.get("cta", ""),
                    visual_brief=row.get("visual_brief", ""),
                )
                plan = WeeklyPlan(plan_title="auto-check", days=[day])
                v_result = self.verifier.verify_plan(self.profile, plan, history)

                if not v_result.passed:
                    result.skipped.append({
                        "calendar_id": calendar_id,
                        "reason": "; ".join(v_result.issues),
                        "reason_code": "verification_failed",
                        "status": status,
                        "approval_status": approval_status,
                    })
                    continue

            # All checks passed — auto-approve
            self.store._approve_calendar_item(
                calendar_id=calendar_id,
                approved_by="auto_approval_engine",
                final_caption_ref=row.get("draft_caption_ref", ""),
                approved_at="",
                approval_status="auto_approved",
            )
            result.auto_approved.append({
                "calendar_id": calendar_id,
                "topic": row.get("topic", ""),
            })

        return result
