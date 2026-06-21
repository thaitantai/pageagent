# Research Agent Handoff Spec

## Goal
Biến Research Agent thành nguồn research chuẩn hóa cho toàn pipeline bằng cách thêm một downstream handoff contract dùng chung cho Strategist, Writer và operator-facing flows.

## Scope
Phase này chỉ xử lý lớp handoff downstream từ `ResearchPacket`.

- Thêm một adapter/normalizer dùng chung để đọc `ResearchPacket`.
- Giữ backward compatibility với `research_brief` legacy shape.
- Chuyển Strategist và Writer sang dùng cùng contract normalize.
- Không thay đổi scoring core của `ResearchTool`.
- Không đổi format artifact `ResearchPacket` đã lưu trên disk.

## Problem
Current state đã có `ResearchPacket`, nhưng consumer logic vẫn bị tản mát:

- Strategist tự normalize `topic_scores`, `handoff_policy`, `page_context`, `blocked_topics`.
- Writer tự bóc `brief.evidence` và tự chặn `draft_questions_only`.
- Daily/operator flows lại giữ shape riêng.

Hệ quả là cùng một packet nhưng mỗi nơi hiểu khác nhau, làm tăng rủi ro:

- over-block hoặc under-block downstream behavior,
- drift giữa Strategist và Writer,
- khó test contract end-to-end,
- khó mở rộng thêm policy field mà không sửa nhiều nơi.

## Design

### Shared Handoff Adapter
Thêm một module nhỏ dưới `fanpage_agent/` để chuẩn hóa input research downstream.

Responsibilities:
- Nhận `dict | None` là `ResearchPacket`, `research_brief`, hoặc payload tương thích.
- Trả về một handoff context ổn định cho downstream:
  - `packet_id`
  - `status`
  - `safe_use`
  - `confidence_score`
  - `page_context`
  - `priority_topics`
  - `blocked_topics`
  - `evidence_refs`
  - `findings`
  - `quality_warnings`
  - `gate_reasons`

### Safe-Use Mapping
Adapter chịu trách nhiệm map `handoff_policy.max_safe_use` sang vocabulary downstream ổn định:

- `draft_questions_only` -> research-only / no public claim path
- `human_review` -> human-review-only draft path
- `public_draft` hoặc `draft_with_claims` -> public draft path

Strategist và Writer không tự map raw policy string nữa.

### Backward Compatibility
Nếu input chỉ có `research_brief` legacy:
- adapter vẫn đọc `confidence_score`, `topic_scores`, `evidence`, `findings`.
- `status` mặc định là `ready` nếu không có gate signals.
- `safe_use` mặc định là conservative public draft, nhưng không tạo fake gate reasons.

### Strategist Integration
Strategist dùng adapter để:
- lấy `priority_topics`/`blocked_topics`,
- đọc `safe_use` theo từng topic,
- giữ `page_context`,
- tạo `strategy_packet` nhất quán với evidence status.

### Writer Integration
Writer dùng adapter để:
- lấy evidence refs đã normalize,
- chặn đúng path `draft_questions_only`,
- gắn `research_packet_id` và `evidence_refs` vào output package metadata.

### Testing
Thêm test ở 3 lớp:
- adapter unit tests,
- Strategist regression tests,
- Writer regression tests.

## File Changes
- Create: `fanpage_agent/research_handoff.py`
- Modify: `fanpage_agent/agents/strategist.py`
- Modify: `fanpage_agent/agents/writer.py`
- Create: `tests/test_research_handoff.py`
- Modify: `tests/test_agents.py`

## Non-Goals
- Không thay schema persisted của `ResearchPacket`.
- Không refactor toàn bộ research pipeline.
- Không thêm source crawling mới.
- Không thêm dashboard/UI mới trong phase này.

## Acceptance Criteria
- Có một shared adapter duy nhất cho Research downstream handoff.
- Strategist và Writer không còn tự parse raw packet theo logic riêng cho phần shared fields.
- Ready/needs-review/blocked behavior giữ nguyên hoặc rõ hơn qua test.
- Backward compatibility với `research_brief` legacy còn hoạt động.
