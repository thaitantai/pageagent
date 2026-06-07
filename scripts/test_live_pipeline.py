#!/usr/bin/env python3
"""Test full research pipeline with real data: AccessTrade API + web search + RSS.

Usage:
    cd /home/tantai/.hermes/fanpage-agent
    ~/.hermes/hermes-agent/venv/bin/python3 scripts/test_live_pipeline.py

Requires:
    - ACCESSTRADE_API_KEY in .env (real API calls to accesstrade.vn)
    - Internet access for DuckDuckGo search + RSS scrape
"""

from __future__ import annotations

import json
import os
import tempfile
import textwrap
from pathlib import Path
from typing import Any


# ── Load .env before any imports that read environment ───────────────────


def _load_dotenv() -> None:
    """Load .env file from project root into os.environ if not already set.

    This is needed because the script is run directly, not through Hermes
    which auto-loads .env. Each provider config reads from os.environ.
    """
    dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key not in os.environ:  # Don't override explicit env vars
            os.environ[key] = value


_load_dotenv()

from fanpage_agent.affiliate import AffiliateRegistry, AffiliateSettings
from fanpage_agent.models import (
    ResearchBrief,
    SourceCandidate,
    SourceDocument,
)
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer
from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.services.competitor_page_discovery import (
    CompetitorPageDiscoveryService,
)
from fanpage_agent.services.offer_evaluator import OfferEvaluator
from fanpage_agent.services.research import ResearchService
from fanpage_agent.services.research_insights import (
    EvidenceExtractor,
    ResearchQualityGate,
)
from fanpage_agent.adapters.sheet_store import LocalSheetStore


# ── Display helpers ─────────────────────────────────────────────────────


def _h1(text: str) -> str:
    """Section header."""
    w = 70
    return f"\n{'=' * w}\n  {text}\n{'=' * w}"


def _h2(text: str) -> str:
    """Sub-section header."""
    w = 70
    return f"\n{'─' * w}\n  {text}\n{'─' * w}"


def _kv(k: str, v: Any) -> str:
    """Key-value line."""
    return f"  ▸ {k}: {v}"


def _ok(text: str) -> str:
    return f"  ✅ {text}"


def _warn(text: str) -> str:
    return f"  ⚠️  {text}"


def _info(text: str) -> str:
    return f"  ℹ️  {text}"


def _product_line(name: str, comm: str, network: str) -> str:
    return f"    🏷️  {name:<28} {comm:>10}  [{network}]"


def _angle_line(idx: int, text: str) -> str:
    return f"    {idx}. {text}"


def _score_line(score: float, topic: str, rationale: str = "") -> str:
    line = f"    {score:.3f} — {topic}"
    if rationale:
        line += f"\n          ↳ {rationale[:110]}"
    return line


# ── Setup synthetic input data ──────────────────────────────────────────


