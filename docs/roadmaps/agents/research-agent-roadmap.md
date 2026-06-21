# Research Agent Roadmap

## Goal
Hoàn thiện Research Agent thành một công đoạn độc lập, tạo ra `ResearchPacket` chuẩn hóa, có thể dùng lại an toàn cho Strategist, Writer, daily ops và operator review.

## Operating Rule
Mỗi phase phải pass targeted tests và smoke CLI liên quan trước khi chuyển phase. Nếu test fail, dừng phase, fix lỗi, chạy lại test rồi mới tiếp tục.

## Current State
- Đã có `ResearchPacket`, `research-standalone`, `page-status` và artifact JSON.
- Đã có evidence gate cơ bản với `status`, `gate_reasons`, `handoff_policy`.
- `run-daily` và `deliver-daily-packet` đã gắn research artifact.
- Strategist và Writer đã đọc được một phần packet, nhưng còn normalize rời rạc và chưa có một contract downstream dùng chung.

## Phase 1: Contract Stabilization
Outcome: mọi consumer downstream đọc cùng một hình dạng handoff, thay vì tự bóc `ResearchPacket` theo cách riêng.

Scope:
- Chuẩn hóa một lớp normalize/adapter cho downstream consumption.
- Giữ tương thích với `research_brief` legacy và `ResearchPacket` mới.
- Xuất rõ `safe_use`, `evidence_status`, `priority_topics`, `blocked_topics`, `page_context`, `evidence_refs`.
- Loại bỏ logic giải mã packet bị lặp giữa Strategist và Writer.

Acceptance tests:
- Strategist và Writer cùng đọc được packet từ cùng adapter.
- Packet bị block không thể rơi vào public writing path.
- Packet `needs_review` vẫn usable nhưng bị gắn human-review constraints.
- Packet `ready` giữ được evidence refs cho writing/output.

## Phase 2: Strategy Handoff
Outcome: Research Agent không chỉ đưa score, mà còn đưa ra handoff contract đủ rõ để Strategist chọn angle đúng mức rủi ro.

Scope:
- Thống nhất mapping `handoff_policy` -> strategy action.
- Bổ sung derived fields cho approval-ready strategy packet.
- Ưu tiên topic theo `topic_scores`, `confidence_score`, `source_documents`, `quality_warnings`.

Acceptance tests:
- Topic affiliate evidence yếu trở thành follow-up/questions flow.
- Topic `needs_review` thành human-review-only strategy brief.
- Topic educational evidence mạnh vẫn không bị over-block.

## Phase 3: Writing Guardrails
Outcome: Writer chỉ dùng claim/recommendation theo đúng policy mà Research Agent phát ra.

Scope:
- Chuẩn hóa evidence refs cho prompt grounding.
- Chặn path viết claim public khi `max_safe_use` không cho phép.
- Ghi rõ `research_packet_id` và evidence refs vào output package.

Acceptance tests:
- `draft_questions_only` không sinh caption claim-driven.
- `human_review_only` vẫn sinh draft nhưng có review note/risk note.
- `public_draft` giữ được citations/evidence refs trong package metadata.

## Phase 4: Operator Visibility
Outcome: operator nhìn thấy chất lượng research và lý do gate ngay trong artifact/digest.

Scope:
- Làm rõ summary cho source coverage, confidence, warnings, disclosure needs.
- Thêm view/list packet recent theo page và status.
- Chuẩn hóa trường tối thiểu cho cron/dashboard đọc lại.

Acceptance tests:
- `page-status` hiển thị packet summary đủ dùng cho vận hành.
- Daily packet/digest show research warnings nhất quán.

## Phase 5: Multi-Page Governance
Outcome: Research Agent scale an toàn cho nhiều page mà không trộn context hoặc source policy.

Scope:
- Tách page-level source policy và topic focus.
- Bảo toàn `page_id`, `page_context`, source selection theo từng page.
- Kiểm tra packet routing không bị chéo giữa nhiều fanpage.

Acceptance tests:
- Hai page khác nhau sinh packet khác context.
- Source registry selection đúng theo page/topic.
- Downstream packet routing không dùng nhầm page context.

## First Implementation Target
Bắt đầu từ Phase 1. `ResearchPacket` đã tồn tại, nhưng consumer contract downstream vẫn phân tán. Trước khi mở rộng scoring hay multi-page, cần khóa shared handoff contract để Strategist và Writer không diễn giải packet theo hai cách khác nhau.
