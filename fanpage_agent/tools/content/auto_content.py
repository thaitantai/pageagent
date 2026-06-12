from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from fanpage_agent.models import (
    BrandProfile,
    CaptionPackage,
    PostHistoryEntry,
    ResearchBrief,
    TrendItem,
)
from fanpage_agent.tools.publishing.planner import PlannerTool
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.tools.content.writer import WriterTool

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Data models cho output của orchestrator
# ──────────────────────────────────────────────

@dataclass
class GapItem:
    """Một gap: trend đang hot nhưng chưa được khai thác."""
    title: str
    source: str
    url: str
    snippet: str
    keywords: list[str] = field(default_factory=list)
    reason: str = ""
    relevance_score: float = 0.0


@dataclass
class DraftProposal:
    """Đề xuất content cho một gap."""
    gap_index: int
    gap_title: str
    pillar: str
    objective: str
    topic: str
    angle: str
    format: str
    caption_package: CaptionPackage | None = None
    draft_error: str = ""


@dataclass
class AutoContentReport:
    """Báo cáo tổng hợp từ một cycle autonomous."""
    run_date: str
    total_trend_items: int
    trend_keywords: list[str]
    trend_clusters: dict[str, list[str]]
    gaps: list[GapItem] = field(default_factory=list)
    proposals: list[DraftProposal] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    strategy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_date": self.run_date,
            "total_trend_items": self.total_trend_items,
            "trend_keywords": self.trend_keywords,
            "trend_clusters": self.trend_clusters,
            "gaps": [g.__dict__ for g in self.gaps],
            "proposals": [
                {
                    "gap_index": p.gap_index,
                    "gap_title": p.gap_title,
                    "pillar": p.pillar,
                    "objective": p.objective,
                    "topic": p.topic,
                    "angle": p.angle,
                    "format": p.format,
                    "caption": (
                        p.caption_package.model_dump(mode="json")
                        if p.caption_package
                        else None
                    ),
                    "draft_error": p.draft_error,
                }
                for p in self.proposals
            ],
            "errors": self.errors,
            "strategy": self.strategy,
        }

    def format_telegram(self, brand_name: str = "") -> str:
        """Telegram-friendly report."""
        lines: list[str] = []
        lines.append("🤖 *Auto Content Cycle*")
        lines.append(f"📅 {self.run_date}")
        if brand_name:
            lines.append(f"🏷 {brand_name}")
        lines.append("")

        # ── Trends ──
        lines.append(f"🔍 *Trends phát hiện: {self.total_trend_items} items*")
        if self.trend_keywords:
            kw = ", ".join(self.trend_keywords[:8])
            lines.append(f"Top keywords: `{kw}`")
        if self.trend_clusters:
            for cluster_name, titles in list(self.trend_clusters.items())[:3]:
                lines.append(f"  • *{cluster_name}*: {len(titles)} bài")
        lines.append("")

        # ── Gaps ──
        lines.append(f"🧩 *Gap phát hiện: {len(self.gaps)}*")
        for i, gap in enumerate(self.gaps[:5], 1):
            lines.append(f"  {i}. [{gap.relevance_score:.0%}] {gap.title}")
            lines.append(f"     → {gap.reason}")
        if len(self.gaps) > 5:
            lines.append(f"  ... +{len(self.gaps)-5} gaps khác")
        lines.append("")

        # ── Draft proposals ──
        if self.proposals:
            lines.append(f"✍️ *Content proposals: {len(self.proposals)}*")
            for p in self.proposals:
                lines.append(f"  • *{p.topic}*")
                lines.append(f"    Pillar: {p.pillar} | Format: {p.format}")
                if p.caption_package and p.caption_package.variants:
                    v = p.caption_package.variants[0]
                    preview = v.caption[:150].replace("\n", " ")
                    if len(v.caption) > 150:
                        preview += "..."
                    lines.append(f"    Draft: _{preview}_")
                elif p.draft_error:
                    lines.append(f"    ⚠️ Lỗi draft: {p.draft_error}")
        elif self.gaps:
            lines.append("⚠️ Có gap nhưng chưa draft — thêm `--draft` để auto sinh caption.")
        lines.append("")

        # ── Action ──
        if self.gaps:
            lines.append("💡 *Gợi ý hành động:*")
            lines.append(f"  1. Duyệt {len(self.gaps)} gaps — chọn topic phù hợp tone brand")
            lines.append("  2. Dùng `auto-content-cycle --draft` để auto sinh draft")
            lines.append("  3. Dùng `plan-week` để đưa vào lịch content")
        else:
            lines.append("✅ Không phát hiện gap — trends đang được khai thác tốt.")

        return "\n".join(lines)


