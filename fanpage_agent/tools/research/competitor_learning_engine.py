#!/usr/bin/env python3
"""Competitor self-learning engine.

Three learning loops:

1. **Scan-&-Learn** — scan competitor web data → lưu snapshot → aggregate products
2. **Auto-Discover** — từ đối thủ hiện tại, search phát hiện đối thủ mới
3. **Trend Detection** — so sánh snapshot cũ vs mới → detect products/angles/formats thay đổi

Kết nối: CompetitorPageDiscoveryTool (web search) + UnifiedStore (SQLite persistence).

NOTE: Helper functions đã chuyển sang competitor_learning_store.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fanpage_agent.tools.research.competitor_learning_store import (
    _AUTO_PROMOTE_MIN_SCORE,
    _DISCOVERY_QUERIES,
    extract_brand_names,
    extract_next_topics,
    insight_to_gaps,
    profile_to_dict,
)

if TYPE_CHECKING:
    from fanpage_agent.adapters.sqlite_store import UnifiedStore
    from fanpage_agent.tools.research.competitor_page_discovery import (
        CompetitorPageDiscoveryTool,
    )

logger = logging.getLogger(__name__)


class CompetitorLearningEngine:
    """Self-learning engine cho competitor analysis.

    Flow:
    ```
    scan(competitor_names)
        ├→ search web (CompetitorPageDiscoveryTool.analyze_competitors())
        ├→ save snapshot (UnifiedStore.save_competitor_snapshot())
        ├→ aggregate products (UnifiedStore.record_competitor_product())
        └→ auto-discover → upsert candidates

    scan_auto_discover()
        ├→ lấy candidates score cao
        ├→ promote candidates >= threshold
        └→ scan lại với candidate mới
    ```
    """

    def __init__(
        self,
        discovery_tool: CompetitorPageDiscoveryTool,
        store: UnifiedStore,
    ) -> None:
        self._tool = discovery_tool
        self._store = store

    # ── Public API ──────────────────────────────────────────

    def record_scan_result(
        self,
        competitor_names: list[str],
        profiles: list[Any],
        insight: Any,
    ) -> dict[str, Any]:
        """Ghi nhận kết quả scan đã được tính từ bên ngoài.

        Không gọi analyze_competitors() lại — nhận profiles + insight có sẵn.
        Dùng sau ResearchTool.build_brief() đã chạy CompetitorPageDiscoveryTool.

        Steps: register → save snapshots → auto-discover → trends → gaps.
        """
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        snapshot_ids: list[int] = []
        all_products: dict[str, list[str]] = {}

        # ── Step 1: register competitors ──
        for name in competitor_names:
            self._store.upsert_competitor(name)

        # ── Step 2: save snapshots ──
        for profile in profiles:
            profile_dict = profile_to_dict(profile)
            products = profile.products_detected
            all_products[profile.name] = products

            sid = self._store.save_competitor_snapshot(
                competitor_name=profile.name,
                profile=profile_dict,
                products=products,
                next_topics=extract_next_topics(profile, insight),
            )
            snapshot_ids.append(sid)

            for prod in products:
                self._store.record_competitor_product(
                    competitor_name=profile.name,
                    product_name=prod,
                    relevance=0.5,
                )

        # ── Step 3: auto-discover ──
        discovered_new: list[str] = []
        if competitor_names:
            discovered_new = self._auto_discover(
                existing_names=competitor_names,
            )

        # ── Step 4: trend detection ──
        trends: dict[str, Any] = {}
        if profiles:
            trends = self._detect_trends(
                profile_names=[p.name for p in profiles],
            )

        # ── Step 5: save gaps ──
        if insight:
            gaps = insight_to_gaps(insight)
            self._store.save_competitor_gaps(gaps)

        return {
            "snapshot_ids": snapshot_ids,
            "discovered_candidates": discovered_new,
            "trends": trends,
            "products_by_competitor": all_products,
            "scanned_at": now,
        }

    def scan(
        self,
        competitor_names: list[str],
        save_snapshot: bool = True,
        discover_new: bool = True,
    ) -> dict[str, Any]:
        """Scan competitors, learn, and return structured results."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        snapshot_ids: list[int] = []
        all_products: dict[str, list[str]] = {}

        # ── Step 1: register competitors ──
        for name in competitor_names:
            self._store.upsert_competitor(name)

        # ── Step 2: analyze ──
        profiles, insight = self._tool.analyze_competitors(competitor_names)

        # ── Step 3: save snapshots ──
        if save_snapshot:
            for profile in profiles:
                profile_dict = profile_to_dict(profile)
                products = profile.products_detected
                all_products[profile.name] = products

                sid = self._store.save_competitor_snapshot(
                    competitor_name=profile.name,
                    profile=profile_dict,
                    products=products,
                    next_topics=extract_next_topics(profile, insight),
                )
                snapshot_ids.append(sid)

                for prod in products:
                    self._store.record_competitor_product(
                        competitor_name=profile.name,
                        product_name=prod,
                        relevance=0.5,
                    )

        # ── Step 4: auto-discover ──
        discovered_new: list[str] = []
        if discover_new and competitor_names:
            discovered_new = self._auto_discover(
                existing_names=competitor_names,
            )
        # ── Step 5: trend detection ──
        trends: dict[str, Any] = {}
        if save_snapshot:
            trends = self._detect_trends(
                profile_names=[p.name for p in profiles],
            )

        # ── Step 6: save gaps ──
        if save_snapshot:
            gaps = insight_to_gaps(insight)
            self._store.save_competitor_gaps(gaps)

        return {
            "profiles": [profile_to_dict(p) for p in profiles],
            "cross_competitor": {
                "shared_products": insight.shared_products,
                "unique_products_by_competitor": insight.unique_products_by_competitor,
                "gap_products": insight.gap_products,
                "underused_formats": insight.underused_formats,
                "recommendation": insight.recommendation,
            },
            "snapshot_ids": snapshot_ids,
            "discovered_candidates": discovered_new,
            "trends": trends,
            "products_by_competitor": all_products,
            "scanned_at": now,
        }

    def scan_auto_discover(
        self,
        min_score: float = _AUTO_PROMOTE_MIN_SCORE,
        max_new: int = 3,
    ) -> dict[str, Any]:
        """Auto-scan từ candidates đã tích lũy.

        1. Lấy candidates có score >= min_score
        2. Promote thành competitor thật
        3. Scan các competitor mới đó
        """
        candidates = self._store.list_competitor_candidates(
            min_score=min_score, limit=max_new,
        )
        if not candidates:
            return {"status": "no_candidates", "promoted": [], "scan": None}

        promoted_names: list[str] = []
        for c in candidates:
            result = self._store.promote_candidate(c["candidate_name"])
            if "error" not in result:
                promoted_names.append(c["candidate_name"])
                logger.info("Auto-promoted candidate: %s", c["candidate_name"])

        if not promoted_names:
            return {"status": "promotion_failed", "promoted": [], "scan": None}

        # Scan the newly promoted competitors
        scan_result = self.scan(
            competitor_names=promoted_names,
            save_snapshot=True,
            discover_new=True,
        )
        return {
            "status": "ok",
            "promoted": promoted_names,
            "scan": scan_result,
        }

    def get_learning_summary(self) -> dict[str, Any]:
        """Get summary of all learned competitors."""
        competitors = self._store.list_competitors()
        candidates = self._store.list_competitor_candidates(min_score=0)
        gaps = self._store.get_latest_gaps(limit=10)
        top_products = self._store.get_top_competitor_products(limit=15)

        # Per-competitor trend summary
        trends: list[dict[str, Any]] = []
        for c in competitors[:10]:
            trend = self._store.get_competitor_trend(c["name"])
            trends.append({
                "name": c["name"],
                "scan_count": trend["scan_count"],
                "auto_discovered": trend["auto_discovered"],
                "products_tracked": trend["products_tracked"],
                "new_products": trend["new_products"],
                "last_scanned": trend["last_scanned"],
            })

        return {
            "total_competitors": len(competitors),
            "auto_discovered": sum(1 for c in competitors if c["auto_discovered"]),
            "total_candidates": len(candidates),
            "competitors": trends,
            "top_products_across_competitors": top_products,
            "latest_gaps": gaps,
        }

    # ── Auto-discovery ──────────────────────────────────────

    def _auto_discover(self, existing_names: list[str]) -> list[str]:
        """Search for new competitor candidates from existing ones."""
        discovered: list[str] = []
        seen_names = {n.strip().lower() for n in existing_names}

        for name in existing_names:
            name_clean = name.strip()
            for template in _DISCOVERY_QUERIES:
                query = template.format(name=name_clean)
                try:
                    results = self._tool._search_competitor(name_clean)
                except Exception as exc:
                    logger.debug("Auto-discover query failed: %s — %s", query, exc)
                    continue

                for result in results:
                    # Extract potential brand names from titles/snippets
                    brand_candidates = extract_brand_names(
                        text=f"{result.title} {result.snippet}",
                        known_names=seen_names,
                    )
                    for cand_name, score in brand_candidates:
                        if cand_name.lower() in seen_names:
                            continue
                        self._store.upsert_competitor_candidate(
                            candidate_name=cand_name,
                            score=score,
                            source_scan=name,
                            source_query=query,
                        )
                        if cand_name not in discovered:
                            discovered.append(cand_name)

        return discovered

    # ── Trend detection ─────────────────────────────────────

    def _detect_trends(
        self, profile_names: list[str],
    ) -> dict[str, Any]:
        """So sánh snapshot mới nhất vs trước đó → phát hiện thay đổi."""
        new_products_all: dict[str, list[str]] = {}
        angle_changes: dict[str, list[str]] = {}
        format_changes: dict[str, list[str]] = {}
        product_trends: dict[str, int] = {}

        for name in profile_names:
            snapshots = self._store.get_competitor_snapshots(name, limit=2)
            if len(snapshots) < 2:
                # First scan — no trend
                current = snapshots[0] if snapshots else {}
                new_products_all[name] = current.get("products_json", []) if isinstance(current, dict) else []
                continue

            current = snapshots[0]
            previous = snapshots[1]

            cur_products = set(
                p.lower() for p in (
                    current["products_json"]
                    if isinstance(current, dict) else []
                )
            )
            prev_products = set(
                p.lower() for p in (
                    previous["products_json"]
                    if isinstance(previous, dict) else []
                )
            )

            new_products = cur_products - prev_products

            if new_products:
                new_products_all[name] = sorted(new_products)[:5]

            # Angle change
            if isinstance(current, dict) and isinstance(previous, dict):
                if current.get("unique_angle") != previous.get("unique_angle"):
                    angle_changes[name] = [
                        previous.get("unique_angle", ""),
                        current.get("unique_angle", ""),
                    ]

                # Format change
                if current.get("top_format") != previous.get("top_format"):
                    format_changes[name] = [
                        previous.get("top_format", ""),
                        current.get("top_format", ""),
                    ]

        # Aggregate product trends across all competitors
        for name, products in new_products_all.items():
            for p in products:
                product_trends[p] = product_trends.get(p, 0) + 1

        return {
            "new_products_detected": new_products_all,
            "angle_changes": angle_changes,
            "format_changes": format_changes,
            "rising_products": sorted(
                product_trends.items(), key=lambda x: x[1], reverse=True,
            )[:10],
            "competitors_with_new_products": [
                n for n, ps in new_products_all.items() if ps
            ],
        }
