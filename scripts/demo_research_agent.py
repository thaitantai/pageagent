#!/usr/bin/env python3
"""
Demo: Research Agent — full pipeline end-to-end với dữ liệu mô phỏng.

Chạy:
    python scripts/demo_research_agent.py

Không cần API key, không cần network — tất cả dữ liệu đều là mock.
"""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from fanpage_agent.adapters.sheet_store import LocalSheetStore
from fanpage_agent.models import (
    ResearchEvidence,
    SourceCandidate,
    SourceDocument,
    TrendItem,
)
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer
from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.tools.research.competitor_page_discovery import (
    CompetitorPageDiscoveryTool,
    FacebookPageClient,
)
from fanpage_agent.tools.research.offer_discovery import OfferDiscoveryTool
from fanpage_agent.tools.research.offer_evaluator import OfferEvaluator, SearchClient
from fanpage_agent.tools.research.product_topic_discovery import ProductTopicCandidate
from fanpage_agent.tools.research.research import ResearchTool
from fanpage_agent.tools.research.research_insights import EvidenceExtractor, ResearchQualityGate

# ────────────────────────────────────────
# Style helpers
# ────────────────────────────────────────
def _header(text: str) -> str:
    """Một line header dùng trong demo output."""
    w = 70
    return f"\n{'─' * w}\n  {text}\n{'─' * w}"

def _chip(label: str, value: Any, color: str | None = None) -> str:
    """Một chip thông tin: label: value."""
    return f"  ▸ {label}: {value}"

def _check(label: str, ok: bool) -> str:
    return f"  {'✅' if ok else '❌'} {label}"

def _sep() -> str:
    return "  " + "·" * 50