# ──────────────────────────────────────────────
# Gap Analysis Engine
# ──────────────────────────────────────────────

# Stopwords tiếng Việt đơn giản cho keyword extraction
VIETNAMESE_STOPWORDS: set[str] = {
    "và", "của", "có", "cho", "với", "trong", "là", "các", "được",
    "một", "những", "không", "tại", "này", "khi", "đến", "từ", "đã",
    "sẽ", "đang", "ra", "về", "lên", "xuống", "vào", "nên", "phải",
    "bị", "đi", "ở", "thì", "hay", "hoặc", "cũng", "rất", "như", "sau",
    "trước", "nếu", "thì", "mà", "qua", "lại", "thêm", "nhiều", "ít",
    "mới", "cũ", "theo", "bằng", "để", "nữa", "vẫn", "chỉ", "tôi",
    "bạn", "mình", "chúng", "người", "việc", "năm", "ngày", "tuổi",
    "cách", "làm", "tập", "tìm", "hiểu",
}


def extract_keywords(text: str, max_words: int = 8) -> list[str]:
    """Trích keywords từ text: lowercase, loại stopwords, đếm tần suất."""
    text = text.lower()
    # Tách từ — simple whitespace split (tiếng Việt không dấu cách từ, nhưng đủ cho title/snippet)
    words = re.findall(r"[a-zA-Zàáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệđìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]+", text)
    # Lọc stopwords và từ quá ngắn
    filtered = [w for w in words if w not in VIETNAMESE_STOPWORDS and len(w) > 2]
    # Count frequency
    counts = Counter(filtered)
    return [word for word, _ in counts.most_common(max_words)]


