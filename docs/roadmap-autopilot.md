# Fanpage Agent Autopilot Roadmap

Muc tieu: dua Fanpage Agent tien gan he thong multi-page co nghien cuu da nguon, noi dung grounded bang bang chung, va Harness kiem soat agent an toan.

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

## Phase 4 - Evidence-Grounded Writer
- Noi `ResearchPacket` va page context vao Writer de caption dua tren evidence, khong viet chung chung.
- Them citation/source hints vao draft metadata de nguoi duyet thay bai dua tren nguon nao.
- Them test Writer dung packet evidence va community value cua page.

## Phase 5 - Page Status & Operator CLI
- Them CLI xem page context/status theo tung page cho nguoi van hanh non-tech.
- Hien thi research packet gan nhat, score, evidence count, va trang thai san sang viet bai.
- Them test CLI khong lo credential va output de doc.

## Phase 6 - End-to-End Safety Slice
- Them test luong comments/research -> strategy -> writer -> harness audit.
- Dam bao publish/write public-facing bi chan neu thieu page context hoac approval.
- Cap nhat docs voi cach chay, cach kiem tra va buoc tiep theo.

## Execution Rules
- Sau moi phase: chay targeted tests, chay full suite neu thay doi core, fix neu fail, roi commit va push.
- Neu test fail: tam dung phase de fix, sau do chay lai test va tiep tuc.
- Khong commit credential; audit/output phai redact token/secret/password.
