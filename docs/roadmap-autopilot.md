# Fanpage Agent Autopilot Roadmap

Muc tieu: dua Fanpage Agent tien gan he thong multi-page co nghien cuu da nguon va Harness kiem soat agent.

## Phase 1 - Multi-Page Profile Foundation
- Chuan hoa metadata cho tung page: topic focus, audience, community value, banned topics, research sources.
- Sua config/registry de doc dung FB_PAGES JSON va expose page context an toan, khong lo token.
- Them test cho default page, page summary va profile fields.

## Phase 2 - Page-Aware Research & Strategy
- Gan page context vao ResearchPacket de biet packet phuc vu page nao.
- Cho standalone research nhan page-id/page config va luu trace nguon theo page.
- Cho Strategist dung page topic/community value khi lap lich.

## Phase 3 - Writer Grounding
- Cho Writer nhan research priority topics/page context.
- Rang buoc caption theo evidence, value-to-community va tone cua page.
- Them test fallback de output khong bi chung chung khi khong co LLM.

## Phase 4 - Harness & Ops Contract
- Tang policy/audit de task public-facing can page_id va action dung role.
- Them CLI/doc/status de kiem tra roadmap, page registry va research packets.
- Chay full test, commit/push tung phase.
