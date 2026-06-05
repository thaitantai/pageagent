# Fanpage Agent Autopilot Roadmap

Muc tieu: dua Fanpage Agent tien gan he thong multi-page co nghien cuu da nguon va Harness kiem soat agent.

## Phase 1 - Multi-Page Profile Foundation (done)
- Chuan hoa metadata cho tung page: `topic_focus`, `audience`, `community_value`, `banned_topics`, `research_sources`.
- Sua config/registry de doc dung `PAGES` JSON va expose page context an toan, khong lo token.
- Them test cho default page, page summary va profile fields.

## Phase 2 - Page-Aware Research & Strategy (done)
- Gan `page_id` va `page_context` vao ResearchPacket de biet packet phuc vu page nao.
- Cho `research-standalone` nhan `--page-id` va luu trace nguon theo page.
- Cho Strategist dung page topic/community value khi lap lich.

## Phase 3 - Harness & Ops Contract (done)
- Tang policy/audit de task public-facing can page context.
- Harness ghi `page_id` vao event/audit, giup truy vet agent dang lam cho page nao.
- Giu approval gate cho publish actions.

## Phase 4 - Next Development Queue
- Noi page context/research packet vao Writer de caption duoc grounded bang evidence va community value.
- Them CLI status cho research packets gan nhat theo tung page.
- Them E2E: comments -> ResearchPacket -> Strategist -> Writer -> Harness audit.