def create_data(tmpdir: Path) -> dict[str, Any]:
    """Create minimal CSV/JSON data files for the research pipeline.

    Returns a dict with paths to all created files.
    """
    # ── Post history (90 days, 10 posts) ─────────────────────────────
    history_csv = tmpdir / "post_history.csv"
    history_csv.write_text(
        textwrap.dedent("""\
            published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate
            2026-06-01,"Da thiếu nước nên làm gì?","Hook A","education","reach","https://fb.com/1",1200,0.05
            2026-06-02,"Da thiếu nước nên làm gì?","Hook B","education","reach","https://fb.com/2",900,0.04
            2026-06-03,"Khi nào cần soi da?","Hook C","trust","lead","https://fb.com/3",1500,0.07
            2026-06-04,"Routine phục hồi da","Hook D","education","lead","https://fb.com/4",1700,0.08
            2026-06-05,"Kem chống nắng vật lý vs hóa học","Hook E","education","reach","https://fb.com/5",2000,0.09
            2026-06-06,"Retinol cho người mới bắt đầu","Hook F","education","lead","https://fb.com/6",2500,0.11
            2026-06-07,"Cách chọn serum Vitamin C","Hook G","comparison","reach","https://fb.com/7",1800,0.06
            2026-06-08,"SPF 50+ có gây bí da không?","Hook H","myth_busting","reach","https://fb.com/8",2200,0.10
            2026-06-09,"Niacinamide cho da dầu mụn","Hook I","education","lead","https://fb.com/9",1900,0.07
            2026-06-10,"So sánh AHA vs BHA","Hook J","comparison","reach","https://fb.com/10",1600,0.05
        """),
        encoding="utf-8",
    )

    # ── Post metrics ─────────────────────────────────────────────────
    metrics_csv = tmpdir / "post_metrics.csv"
    metrics_csv.write_text(
        textwrap.dedent("""\
            published_at,topic,pillar,objective,reach,engagements,leads
            2026-06-01,"Da thiếu nước nên làm gì?","education","reach",1200,60,2
            2026-06-03,"Khi nào cần soi da?","trust","lead",1500,90,8
            2026-06-04,"Routine phục hồi da","education","lead",1700,130,11
            2026-06-05,"Kem chống nắng vật lý vs hóa học","education","reach",2000,180,4
            2026-06-06,"Retinol cho người mới bắt đầu","education","lead",2500,275,15
            2026-06-07,"Cách chọn serum Vitamin C","comparison","reach",1800,108,6
            2026-06-08,"SPF 50+ có gây bí da không?","myth_busting","reach",2200,220,5
            2026-06-09,"Niacinamide cho da dầu mụn","education","lead",1900,133,9
            2026-06-10,"So sánh AHA vs BHA","comparison","reach",1600,80,3
        """),
        encoding="utf-8",
    )

    # ── Comments ─────────────────────────────────────────────────────
    comments_csv = tmpdir / "comment_inbox.csv"
    comments_csv.write_text(
        textwrap.dedent("""\
            created_at,source,message
            2026-06-05,comment,"Da thiếu nước thì nên bắt đầu từ đâu?"
            2026-06-05,inbox,"Chi phí soi da là bao nhiêu?"
            2026-06-06,comment,"Da treatment bị khô thì xử lý sao?"
            2026-06-07,comment,"Kem chống nắng nào không gây bí da dầu?"
            2026-06-08,comment,"Retinol nồng độ nào cho người mới?"
            2026-06-09,comment,"Serum Vitamin C nào cho da dầu?"
            2026-06-10,comment,"Niacinamide dùng chung với retinol được không?"
        """),
        encoding="utf-8",
    )

    # ── Campaign notes ───────────────────────────────────────────────
    campaign_json = tmpdir / "campaign_notes.json"
    campaign_json.write_text(
        json.dumps(
            {
                "campaign_focus": ["Kem chống nắng", "Retinol"],
                "priority_objective": "lead",
                "notes": ["Đẩy sản phẩm chống nắng mùa hè + retinol cho người mới"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "history": history_csv,
        "metrics": metrics_csv,
        "comments": comments_csv,
        "campaign": campaign_json,
    }


# ── Source documents (simulated RSS sources) ─────────────────────────────


def create_source_docs() -> list[SourceDocument]:
    """Return a few simulated source documents."""
    return [
        SourceDocument(
            source_id="healthline-spf",
            source_name="Healthline VN",
            source_type="rss",
            url="https://example.com/spf50-oily",
            title="Kem chống nắng SPF 50+ cho da dầu mụn",
            content=(
                "Chọn kem chống nắng cho da dầu mụn cần chú ý SPF, "
                "kết cấu không nhờn rít, và khả năng kiểm soát dầu. "
                "SPF 50+ PA+++ là tiêu chuẩn vàng cho da dầu mụn."
            ),
            trust_score=0.85,
            freshness_score=0.9,
        ),
        SourceDocument(
            source_id="dep365-vitc",
            source_name="Đẹp365",
            source_type="website",
            url="https://example.com/vitamin-c-review",
            title="Top 5 serum Vitamin C đáng mua nhất 2026",
            content=(
                "Serum Vitamin C giúp làm sáng da, mờ thâm nám, "
                "và bảo vệ da khỏi tác hại của môi trường. "
                "Nồng độ từ 10-20% là phù hợp cho người mới."
            ),
            trust_score=0.7,
            freshness_score=0.8,
        ),
        SourceDocument(
            source_id="watsons-retinol",
            source_name="Watsons Blog",
            source_type="website",
            url="https://example.com/retinol-beginner",
            title="Retinol cho người mới: hướng dẫn từng bước",
            content=(
                "Bắt đầu với Retinol nồng độ thấp 0.25-0.5% là lý tưởng "
                "cho người mới. Sử dụng 2-3 lần/tuần, tăng dần khi da quen."
            ),
            trust_score=0.75,
            freshness_score=0.85,
        ),
    ]


# ── Source candidates ────────────────────────────────────────────────────


def create_source_candidates() -> list[SourceCandidate]:
    """Return simulated source candidates for the pipeline."""
    return [
        SourceCandidate(
            source_id="blogskincare",
            title="Blog Skincare Vietnam — chuyên review mỹ phẩm",
            url="https://blogskincare.example.com",
            snippet="Blog review mỹ phẩm uy tín, cập nhật thường xuyên",
            discovery_query="review mỹ phẩm skincare",
        ),
        SourceCandidate(
            source_id="hellobacsi",
            title="HelloBacsi — chuyên mục chăm sóc da",
            url="https://hellobacsi.example.com",
            snippet="Thông tin sức khỏe làn da từ chuyên gia y tế",
            discovery_query="chăm sóc da khoa học",
        ),
    ]


# ── Page context (minimal — no affiliate_offers, uses real AccessTrade) ──


def create_page_context() -> dict[str, Any]:
    """Return minimal page context — no hardcoded offerings.

    The pipeline relies on AffiliateRegistry (real AccessTrade API)
    for product discovery instead of manually configured offers.
    """
    return {
        "page_name": "Skincare cho GenZ",
        "industry_focus": "chăm sóc da",
        "affiliate_offers": [],  # empty — pipeline uses AccessTrade API instead
    }


# ── Main demo runner ─────────────────────────────────────────────────────


def run_test() -> None:
    """Run the full research pipeline with real API calls."""
    print()
    print("=" * 70)
    print("  🧪  RESEARCH PIPELINE — LIVE TEST (AccessTrade API + Web Search)")
    print("  Dữ liệu: synthetic local (post history, metrics, comments)")
    print("  API thật: AccessTrade.vn + DuckDuckGo web search + RSS scrape")
    print("=" * 70)

    # ── Setup ────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        data = create_data(tmpdir)

        store = LocalSheetStore(
            calendar_csv=tmpdir / "calendar.csv",
            history_csv=data["history"],
            metrics_csv=data["metrics"],
        )

        source_docs = create_source_docs()
        source_candidates = create_source_candidates()
        page_context = create_page_context()

        # ── Component 1: AffiliateRegistry (real AccessTrade API) ──
        print(_h1("📦 Component 1 — AffiliateRegistry (AccessTrade API thật)"))
        affiliate_settings = AffiliateSettings.load()
        registry = AffiliateRegistry(affiliate_settings)

        if registry.is_enabled():
            print(_ok("AccessTrade API configured"))
            # Test search
            print(_h2("Search: keyword 'retinol'"))
            retinol_products = registry.search_all(
                "retinol", max_results_per_provider=5
            )
            if retinol_products:
                print(f"  Tìm thấy {len(retinol_products)} sản phẩm:")
                for p in retinol_products:
                    print(_product_line(p.product_name, p.commission_note, p.network))
            else:
                print(_info("Không tìm thấy sản phẩm cho keyword 'retinol'"))

            # Full skincare discovery
            print(_h2("Skincare discovery (all keywords)"))
            all_products = registry.search_skincare_products(
                max_results_per_provider=3
            )
            if all_products:
                print(f"  Tổng cộng {len(all_products)} sản phẩm skincare "
                      f"(sau dedup + filter min commission):")
                for p in all_products[:8]:
                    print(_product_line(p.product_name, p.commission_note, p.network))
                if len(all_products) > 8:
                    print(f"    ... và {len(all_products) - 8} sản phẩm khác")
            else:
                print(_info("Không tìm thấy sản phẩm skincare từ AccessTrade"))
        else:
            print(_warn("AccessTrade chưa được cấu hình (thiếu API key trong .env)"))

        # ── Component 2: TrendScraper (real DuckDuckGo + RSS) ─────
        print(_h1("🌐 Component 2 — TrendScraper (web search + RSS thật)"))
        scraper = TrendScraper()
        print(_kv("Web search", "DuckDuckGo (8 fallback queries)"))
        print(_kv("RSS sources", "VnExpress, 24h, Afamily"))

        trends = scraper.search_trends(max_articles=10)
        rss_trends = scraper.fetch_all()

        print(f"\n  Web search: {len(trends)} items")
        for t in trends[:5]:
            print(f"    📄 {t.source}: {t.title[:65]}...")
        if len(trends) > 5:
            print(f"    ... và {len(trends) - 5} items khác")

        print(f"\n  RSS scrape: {len(rss_trends)} items")
        for t in rss_trends[:5]:
            print(f"    📄 {t.source}: {t.title[:65]}...")
        if len(rss_trends) > 5:
            print(f"    ... và {len(rss_trends) - 5} items khác")

        all_trends = trends + rss_trends

        # ── Component 3: TrendAnalyzer ───────────────────────────
        print(_h1("📊 Component 3 — TrendAnalyzer"))
        analyzer = TrendAnalyzer(all_trends)
        report = analyzer.generate_report()
        top_keywords = [kw["word"] for kw in report["top_keywords"][:15]]
        clusters = report["clusters"]

        print(_kv("Top keywords", ", ".join(top_keywords[:10])))
        print(f"  Clusters ({len(clusters)}):")
        for name, items in list(clusters.items())[:5]:
            print(f"    📌 {name} ({len(items)} items)")

        # ── Component 4: ResearchService → build_brief ──────────
        print(_h1("🧠 Component 4 — ResearchService.build_brief() (FULL PIPELINE)"))
        print(_info("Gồm: post history → web search → OfferDiscovery → "
                    "AffiliateRegistry → QualityGate → OfferEvaluator → scoring"))
        print()

        service = ResearchService(
            trend_scraper=scraper,
            trend_analyzer=analyzer,
            affiliate_registry=registry,
        )

        brief = service.build_brief(
            store=store,
            comment_csv=data["comments"],
            campaign_notes_file=data["campaign"],
            source_documents=source_docs,
            source_candidates=source_candidates,
            page_context=page_context,
            fetch_external_trends=True,
            discover_product_topics=True,
            discover_offers=True,
            scan_competitor_pages=False,       # Không có FB pages config thật
            competitor_page_ids=None,
            fetch_affiliate_offers=True,        # AccessTrade API thật
            max_product_topics=10,
        )

        # ── Display results ──────────────────────────────────────
        _print_brief(brief)


def _print_brief(brief: ResearchBrief) -> None:
    """Display ResearchBrief contents to stdout."""
    # ── Campaign focus ───────────────────────────────────────────
    print(_h2("🎯 CAMPAIGN FOCUS"))
    if brief.campaign_focus:
        print(f"    {', '.join(brief.campaign_focus)}")
    print(_kv("Priority objective", brief.recommended_objectives[0] if brief.recommended_objectives else "N/A"))

    # ── Overused topics ──────────────────────────────────────────
    if brief.overused_topics:
        print(_h2("⚠️  OVERUSED TOPICS (cần giảm)"))
        for t in brief.overused_topics:
            print(f"    🔄 {t}")

    # ── Top performing topics ────────────────────────────────────
    if brief.top_performing_topics:
        print(_h2("⭐ TOP PERFORMING TOPICS"))
        for t in brief.top_performing_topics:
            print(f"    ★ {t}")

    # ── Frequently asked questions ──────────────────────────────
    if brief.frequent_questions:
        print(_h2("💬 FREQUENT QUESTIONS (từ comment/inbox)"))
        for q in brief.frequent_questions:
            print(f"    ❓ {q[:70]}")

    # ── Next angles ──────────────────────────────────────────────
    print(_h2("✍️  TOP 5 GÓC NHÌN ĐỀ XUẤT (next_angles)"))
    if brief.next_angles:
        for i, angle in enumerate(brief.next_angles, 1):
            print(_angle_line(i, angle))
    else:
        print(_warn("Không có đề xuất góc nhìn nào"))

    # ── Topic scores ─────────────────────────────────────────────
    print(_h2("📈 TOPIC SCORES (xếp hạng)"))
    if brief.topic_scores:
        for ts in brief.topic_scores[:8]:
            print(_score_line(ts.total_score, ts.topic, ts.rationale))
        if len(brief.topic_scores) > 8:
            print(f"    ... và {len(brief.topic_scores) - 8} topic khác")
    else:
        print(_info("Không có topic scores"))

    # ── Recommendations ─────────────────────────────────────────
    print(_h2("💡 RECOMMENDATIONS"))
    for r in brief.recommendations:
        print(f"    • {r[:100]}")

    # ── Affiliate products from API ──────────────────────────────
    print(_h2("📦 AFFILIATE OFFERS (từ research pipeline)"))
    if brief.next_angles:
        affiliate_angles = [
            a for a in brief.next_angles
            if any(kw in a.lower() for kw in [
                "accesstrade", "shopee", "commission", "affiliate",
                "network", "buying_guide", "review từ",
                "chọn",  # "Cách chọn X"
            ])
        ]
        if affiliate_angles:
            for a in affiliate_angles:
                print(f"    📎 {a}")
        else:
            # Count terms that look like product names
            product_mentions = [
                a for a in brief.next_angles
                if any(kw in a.lower() for kw in [
                    "retinol", "vitamin", "niacinamide", "spf",
                    "chống nắng", "serum", "aha", "bha",
                ])
            ]
            if product_mentions:
                for a in product_mentions:
                    print(f"    📎 {a}")
            else:
                print(_info("Các góc nhìn trên được sinh từ pipeline content discovery"))
    else:
        print(_info("Không có góc nhìn nào để hiển thị"))

    # ── External trends ─────────────────────────────────────────
    print(_h2("🌍 EXTERNAL TRENDS"))
    if brief.external_trends:
        for t in brief.external_trends[:5]:
            print(f"    📄 {t.source}: {t.title[:70]}")
        if len(brief.external_trends) > 5:
            print(f"    ... và {len(brief.external_trends) - 5} items khác")
    else:
        print(_info("Không có external trends"))

    # ── Quality warnings ────────────────────────────────────────
    print(_h2("⚠️  QUALITY WARNINGS"))
    if brief.quality_warnings:
        for w in brief.quality_warnings:
            print(f"    ⚠️  {w}")
    else:
        print(_ok("Không có cảnh báo chất lượng"))

    # ── Confidence score ────────────────────────────────────────
    print(f"\n  📊 CONFIDENCE SCORE: {brief.confidence_score:.3f} / 1.0")

    print("\n" + "=" * 70)
    print("  ✅ LIVE TEST COMPLETE")
    print("=" * 70)


# ── Entry point ─────────────────────────────────────────────────────────


def main() -> None:
    run_test()


if __name__ == "__main__":
    main()