# ────────────────────────────────────────
# STEP 1 — Tạo dữ liệu giả
# ────────────────────────────────────────
def create_fake_data(tmpdir: Path) -> dict:
    """Tạo file CSV/JSON giả trong tmpdir, trả về dict các đường dẫn."""
    post_history_csv = tmpdir / "post_history.csv"
    post_history_csv.write_text(
        "published_at,topic,hook,pillar,objective,permalink,reach,engagement_rate\n"
        "2026-06-01,Da thiếu nước nên làm gì?,Hook A,education,reach,https://example.com/1,1200,0.05\n"
        "2026-06-02,Da thiếu nước nên làm gì?,Hook B,education,reach,https://example.com/2,900,0.04\n"
        "2026-06-03,Khi nào cần soi da?,Hook C,trust,lead,https://example.com/3,1500,0.07\n"
        "2026-06-04,Routine phục hồi da,Hook D,education,lead,https://example.com/4,1700,0.08\n"
        "2026-06-05,Kem chống nắng vật lý vs hóa học,Hook E,education,reach,https://example.com/5,2000,0.09\n"
        "2026-06-06,Retinol cho người mới bắt đầu,Hook F,education,lead,https://example.com/6,2500,0.11\n"
        "2026-06-07,Cách chọn serum Vitamin C,Hook G,comparison,reach,https://example.com/7,1800,0.06\n",
        encoding="utf-8",
    )

    metrics_csv = tmpdir / "post_metrics.csv"
    metrics_csv.write_text(
        "published_at,topic,pillar,objective,reach,engagements,leads\n"
        "2026-06-01,Da thiếu nước nên làm gì?,education,reach,1200,60,2\n"
        "2026-06-03,Khi nào cần soi da?,trust,lead,1500,90,8\n"
        "2026-06-04,Routine phục hồi da,education,lead,1700,130,11\n"
        "2026-06-05,Kem chống nắng vật lý vs hóa học,education,reach,2000,180,4\n"
        "2026-06-06,Retinol cho người mới bắt đầu,education,lead,2500,275,15\n"
        "2026-06-07,Cách chọn serum Vitamin C,comparison,reach,1800,108,6\n",
        encoding="utf-8",
    )

    comments_csv = tmpdir / "comment_inbox.csv"
    comments_csv.write_text(
        "created_at,source,message\n"
        "2026-06-05,comment,Da thiếu nước thì nên bắt đầu từ đâu?\n"
        "2026-06-05,inbox,Chi phí soi da là bao nhiêu?\n"
        "2026-06-06,comment,Da treatment bị khô thì xử lý sao?\n"
        "2026-06-07,comment,Kem chống nắng nào không gây bí da dầu?\n"
        "2026-06-08,comment,Retinol nồng độ nào cho người mới?\n",
        encoding="utf-8",
    )

    campaign_json = tmpdir / "campaign_notes.json"
    campaign_json.write_text(
        json.dumps(
            {
                "campaign_focus": ["soi da", "phục hồi da treatment"],
                "priority_objective": "lead",
                "notes": ["Đẩy dịch vụ soi da trong 7 ngày tới"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "history": post_history_csv,
        "metrics": metrics_csv,
        "comments": comments_csv,
        "campaign": campaign_json,
    }


# ────────────────────────────────────────
# STEP 2 — Tạo Mock TrendScraper
# ────────────────────────────────────────
def create_mock_scraper() -> MagicMock:
    """TrendScraper mock trả về dữ liệu skincare giống thật."""
    mock = MagicMock(spec=TrendScraper)

    mock.search_trends.return_value = [
        TrendItem(
            title="Kem chống nắng SPF 50+ cho da dầu: có gây bí da không?",
            source="Healthline VN",
            url="https://example.com/spf50-oily",
            snippet="Nhiều người cho rằng kem chống nắng SPF cao gây bí da...",
        ),
        TrendItem(
            title="Review serum Vitamin C giá rẻ tốt nhất 2026",
            source="Đẹp365",
            url="https://example.com/vit-c-review",
            snippet="Serum Vitamin C là 'cứu tinh' cho làn da xỉn màu...",
        ),
        TrendItem(
            title="Retinol cho người mới: nồng độ, cách dùng, lưu ý",
            source="Watsons Blog",
            url="https://example.com/retinol-beginner",
            snippet="Bắt đầu với Retinol không khó nếu bạn biết cách...",
        ),
        TrendItem(
            title="So sánh AHA vs BHA: nên chọn loại nào cho da mụn?",
            source="VnExpress",
            url="https://example.com/aha-bha",
            snippet="AHA và BHA là hai thành phần tẩy da chết phổ biến...",
        ),
        TrendItem(
            title="Mẹo dưỡng ẩm cho da dầu mụn mùa hè",
            source="Afamily",
            url="https://example.com/moisture-oily-summer",
            snippet="Da dầu cũng cần dưỡng ẩm, đặc biệt vào mùa hè...",
        ),
        TrendItem(
            title="Top 5 sản phẩm Niacinamide được ưa chuộng nhất 2026",
            source="Đẹp365",
            url="https://example.com/niacinamide-top5",
            snippet="Niacinamide là thành phần 'đa năng' được dân skincare yêu thích...",
        ),
        TrendItem(
            title="Treatment da mụn tại nhà: có hiệu quả không?",
            source="Healthline VN",
            url="https://example.com/acne-treatment-home",
            snippet="Các phương pháp treatment da mụn tại nhà đang lên ngôi...",
        ),
    ]

    mock.fetch_all.return_value = [
        TrendItem(title="Cách chọn kem dưỡng ẩm cho da dầu", source="VnExpress"),
        TrendItem(title="Chống nắng mùa hè đúng cách", source="24h"),
        TrendItem(title="Retinol có nên dùng hàng ngày không", source="Afamily"),
        TrendItem(title="Trị mụn hiệu quả với BHA", source="VnExpress"),
        TrendItem(title="Dưỡng ẩm sâu cho da khô", source="24h"),
    ]

    return mock


# ────────────────────────────────────────
# STEP 3 — Tạo Mock Facebook Client (competitor pages)
# ────────────────────────────────────────
def create_mock_fb_client() -> MagicMock:
    """Facebook API mock với dữ liệu post skincare giống thật."""
    mock = MagicMock(spec=FacebookPageClient)

    # Page info cho competitor pages
    mock.get_public_page_info.side_effect = lambda page_id: {
        "skincare_vn": {
            "name": "Skincare Vietnam",
            "category": "Health/Beauty",
            "fan_count": 25000,
        },
        "beauty_tips_asia": {
            "name": "Beauty Tips Asia",
            "category": "Health/Beauty",
            "fan_count": 18000,
        },
    }.get(page_id, {"name": "Unknown Page", "fan_count": 0})

    # Posts cho mỗi competitor page
    mock.get_public_page_posts.side_effect = lambda page_id, limit: {
        "skincare_vn": [
            {
                "message": (
                    "Mình vừa thử serum retinol mới và da căng bóng hẳn luôn! "
                    "So sánh retinol vs bakuchiol có bạn nào cần không? "
                    "Review đầy đủ mình sẽ up trong tuần này 🌟 "
                    "Tag @[lanpage:1:Laneige] và @[cerave_page:1:CeraVe] để xem thêm nhé"
                ),
                "created_time": "2026-06-06T09:00:00+0000",
                "likes": 120,
                "comments": 15,
                "shares": 8,
            },
            {
                "message": (
                    "Kem chống nắng vật lý hay hóa học? "
                    "Mình đã dùng cả 2 loại và đây là sự thật: "
                    "SPF 50+ PA+++ là chuẩn vàng cho da dầu mụn. "
                    "Dùng kem chống nắng mỗi ngày là bước quan trọng nhất!"
                ),
                "created_time": "2026-06-04T14:00:00+0000",
                "likes": 200,
                "comments": 30,
                "shares": 12,
            },
            {
                "message": "Cảm ơn mọi người đã theo dõi! Tuần sau mình sẽ review serum dưỡng ẩm hot nhất hiện nay.",
                "created_time": "2026-06-02T10:00:00+0000",
                "likes": 50,
                "comments": 5,
                "shares": 2,
            },
        ],
        "beauty_tips_asia": [
            {
                "message": (
                    "Top 3 serum vitamin C giá rẻ dưới 300k đáng mua nhất năm 2026! "
                    "Cả 3 đều có Vitamin C ổn định, không gây kích ứng. "
                    "Bạn đã dùng loại nào chưa? Comment bên dưới nhé! 💬"
                ),
                "created_time": "2026-06-05T08:00:00+0000",
                "likes": 95,
                "comments": 22,
                "shares": 10,
            },
            {
                "message": (
                    "Niacinamide hay Vitamin C dùng trước? "
                    "Mình chia sẻ routine sáng cho da dầu mụn: "
                    "Rửa mặt → Toner → Niacinamide → Dưỡng ẩm → Kem chống nắng. "
                    "Bạn nào có thắc mắc gì không? 😊"
                ),
                "created_time": "2026-06-03T11:00:00+0000",
                "likes": 150,
                "comments": 18,
                "shares": 7,
            },
        ],
    }.get(page_id, [])

    return mock


# ────────────────────────────────────────
# STEP 4 — Tạo Mock SearchClient cho OfferEvaluator
# ────────────────────────────────────────
def create_mock_evaluator_search() -> MagicMock:
    """OfferEvaluator search client mock giúp offer đạt score qua 0.5."""
    mock = MagicMock(spec=SearchClient)

    def search_trends_side_effect(
        queries: list[str], max_articles: int = 10
    ) -> list[Any]:
        """Trả về evidence phù hợp dựa trên query."""
        results = []
        for q in queries:
            q_lower = q.lower()
            if "chống nắng" in q_lower or "sunscreen" in q_lower:
                results.append(
                    MagicMock(
                        title="Kem chống nắng cho da dầu: review thực tế sau 30 ngày",
                        source="Review Skincare Blog",
                        url="https://example.com/sunscreen-review-30days",
                    )
                )
                results.append(
                    MagicMock(
                        title="SPF 50+ cho da dầu mụn: tổng hợp 10 sản phẩm tốt nhất",
                        source="Đẹp365",
                        url="https://example.com/spf50-top10",
                    )
                )
            elif "retinol" in q_lower:
                results.append(
                    MagicMock(
                        title="Retinol cho người mới: hướng dẫn từng bước",
                        source="Watsons Blog",
                        url="https://example.com/retinol-step-by-step",
                    )
                )
            elif "serum" in q_lower or "vitamin c" in q_lower:
                results.append(
                    MagicMock(
                        title="So sánh serum Vitamin C: 5 sản phẩm đáng mua nhất 2026",
                        source="Đẹp365",
                        url="https://example.com/vitamin-c-top5",
                    )
                )
            elif "niacinamide" in q_lower:
                results.append(
                    MagicMock(
                        title="Niacinamide 10% có tốt hơn 5% không? So sánh chi tiết",
                        source="Afamily",
                        url="https://example.com/niacinamide-comparison",
                    )
                )
        return results[:max_articles]

    mock.search_trends.side_effect = search_trends_side_effect
    return mock


# ────────────────────────────────────────
# STEP 5 — Chạy demo
# ────────────────────────────────────────
def run_demo():
    print("\n" + "=" * 70)
    print("  🧠  RESEARCH AGENT — DEMO PIPELINE ĐẦY ĐỦ")
    print("  Dữ liệu mô phỏng | Không cần API | Tất cả 3 phases")
    print("=" * 70)

    # Setup
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        data = create_fake_data(tmpdir)
        store = LocalSheetStore(
            calendar_csv=tmpdir / "calendar.csv",
            history_csv=data["history"],
            metrics_csv=data["metrics"],
        )

        mock_scraper = create_mock_scraper()
        mock_fb_client = create_mock_fb_client()
        mock_evaluator_search = create_mock_evaluator_search()

        # ─── ResearchTool với tất cả mocks ───
        service = ResearchTool(
            trend_scraper=mock_scraper,
            trend_analyzer=TrendAnalyzer([]),  # sẽ reset bên trong build_brief
            competitor_discovery=CompetitorPageDiscoveryTool(
                fb_client=mock_fb_client,
            ),
            offer_evaluator=OfferEvaluator(
                search_client=mock_evaluator_search,
            ),
        )

        # Source documents (giả lập nguồn RSS cố định)
        source_docs = [
            SourceDocument(
                source_id="healthline-1",
                source_name="Healthline VN",
                source_type="rss",
                url="https://example.com/spf50-oily",
                title="Kem chống nắng SPF 50+ cho da dầu mụn",
                content="Chọn kem chống nắng cho da dầu mụn cần chú ý SPF, kết cấu...",
                trust_score=0.85,
                freshness_score=0.9,
            ),
            SourceDocument(
                source_id="dep365-1",
                source_name="Đẹp365",
                source_type="website",
                url="https://example.com/vitamin-c-review",
                title="Top 5 serum Vitamin C đáng mua nhất 2026",
                content="Serum Vitamin C giúp làm sáng da, mờ thâm nám...",
                trust_score=0.7,
                freshness_score=0.8,
            ),
        ]

        # Source candidates
        source_candidates = [
            SourceCandidate(
                source_id="blogskincare",
                title="Blog Skincare Vietnam - chuyên review mỹ phẩm",
                url="https://blogskincare.example.com",
                snippet="Blog review mỹ phẩm uy tín, cập nhật thường xuyên",
                discovery_query="review mỹ phẩm skincare",
            ),
        ]

        # Page context
        page_context = {
            "page_name": "Skincare cho GenZ",
            "industry_focus": "chăm sóc da",
            "affiliate_offers": [
                {
                    "product_name": "Kem chống nắng",
                    "affiliate_link": "https://shop.affiliate.com/sunscreen",
                    "category": "sunscreen",
                    "commission_rate": 0.15,
                    "brand": "Anessa",
                },
            ],
        }

        # ──────────────────────────────────────
        # DEMO OUTPUT
        # ──────────────────────────────────────
        print(_header("📋 Bước 1: Đọc dữ liệu nội bộ"))
        history = store.read_post_history(limit=90)
        metrics = store.read_post_metrics()
        print(_chip("Post history", f"{len(history)} bài trong 90 ngày"))
        print(_chip("Post metrics", f"{len(metrics)} bài có dữ liệu hiệu suất"))
        print(_chip("File comment", data["comments"].name))
        print(_chip("Campaign focus", "soi da, phục hồi da treatment"))
        print(_chip("Priority objective", "lead"))

        print(_header("🌐 Bước 2: TrendScraper — web search + RSS scrape"))
        print(_chip("Mô phỏng search", "7 trend items trả về"))
        for t in mock_scraper.search_trends.return_value:
            print(f"    📄 {t.source}: {t.title[:60]}...")
        print(_chip("Mô phỏng fetch_all", "5 items từ nguồn cố định"))
        for t in mock_scraper.fetch_all.return_value:
            print(f"    📄 {t.source}: {t.title}")

        print(_header("📦 Bước 3: OfferDiscovery — phát hiện offer từ web crawl"))
        discoverer = OfferDiscoveryTool()
        discovered = discoverer.discover(
            source_documents=source_docs,
            external_trends=mock_scraper.search_trends.return_value,
            existing_offers=["Kem chống nắng"],
            max_offers=4,
        )
        print(f"  Phát hiện {len(discovered)} sản phẩm từ nội dung crawl:")
        if discovered:
            for d in discovered:
                print(f"    🔹 {d.product_name} → angle: {d.angle}")

        print(_header("📱 Bước 4: CompetitorPageDiscovery — scan Facebook đối thủ"))
        print(_chip("Seed pages", "['skincare_vn', 'beauty_tips_asia']"))
        fb_offers, new_pages = CompetitorPageDiscoveryTool(
            fb_client=mock_fb_client,
        ).discover(
            competitor_page_ids=["skincare_vn", "beauty_tips_asia"],
            existing_offers=["Kem chống nắng", *(d.product_name for d in discovered)],
        )
        print(f"  ➡️  Phát hiện {len(fb_offers)} offer từ Facebook:")
        for o in fb_offers:
            print(f"    🔹 {o.product_name} (angle: {o.angle}, source: FB)")
        if new_pages:
            print(f"  🌱 Tự mở rộng: phát hiện {len(new_pages)} page mới từ mention")
            for p in new_pages:
                print(f"    ➕ {p}")

        print(_header("🏆 Bước 5: build_brief() — pipeline hoàn chỉnh"))
        print("  Gọi ResearchTool.build_brief() với tất cả flags...\n")

        brief = service.build_brief(
            store=store,
            comment_csv=data["comments"],
            campaign_notes_file=data["campaign"],
            source_documents=source_docs,
            source_candidates=source_candidates,
            page_context=page_context,
            discover_product_topics=True,
            discover_offers=True,
            scan_competitor_pages=True,
            competitor_page_ids=["skincare_vn", "beauty_tips_asia"],
            max_product_topics=8,
        )

        # ─── Kết quả ───
        print(_header("📊 KẾT QUẢ RESEARCH BRIEF"))

        print("\n  📌 TOP 5 GÓC NHÌN ĐỀ XUẤT (next_angles):")
        for i, angle in enumerate(brief.next_angles, 1):
            print(f"    {i}. {angle}")

        print("\n  📈 TOPIC SCORES (xếp hạng):")
        for ts in brief.topic_scores[:5]:
            print(f"    {ts.total_score:.3f} — {ts.topic}")
            if ts.rationale:
                print(f"          ↳ {ts.rationale[:100]}")

        if len(brief.topic_scores) > 5:
            print(f"    ... và {len(brief.topic_scores) - 5} topic khác")

        print("\n  ⚠️  CẢNH BÁO CHẤT LƯỢNG (quality_warnings):")
        if brief.quality_warnings:
            for w in brief.quality_warnings:
                print(f"    ⚠️  {w}")
        else:
            print("    ✅ Không có cảnh báo")

        print(f"\n  📊 ĐIỂM TIN CẬY TỔNG THỂ: {brief.confidence_score:.3f} / 1.0")

        print("\n  📚 EVIDENCE THU THẬP ĐƯỢC:")
        if brief.evidence:
            for ev in brief.evidence[:5]:
                print(f"    📎 [{ev.source}] {ev.claim[:80]}")
            if len(brief.evidence) > 5:
                print(f"    ... và {len(brief.evidence) - 5} evidence khác")
        else:
            print("    (không có)")

        print("\n  🔑 TOP KEYWORD TREND:")
        if brief.trend_keywords:
            print(f"    {', '.join(brief.trend_keywords[:10])}")

        print("\n  📋 KHUYẾN NGHỊ:")
        for r in brief.recommendations:
            print(f"    💡 {r}")

        print(f"\n  ♻️  TOPIC ĐÃ DÙNG NHIỀU (overused):")
        if brief.overused_topics:
            for t in brief.overused_topics:
                print(f"    🔄 {t}")
        else:
            print("    (không có)")

        print(f"\n  🏆 TOP PERFORMING TOPICS:")
        for t in brief.top_performing_topics:
            print(f"    ⭐ {t}")

        print(f"\n  ❓ CÂU HỎI THƯỜNG GẶP:")
        for q in brief.frequent_questions:
            print(f"    💬 {q}")

        print(f"\n  🎯 CAMPAIGN FOCUS: {', '.join(brief.campaign_focus)}")
        print(f"  🎯 OBJECTIVES: {', '.join(brief.recommended_objectives)}")
        print(f"  🏛️  PILLARS: {', '.join(brief.recommended_pillars[:3])}")

        # ──────────────────────────────────────
        # Tổng kết
        # ──────────────────────────────────────
        print("\n" + "=" * 70)
        print("  ✅ DEMO HOÀN TẤT")
        print("=" * 70)
        print(f"\n  Tổng quan pipeline đã chạy:")
        print("  " + " → ".join([
            "📋 Nội bộ",
            "🌐 Web Search",
            "📦 OfferDiscovery",
            "📱 CompetitorFb",
            "📊 Evaluator",
            "✅ Brief",
        ]))
        print(f"\n  Dữ liệu demo:")
        print(f"    - Post history:     {len(history)} bài")
        print(f"    - Web trends:       {len(brief.external_trends)} items")
        print(f"    - Offer phát hiện:  {len(discovered)} (web) + {len(fb_offers)} (FB)")
        print(f"    - Góc nhìn đề xuất: {len(brief.next_angles)}")
        print(f"    - Topic scores:     {len(brief.topic_scores)}")
        print(f"    - Evidence:         {len(brief.evidence)} items")
        print(f"    - Khuyến nghị:      {len(brief.recommendations)}")
        print(f"\n  🚀 Muốn chạy thật? Cung cấp FB token + WebSearch key và dùng dữ liệu thật.")
        print()


if __name__ == "__main__":
    run_demo()
