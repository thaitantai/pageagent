from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_PRODUCT_TOPIC_TEMPLATES = [
    ("education", "{pain}: {product} có giúp gì và cần lưu ý gì?"),
    ("myth_busting", "Những hiểu lầm thường gặp khi dùng {product} cho {pain}"),
    ("how_to", "Cách dùng {product} để hỗ trợ {benefit} an toàn hơn"),
    ("comparison", "Khi nào nên chọn {product} thay vì giải pháp thông thường?"),
    ("faq", "Khách hàng hay hỏi gì trước khi chọn {product}?"),
]

_AFFILIATE_TOPIC_TEMPLATES = [
    ("buying_guide", "Cách chọn {category} phù hợp khi {pain}"),
    ("comparison", "So sánh {product} với các lựa chọn cùng nhóm: ai phù hợp với ai?"),
    ("checklist", "Checklist trước khi mua {category}: đừng chỉ nhìn giá"),
    ("red_flags", "Dấu hiệu nên cân nhắc kỹ trước khi mua {category}"),
    ("faq", "Khách hàng hay hỏi gì trước khi chọn {product}?"),
]

_AFFILIATE_DISCLOSURE = "affiliate_disclosure_required"


@dataclass(frozen=True)
class ProductTopicCandidate:
    topic: str
    angle: str
    product_name: str
    customer_pain: str = ""
    research_query: str = ""
    product_relevance: float = 0.0
    customer_value: float = 0.0
    risk_level: str = "low"
    reason_codes: list[str] = field(default_factory=list)

    @property
    def is_affiliate_offer(self) -> bool:
        return "affiliate_offer" in self.reason_codes

    def as_topic_score_metadata(self) -> dict[str, Any]:
        return {
            "angle": self.angle,
            "product_name": self.product_name,
            "customer_pain": self.customer_pain,
            "research_query": self.research_query,
            "product_relevance": self.product_relevance,
            "customer_value": self.customer_value,
            "risk_level": self.risk_level,
            "reason_codes": list(self.reason_codes),
        }


class ProductAwareTopicDiscovery:
    """Generate product-led topic candidates without turning content into hard-selling."""

    def discover(self, page_context: dict[str, Any], max_topics: int = 8) -> list[ProductTopicCandidate]:
        offers = self._as_list_of_dicts(page_context.get("affiliate_offers"))
        products = self._as_list_of_dicts(page_context.get("products_services") or page_context.get("products"))
        pains = self._pain_points(page_context)
        candidates: list[ProductTopicCandidate] = []
        for offer in offers:
            candidates.extend(self._build_offer_candidates(offer, pains, page_context, max_topics - len(candidates)))
            if len(candidates) >= max_topics:
                return candidates[:max_topics]
        for product in products:
            candidates.extend(self._build_product_candidates(product, pains, max_topics - len(candidates)))
            if len(candidates) >= max_topics:
                return candidates[:max_topics]
        return candidates

    def _build_offer_candidates(
        self,
        offer: dict[str, Any],
        pains: list[str],
        page_context: dict[str, Any],
        remaining: int,
    ) -> list[ProductTopicCandidate]:
        name = str(offer.get("name", "")).strip()
        if not name or remaining <= 0:
            return []
        category = str(offer.get("category") or page_context.get("industry_focus") or "sản phẩm").strip()
        benefits = self._as_strings(offer.get("benefits")) or self._as_strings(offer.get("proof_points"))
        do_not_claim = self._as_strings(offer.get("do_not_claim"))
        competitors = self._as_strings(offer.get("competitors"))
        raw_policy = page_context.get("content_policy")
        content_policy: dict[str, Any] = raw_policy if isinstance(raw_policy, dict) else {}
        disclosure_required = bool(content_policy.get("affiliate_disclosure_required", True))
        risk_level = "medium" if do_not_claim else "low"
        pain_values = self._as_strings(offer.get("customer_pain_points")) or pains or benefits or [category]
        candidates: list[ProductTopicCandidate] = []
        for index, (angle, template) in enumerate(_AFFILIATE_TOPIC_TEMPLATES):
            pain = pain_values[index % len(pain_values)] if pain_values else "nhu cầu mua hàng"
            benefit = benefits[index % len(benefits)] if benefits else pain
            topic = template.format(product=name, category=category, pain=pain, benefit=benefit)
            reason_codes = ["affiliate_offer", "community_first", "evidence_required", f"angle:{angle}"]
            if disclosure_required:
                reason_codes.append(_AFFILIATE_DISCLOSURE)
            if do_not_claim:
                reason_codes.append("claim_guard_required")
            if competitors and angle == "comparison":
                reason_codes.append("competitor_comparison")
            candidates.append(ProductTopicCandidate(
                topic=topic,
                angle=angle,
                product_name=name,
                customer_pain=pain,
                research_query=f"{name} {category} {pain} {benefit} review comparison evidence".strip(),
                product_relevance=0.82 if name.lower() in topic.lower() else 0.68,
                customer_value=0.92 if angle in {"buying_guide", "checklist", "red_flags"} else 0.82,
                risk_level=risk_level,
                reason_codes=reason_codes,
            ))
            if len(candidates) >= remaining:
                return candidates
        return candidates

    def _build_product_candidates(
        self,
        product: dict[str, Any],
        pains: list[str],
        remaining: int,
    ) -> list[ProductTopicCandidate]:
        name = str(product.get("name", "")).strip()
        if not name or remaining <= 0:
            return []
        benefits = self._as_strings(product.get("benefits")) or self._as_strings(product.get("proof_points"))
        do_not_claim = self._as_strings(product.get("do_not_claim"))
        risk_level = "medium" if do_not_claim else "low"
        pain_values = self._as_strings(product.get("customer_pain_points")) or pains or benefits or [str(product.get("category", "sản phẩm")).strip()]
        candidates: list[ProductTopicCandidate] = []
        for index, (angle, template) in enumerate(_PRODUCT_TOPIC_TEMPLATES):
            pain = pain_values[index % len(pain_values)] if pain_values else "nhu cầu khách hàng"
            benefit = benefits[index % len(benefits)] if benefits else pain
            topic = template.format(product=name, pain=pain, benefit=benefit)
            reason_codes = ["product_context", f"angle:{angle}"]
            if do_not_claim:
                reason_codes.append("claim_guard_required")
            candidates.append(ProductTopicCandidate(
                topic=topic,
                angle=angle,
                product_name=name,
                customer_pain=pain,
                research_query=f"{name} {pain} {benefit} evidence advice".strip(),
                product_relevance=0.9 if name.lower() in topic.lower() else 0.75,
                customer_value=0.85 if pain else 0.65,
                risk_level=risk_level,
                reason_codes=reason_codes,
            ))
            if len(candidates) >= remaining:
                return candidates
        return candidates

    def _pain_points(self, page_context: dict[str, Any]) -> list[str]:
        pains = self._as_strings(page_context.get("customer_pain_points"))
        audience = page_context.get("audience") or page_context.get("target_audience") or ""
        if not pains and audience:
            pains = [str(audience)]
        if not pains:
            pains = self._as_strings(page_context.get("topic_focus"))
        return pains

    @staticmethod
    def _as_strings(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    @staticmethod
    def _as_list_of_dicts(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []
