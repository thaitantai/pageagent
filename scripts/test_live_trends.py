"""Test live TrendScraper (web search + RSS — không cần config gì cả)."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fanpage_agent.scraping.trend_scraper import TrendScraper
from fanpage_agent.scraping.trend_analyzer import TrendAnalyzer

scraper = TrendScraper()

print("=" * 60)
print("PART 1: Web search (DuckDuckGo) — 4 fallback queries")
print("=" * 60)

# Chỉ dùng 4 queries để nhanh
results = scraper.search_trends(
    queries=[
        "xu hướng chăm sóc da 2026",
        "review kem chống nắng tốt nhất 2026",
        "serum vitamin C review",
        "retinoid cho người mới bắt đầu",
    ],
    max_results_per_query=2,
    max_articles=8,
)

print(f"\n→ {len(results)} kết quả từ web search\n")
for i, r in enumerate(results[:6], 1):
    src = r.source[:30] if r.source else "?"
    snippet = (r.snippet[:120] + "…") if len(r.snippet or "") > 120 else (r.snippet or "")
    print(f"  {i}. {r.title[:70]}")
    print(f"     Nguồn: {src}")
    print(f"     {snippet}")
    print()

# PART 2: RSS scrape
print("=" * 60)
print("PART 2: RSS scrape (VnExpress, 24h, Afamily)")
print("=" * 60)
rss_items = scraper.fetch_all()
print(f"\n→ {len(rss_items)} kết quả từ RSS\n")
for i, r in enumerate(rss_items[:5], 1):
    print(f"  {i}. [{r.source}] {r.title[:90]}")

# PART 3: TrendAnalyzer
print("\n" + "=" * 60)
print("PART 3: TrendAnalyzer")
print("=" * 60)
all_trends = results + rss_items
if all_trends:
    analyzer = TrendAnalyzer(all_trends)
    report = analyzer.generate_report()
    print(f"\n→ Top keywords ({len(report.get('top_keywords', []))}):")
    for kw in report.get("top_keywords", [])[:10]:
        print(f"   • {kw['word']} (×{kw['count']})")
    print(f"\n→ Clusters ({len(report.get('clusters', {}))}):")
    for name, items in list(report.get("clusters", {}).items())[:5]:
        print(f"   • {name}: {len(items)} bài")
else:
    print("  Không có trend nào để phân tích.")

print("\n✅ Done!")
