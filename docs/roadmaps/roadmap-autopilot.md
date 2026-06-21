# Fanpage Agent Autopilot Roadmap

Mục tiêu: đưa Fanpage Agent tiến gần hệ thống multi-page có nghiên cứu đa nguồn, nội dung grounded bằng bằng chứng, và Harness kiểm soát agent an toàn.

## Phase 1 — Multi-Page Profile Foundation (done)
- Chuẩn hóa metadata cho từng page: `topic_focus`, `audience`, `community_value`, `banned_topics`, `research_sources`.
- Sửa config/registry để đọc đúng `PAGES` JSON va expose page context an toan, khong lo token.
- Thêm test cho default page, page summary và profile fields.

## Phase 2 — Page-Aware Research & Strategy (done)
- Gán `page_id` và `page_context` vào ResearchPacket de biet packet phuc vu page nao.
- Cho `research-standalone` nhận `--page-id` va luu trace nguon theo page.
- Cho Strategist dùng page topic/community value khi lập lịch.

## Phase 3 — Harness & Ops Contract (done)
- Tăng policy/audit để task public-facing cần page context.
- Harness ghi `page_id` vào event/audit, giup truy vet agent dang lam cho page nao.
- Giữ approval gate cho publish actions.

## Phase 4 — Evidence-Grounded Writer (done)
- Nối `ResearchPacket` và page context vào Writer de caption dua tren evidence, khong viet chung chung.
- Thêm citation/source hints vào draft metadata de nguoi duyet thay bai dua tren nguon nao.
- Thêm test Writer dùng packet evidence va community value cua page.

## Phase 5 — Page Status & Operator CLI (done)
- Thêm CLI xem page context/status theo từng page cho nguoi van hanh non-tech.
- Hiển thị research packet gần nhất, score, evidence count, va trang thai san sang viet bai.
- Thêm test CLI không lộ credential va output de doc.

## Phase 6 — End-to-End Safety Slice (done)
- Thêm test luồng ResearchPacket → Writer → Harness audit/status.
- Đảm bảo write public-facing bị chặn nếu thiếu page context.
- Cập nhật docs với cách chạy, cách kiểm tra và bước tiếp theo.

## Execution Rules
- Sau mỗi phase: chạy targeted tests, chạy full suite nếu thay đổi core, fix nếu fail, rồi commit và push.
- Nếu test fail: tạm dừng phase để fix, sau đó chạy lại test và tiếp tục.
- Không commit credential; audit/output phải redact token/secret/password.
