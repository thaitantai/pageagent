from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date as _date, timedelta
from pathlib import Path

from fanpage_agent.adapters.sheet_store import LocalSheetStore as Store
from fanpage_agent.models import BrandProfile, PlanDay, WeeklyPlan
from fanpage_agent.services.auto_approval import AutoApprovalEngine, AutoApprovalConfig
from fanpage_agent.services.planner import PlannerService
from fanpage_agent.services.verifier import VerifierService
from fanpage_agent.services.writer import WriterService


@dataclass
class FillResult:
    """Report of what the CalendarGapService filled."""

    filled: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def filled_count(self) -> int:
        return len(self.filled)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def to_dict(self) -> dict:
        return {
            "filled_count": self.filled_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "filled": self.filled,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class CalendarGapService:
    """Auto-detect missing content in the calendar and fill it.

    Pipeline per gap day:
      1. PlanDay — PlannerService (if no item exists)
      2. Write caption — WriterService
      3. Save caption artifact
      4. Attach draft_caption_ref to store
      5. Verify — VerifierService
      6. Auto-approve — AutoApprovalEngine
    """

    def __init__(
        self,
        planner: PlannerService | None = None,
        writer: WriterService | None = None,
        verifier: VerifierService | None = None,
        artifacts_dir: str | Path | None = None,
    ) -> None:
        self.planner = planner or PlannerService()
        self.writer = writer or WriterService()
        self.verifier = verifier or VerifierService()
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else Path("artifacts/captions")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def fill_gaps(
        self,
        profile: BrandProfile,
        store: Store,
        start_date: str | None = None,
        lookahead_days: int = 3,
        max_items: int = 3,
    ) -> FillResult:
        """Scan calendar for gaps and fill them.

        Args:
            profile: Brand profile for content generation.
            store: Data store (LocalSheetStore).
            start_date: ISO date to start scanning from (default: today).
            lookahead_days: How many days forward to scan.
            max_items: Max items to fill in a single pass (safety cap).

        Returns:
            FillResult with filled/skipped/errors counts.
        """
        result = FillResult()
        today = _date.today()
        start = _date.fromisoformat(start_date) if start_date else today
        end = start + timedelta(days=lookahead_days - 1)

        # 1. Get existing items in the window
        all_rows = store._read_calendar_rows()
        brand_rows = [r for r in all_rows if r.get("brand_id") == profile.brand_id]
        planned_by_date: dict[str, list[dict]] = {}
        for row in brand_rows:
            d = row.get("date", "")
            if d:
                planned_by_date.setdefault(d, []).append(row)

        # 2. Build history for verification
        history = store.read_post_history(limit=30) if store.history_csv else []

        # 3. Iterate over dates in range
        cursor = start
        while cursor <= end:
            iso = cursor.isoformat()
            day_rows = planned_by_date.get(iso, [])

            # Skip weekends and already-filled days
            if cursor.weekday() >= 5:  # Saturday=5, Sunday=6
                result.skipped.append({
                    "date": iso,
                    "reason": "Weekend",
                })
                cursor += timedelta(days=1)
                continue

            if self._is_day_filled(day_rows):
                result.skipped.append({
                    "date": iso,
                    "reason": f"Already has {len(day_rows)} item(s)",
                })
                cursor += timedelta(days=1)
                continue

            if result.filled_count >= max_items:
                break

            # 4. Fill this day
            self._fill_day(iso, profile, store, result, history)
            cursor += timedelta(days=1)

        return result

    def _is_day_filled(self, day_rows: list[dict]) -> bool:
        """A day is 'filled' if it has a row with an approved/published status."""
        for row in day_rows:
            s = row.get("status", "")
            if s in ("approved", "published", "auto_approved"):
                return True
        return False

    def _fill_day(
        self,
        iso_date: str,
        profile: BrandProfile,
        store: Store,
        result: FillResult,
        history: list,
    ) -> None:
        """Generate plan + caption + verify + approve for a single day."""
        try:
            # --- Step A: Generate PlanDay(s) for this date ---
            plan: WeeklyPlan = self.planner.plan_week(
                profile=profile,
                start_date=iso_date,
                days=1,
            )
            if not plan.days:
                result.errors.append({
                    "date": iso_date,
                    "reason": "Planner returned no days",
                })
                return

            day = plan.days[0]

            # --- Step B: Append plan to calendar store ---
            store.append_plan(profile.brand_id, plan)
            calendar_id = f"{plan.plan_title}-1"

            # --- Step C: Write caption ---
            caption_package = self.writer.write_caption(
                profile=profile,
                topic=day.topic,
                pillar=day.pillar,
                objective=day.objective,
                fmt=day.format,
            )

            # --- Step D: Save caption artifact ---
            safe_brand = profile.brand_id.replace(" ", "_").lower()
            caption_filename = f"daily-caption-auto-{safe_brand}-{iso_date}-1.json"
            caption_path = self.artifacts_dir / caption_filename
            caption_payload = caption_package.model_dump(mode="json")
            caption_path.write_text(json.dumps(caption_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            caption_ref = str(caption_path)

            # --- Step E: Attach draft caption ref ---
            store.attach_draft_caption_ref(
                calendar_id=calendar_id,
                caption_ref=caption_ref,
                updated_at=iso_date,
            )

            # --- Step F: Verify ---
            v_plan = self.verifier.verify_plan(profile, plan)
            if not v_plan.passed:
                result.errors.append({
                    "calendar_id": calendar_id,
                    "reason": f"Plan verification failed: {'; '.join(v_plan.issues)}",
                })
                return

            v_caption = self.verifier.verify_caption_package(profile, caption_package)
            if not v_caption.passed:
                result.errors.append({
                    "calendar_id": calendar_id,
                    "reason": f"Caption verification failed: {'; '.join(v_caption.issues)}",
                })
                return

            # --- Step G: Auto-approve ---
            engine = AutoApprovalEngine(
                brand_profile=profile,
                store=store,
                verifier=self.verifier,
                config=AutoApprovalConfig(),
            )
            ar = engine.process_pending()

            if any(a.get("calendar_id") == calendar_id for a in ar.auto_approved):
                result.filled.append({
                    "calendar_id": calendar_id,
                    "date": iso_date,
                    "topic": day.topic,
                    "pillar": day.pillar,
                    "caption_ref": caption_ref,
                })
            else:
                # If auto-approval skipped it, let's check why
                skipped_reason = "Unknown"
                for s in ar.skipped:
                    if s.get("calendar_id") == calendar_id:
                        skipped_reason = s.get("reason", "Unknown")
                        break
                result.errors.append({
                    "calendar_id": calendar_id,
                    "reason": f"Auto-approval skipped: {skipped_reason}",
                })

        except Exception as exc:
            result.errors.append({
                "date": iso_date,
                "reason": f"Exception: {exc}",
            })
