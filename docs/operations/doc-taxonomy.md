# Documentation Taxonomy

Tài liệu trong repo được tổ chức theo vai trò và vòng đời, với `agent` là trục chính cho roadmap/spec/plan nghiệp vụ.

## Reading Order

1. `roadmap` chọn phase hoặc hướng phát triển.
2. `spec` định nghĩa trạng thái đúng của phase/module.
3. `plan` map spec sang module/file, task và verification.
4. `code/tests` là bằng chứng implementation.

## Directory Roles

- `docs/roadmaps/`
  Roadmap dài hạn theo sản phẩm, agent hoặc domain.
- `docs/specs/`
  Technical spec hoặc behavioral contract hiện hành.
- `docs/plans/`
  Kế hoạch thực thi cụ thể để hiện thực spec.
- `docs/operations/`
  Policy vận hành, deploy, release, và quy ước tài liệu.
- `docs/superpowers/`
  Chỉ dành cho artifact nội bộ workflow agent. Không là nơi mặc định cho tài liệu chính của dự án.

## Agent-First Structure

```text
docs/
  roadmaps/
    agents/
      <agent>-agent-roadmap.md
  specs/
    agents/
      <agent>/
        active/
        archive/
  plans/
    agents/
      <agent>/
        active/
        archive/
```

Với workstream không gắn chặt vào một agent, dùng `features/`, `operations/`, hoặc `architecture/` dưới `specs/` và `plans/`.

## Active And Archive

### Specs

- `active`
  File vẫn là source of truth hiện hành cho behavior/boundaries.
- `archive`
  File đã bị thay thế hoặc không còn mô tả đúng hệ thống hiện tại.

### Plans

- `active`
  File vẫn đang điều phối implementation hoặc còn follow-up task cần làm.
- `archive`
  File đã hoàn thành vai trò thi công hoặc không còn là plan hiện hành nữa.

## Change Rules

- Đổi hướng dài hạn: cập nhật `roadmap`.
- Đổi behavior, boundaries, responsibilities hoặc acceptance criteria: cập nhật `spec` trước.
- Đổi cách thi công, module/file cần sửa, task hoặc verification: cập nhật `plan`.

Task đã hoàn thành là historical record. Nếu có thay đổi sau đó:
- giữ task cũ nếu nó phản ánh đúng việc đã làm,
- thêm follow-up task mới nếu cần điều chỉnh hoặc migration,
- không ghi đè làm mất lịch sử completed task trừ khi chỉ chỉnh câu chữ cho khớp current state.

## Naming

- Roadmap: `<agent>-agent-roadmap.md`
- Spec: `YYYY-MM-DD-<topic>-spec.md`
- Plan: `YYYY-MM-DD-<topic>-plan.md`

Tên file nên mô tả capability hoặc implementation slice, không mô tả workflow tool.