def compute_keyword_overlap(keywords_a: list[str], keywords_b: list[str]) -> float:
    """Jaccard overlap giữa 2 keyword sets."""
    set_a = set(keywords_a)
    set_b = set(keywords_b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def analyze_gaps(
    external_trends: list[TrendItem],
    post_history: list[PostHistoryEntry],
    max_gaps: int = 10,
    min_title_length: int = 20,
) -> list[GapItem]:
    """Phân tích gap: trend nào chưa được khai thác.

    Steps:
      1. Dedup by URL (giữ URL đầu tiên)
      2. Lọc noise (title quá ngắn, address-like)
      3. Extract keywords từ title + snippet
      4. So sánh overlap với topics đã đăng (post_history)
      5. Nếu overlap thấp → là gap
      6. Tính relevance score
      7. Dedup title tương tự (fuzzy overlap >70% → merge)
    """
    if not external_trends:
        return []

    # ── 1. Dedup by URL ──
    seen_urls: set[str] = set()
    deduped: list[TrendItem] = []
    for t in external_trends:
        if t.url not in seen_urls:
            seen_urls.add(t.url)
            deduped.append(t)

    logger.debug("analyze_gaps: %d raw → %d after URL dedup", len(external_trends), len(deduped))

    # ── 2. Filter noise ──
    address_pattern = re.compile(r"(toà nhà|tòa nhà|star tower|số \d+|quận|huyện|phường|thành phố)", re.I)
    filtered: list[TrendItem] = []
    for t in deduped:
        title = (t.title or "").strip()
        # Bỏ title quá ngắn hoặc chứa địa chỉ
        if len(title) < min_title_length:
            continue
        if address_pattern.search(title):
            continue
        filtered.append(t)

    logger.debug("analyze_gaps: %d after noise filter", len(filtered))

    # ── 3. Build published topic keywords ──
    published_keywords: list[list[str]] = []
    for entry in post_history:
        kw = extract_keywords(entry.topic or "") + extract_keywords(entry.hook or "")
        if kw:
            published_keywords.append(kw)

    # ── 4-6. Gap scoring ──
    raw_gaps: list[GapItem] = []
    for trend in filtered:
        title_kw = extract_keywords(trend.title)
        snippet_kw = extract_keywords(trend.snippet or "")
        trend_kw = list(dict.fromkeys(title_kw + snippet_kw))[:10]  # dedup + limit

        if not trend_kw:
            continue

        # Compute max overlap against any published topic
        max_overlap = 0.0
        if published_keywords:
            max_overlap = max(compute_keyword_overlap(trend_kw, pk) for pk in published_keywords)

        # Gap threshold: < 30% overlap = chưa được khai thác
        if max_overlap < 0.30:
            # Reason
            if not published_keywords:
                reason = "Chưa có lịch sử xuất bản → content mới toanh"
            else:
                reason = f"Overlap {max_overlap:.0%} với nội dung đã đăng → chủ đề mới"

            # Relevance: dựa trên keyword diversity (nhiều keywords = chủ đề phong phú)
            relevance = (len(trend_kw) / 10.0) * (1.0 - max_overlap)

            raw_gaps.append(GapItem(
                title=trend.title,
                source=trend.source,
                url=trend.url,
                snippet=trend.snippet,
                keywords=trend_kw,
                reason=reason,
                relevance_score=round(relevance, 2),
            ))

    # ── 7. Dedup by title similarity ──
    # Sort by relevance (cao → thấp) trước khi dedup
    raw_gaps.sort(key=lambda g: g.relevance_score, reverse=True)

    final_gaps: list[GapItem] = []
    for gap in raw_gaps:
        is_duplicate = False
        for existing in final_gaps:
            overlap = compute_keyword_overlap(gap.keywords, existing.keywords)
            if overlap > 0.70:
                is_duplicate = True
                break
        if not is_duplicate:
            final_gaps.append(gap)
            if len(final_gaps) >= max_gaps:
                break

    logger.info("analyze_gaps: %d raw gaps → %d final gaps", len(raw_gaps), len(final_gaps))
    return final_gaps


# ──────────────────────────────────────────────
# AutoContentOrchestrator
# ──────────────────────────────────────────────

MAX_DRAFTS_PER_CYCLE = 3


class AutoContentOrchestrator:
    """Autonomous content agent loop.

    Pipeline per cycle:
      1. Research — web search + scrape → ResearchBrief với trends
      2. Strategist — research → strategy (pillar mix, ideas, gap fills)
      3. Gap analysis — so sánh trends vs published history → gaps
      4. Draft — sinh caption cho top gaps (nếu có brand profile)
      5. Report — tổng hợp + format Telegram
    """

    def __init__(
        self,
        research_service: ResearchTool | None = None,
        writer_service: WriterTool | None = None,
        planner_service: PlannerTool | None = None,
        strategist_service: Any = None,  # StrategistTool
    ) -> None:
        self.research = research_service or ResearchTool()
        self.writer = writer_service or WriterTool()
        self.planner = planner_service or PlannerTool()
        self._strategist = strategist_service

    def run_cycle(
        self,
        store: Any,
        brand_profile: BrandProfile | None = None,
        comment_csv: str | Path | None = None,
        campaign_file: str | Path | None = None,
        draft_content: bool = False,
        max_gaps: int = 10,
    ) -> AutoContentReport:
        """Run một autonomous cycle hoàn chỉnh.

        Args:
            store: Data store (LocalSheetStore) với read_post_history.
            brand_profile: Brand profile để draft content.
            comment_csv: Path tới comment CSV cho research.
            campaign_file: Path tới campaign notes JSON.
            draft_content: Có sinh draft caption cho gaps không.
            max_gaps: Số gap tối đa trong report.

        Returns:
            AutoContentReport với gaps + proposals.
        """
        run_date = date.today().isoformat()
        errors: list[str] = []

        # ── 1. Research: web search + scrape → research brief ──
        try:
            brief: ResearchBrief = self.research.build_brief(
                store=store,
                comment_csv=comment_csv,
                campaign_notes_file=campaign_file,
                fetch_external_trends=True,
            )
        except Exception as exc:
            errors.append(f"Research thất bại: {exc}")
            return AutoContentReport(
                run_date=run_date,
                total_trend_items=0,
                trend_keywords=[],
                trend_clusters={},
                errors=errors,
            )

        # ── 2. Strategist: research → strategy ──
        strategy_payload: dict[str, Any] = {}
        if self._strategist and brand_profile:
            try:
                strategy = self._strategist.build_strategy(
                    profile=brand_profile,
                    research_brief=brief,
                )
                strategy_payload = strategy.model_dump(mode="json")
            except Exception as exc:
                logger.warning("Strategist step failed (non-fatal): %s", exc)
                errors.append(f"Strategist: {exc}")

        # ── 3. Gap analysis ──
        post_history = store.read_post_history(limit=90)  # type: ignore[union-attr]

        gaps = analyze_gaps(
            external_trends=brief.external_trends,
            post_history=post_history,
            max_gaps=max_gaps,
        )

        # ── 3. Draft content cho top gaps ──
        proposals: list[DraftProposal] = []
        if draft_content and brand_profile and gaps:
            for idx, gap in enumerate(gaps[:MAX_DRAFTS_PER_CYCLE]):
                # Map gap → pillar + objective
                pillar, objective, fmt = self._map_gap_to_pillar(brand_profile, gap)

                # Use PlannerTool to generate a good angle
                try:
                    plan = self.planner.plan_week(
                        profile=brand_profile,
                        start_date=run_date,
                        days=1,
                    )
                except Exception as exc:
                    logger.warning(
                        "Planner angle failed for gap '%s', dùng gap title làm angle: %s",
                        gap.title, exc,
                    )
                    plan = None

                angle = plan.days[0].angle if plan and plan.days else gap.title

                # Write caption
                try:
                    caption = self.writer.write_caption(
                        profile=brand_profile,
                        topic=gap.title,
                        pillar=pillar,
                        objective=objective,
                        fmt=fmt,
                    )
                except Exception as exc:
                    proposals.append(DraftProposal(
                        gap_index=idx,
                        gap_title=gap.title,
                        pillar=pillar,
                        objective=objective,
                        topic=gap.title,
                        angle=angle,
                        format=fmt,
                        draft_error=str(exc),
                    ))
                    continue

                proposals.append(DraftProposal(
                    gap_index=idx,
                    gap_title=gap.title,
                    pillar=pillar,
                    objective=objective,
                    topic=gap.title,
                    angle=angle,
                    format=fmt,
                    caption_package=caption,
                ))

        # ── 4. Build report ──
        return AutoContentReport(
            run_date=run_date,
            total_trend_items=len(brief.external_trends),
            trend_keywords=brief.trend_keywords,
            trend_clusters=brief.trend_clusters,
            gaps=gaps,
            proposals=proposals,
            errors=errors,
            strategy=strategy_payload,
        )

    @staticmethod
    def _map_gap_to_pillar(
        profile: BrandProfile,
        gap: GapItem,
    ) -> tuple[str, str, str]:
        """Gán gap topic vào pillar phù hợp nhất dựa trên keyword match.

        Returns: (pillar_name, objective, format)
        """
        if not profile.content_pillars:
            return ("general", "reach", "post_short")

        gap_keywords = set(gap.keywords)

        best_pillar = profile.content_pillars[0]
        best_score = 0

        for pillar in profile.content_pillars:
            pillar_text = f"{pillar.pillar_name} {pillar.description} {' '.join(pillar.example_angles)}"
            pillar_kw = set(extract_keywords(pillar_text))
            score = len(gap_keywords & pillar_kw)
            if score > best_score:
                best_score = score
                best_pillar = pillar

        objective = best_pillar.goal or "reach"
        fmt = best_pillar.allowed_formats[0] if best_pillar.allowed_formats else "post_short"

        return (best_pillar.pillar_name, objective, fmt)
