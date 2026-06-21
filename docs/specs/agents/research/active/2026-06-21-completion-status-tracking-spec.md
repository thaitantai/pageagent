# Research Agent Completion Status Tracking Spec

## Goal

Đóng vòng completion cho Research Agent bằng cách đưa roadmap, spec, plan và CLI status về cùng một trạng thái có thể kiểm chứng được từ code, test và artifact hiện có.

## Scope

Phase này không thêm capability research mới. Nó chuẩn hóa cách repo biểu diễn và kiểm chứng trạng thái hoàn tất của Research Agent.

Bao gồm:

- cập nhật roadmap Research Agent để phản ánh đúng các phase đã hoàn thành,
- thêm active spec/plan hiện hành cho workstream completion/status tracking,
- mở rộng CLI status để đọc được roadmap theo target thay vì chỉ product roadmap chung,
- thêm test cho status parsing/reporting của research roadmap,
- giữ archive handoff contract cũ làm historical record.

Không bao gồm:

- thay đổi schema `ResearchPacket`,
- thay đổi behavior của `research-standalone`, `page-status`, `run-daily`, `deliver-daily-packet`,
- thêm phase research mới vượt ngoài roadmap hiện tại.

## Problem

Research Agent đã có phần lớn implementation cho các phase trong roadmap, nhưng repo chưa chứng minh được completion một cách nhất quán:

- roadmap research vẫn còn mô tả `First Implementation Target` như thể mới dừng ở Phase 1,
- `docs/specs/agents/research/active/` và `docs/plans/agents/research/active/` đang trống,
- `roadmap-status` chỉ đọc `docs/roadmaps/roadmap-next.md`, nên không phản ánh được trạng thái roadmap research,
- completion audit vì thế thiếu bằng chứng machine-readable cho riêng Research Agent.

## Design

### 1. Research roadmap becomes authoritative current-state record

`docs/roadmaps/agents/research-agent-roadmap.md` vẫn là roadmap nguồn cho Research Agent, nhưng nội dung phải phản ánh current state đã được kiểm chứng:

- Phase 1-5 được đánh dấu rõ là đã hoàn thành nếu code/test hiện tại đã chứng minh đủ acceptance,
- phần current state và next target phải khớp với code hiện tại,
- `First Implementation Target` được thay bằng next target thực tế hoặc completion note phù hợp.

Roadmap không được tuyên bố completed cho phase nào nếu chưa có evidence từ test/CLI hiện tại.

### 2. Status CLI supports roadmap target selection

CLI status được mở rộng để đọc roadmap theo target thay vì hard-code product roadmap chung.

Yêu cầu behavior:

- vẫn giữ backward compatibility với `roadmap-status` hiện tại khi không truyền target,
- hỗ trợ chọn research roadmap bằng target/agent argument rõ ràng,
- output JSON giữ shape hiện tại tối đa có thể, chỉ thêm trường mới khi cần để chỉ ra roadmap target/path thực sự đang đọc,
- phase parsing tiếp tục hỗ trợ tiếng Việt có dấu như logic hiện tại.

### 3. Completion evidence is testable

Phải có targeted tests chứng minh:

- `roadmap-status` mặc định vẫn đọc product roadmap như cũ,
- research roadmap có thể được parse/report riêng qua CLI/helper mới,
- research roadmap report đúng phase done/active dựa trên text hiện hành,
- output chứa đúng roadmap path và next/current phase tương ứng.

### 4. Active spec/plan lifecycle

Archive handoff contract cũ vẫn giữ nguyên vì đó là historical record cho một phase đã hoàn thành.

Active spec/plan mới là source of truth hiện hành cho workstream completion/status tracking cho đến khi phase này hoàn thành và được archive sau.

## File Changes

- Create: `docs/specs/agents/research/active/2026-06-21-completion-status-tracking-spec.md`
- Create: `docs/plans/agents/research/active/2026-06-21-completion-status-tracking-plan.md`
- Modify: `docs/roadmaps/agents/research-agent-roadmap.md`
- Modify: `fanpage_agent/status_cli.py`
- Modify: `fanpage_agent/runtime_cli/dispatcher.py`
- Modify: `tests/test_audit.py`

## Acceptance Criteria

- Research Agent có active spec và active plan hiện hành trong đúng taxonomy.
- `roadmap-status` vẫn hoạt động cho product roadmap mặc định.
- Có cách machine-readable để đọc trạng thái roadmap Research Agent qua CLI/helper.
- Research roadmap phản ánh đúng current implementation state thay vì còn ghi như mới ở target Phase 1.
- Tất cả test liên quan pass, và full suite pass.
