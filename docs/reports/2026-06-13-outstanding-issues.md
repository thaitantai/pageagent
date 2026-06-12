# Tồn đọng sau đợt refactor 2026-06-13 — và cách khắc phục

Trạng thái nền: 16 commits đợt 2026-06-13 đã hoàn tất toàn bộ refactor plan 6 phase + Expansion Increment 1. Suite: 659 passed / 0 failed. Tài liệu nguồn: [code review](2026-06-13-code-review.md), [refactor plan](../plans/2026-06-13-refactor-plan.md), [expansion plan](../plans/2026-06-13-expansion-plan.md).

**Kết luận: mọi tồn đọng đều khắc phục được — chúng nằm lại vì trình tự (cần quyết định vận hành, cần test trước, hoặc rủi ro cao hơn giá trị nếu làm vội), không phải vì bất khả thi.**

## Nhóm 1 — Rủi ro thật đang chạy production (ưu tiên cao nhất)

| # | Tồn đọng | Cách khắc phục | Công sức |
|---|---|---|---|
| 1.1 | `CommunityAgent._auto_reply` ([agents/community.py:456](../../fanpage_agent/agents/community.py)) post thẳng lên FB không qua duyệt người — comment nhạy cảm (khiếu nại, y tế, hoàn tiền) chỉ gate bằng quality score | Increment 2: tái dùng keyword/escalation của `CommunityTriageTool`, route sensitive → lane `approved-triage-replies` sẵn có; thêm `auto_reply_sensitive` vào `approval_required_actions` của harness | ~1 ngày |
| 1.2 | `scheduled-publish` không có `--dry-run` — không diễn tập publish được | Mirror pattern `dry_run` sẵn có trong `ContentQueueTool` | ~0.5 ngày |
| 1.3 | Không có CI (`.github/` không tồn tại) | Các check đã sẵn dạng CLI (`ops-status --fail-on-stale`, `hermes-cron-status`, pytest). Để cuối có chủ đích: CI đóng băng interface, chạy sau Increment 2-4 | ~0.5 ngày |

## Nhóm 2 — Sẽ thành bug khi mở rộng (theo trình tự expansion plan)

| # | Tồn đọng | Cách khắc phục |
|---|---|---|
| 2.1 | `UnifiedStore` không có cột `page_id` — score/feedback/topic là page-global; có page thứ 2 là predictor rank chéo niche | Increment 4: ALTER TABLE DEFAULT `'main'` (copy pattern migration từ `memory/core.py`). Làm SAU Increment 2-3 để migration cover field mới một lần |
| 2.2 | Weekly report chỉ là chuỗi human-readable, không có gì machine-readable chảy ngược về Strategist | Increment 3: `next_actions` structured + `StrategistAgent._feedback_context` intake. Thuần wiring |

## Nhóm 3 — Nợ kiến trúc hoãn có chủ đích (làm được, cần điều kiện)

| # | Tồn đọng | Điều kiện khắc phục |
|---|---|---|
| 3.1 | Root modules (`config.py`, `agent.py`, `tools.py`, `scheduler.py`, `cli.py`) ship tên generic ra site-packages qua `py-modules`; 2 lớp config re-export | Khó nhất: đổi MỌI import nội bộ sang package path trước → đảo chiều shim → bỏ `py-modules`. Làm ẩu = 2 instance `Settings` cache khác nhau (dual-module-instance hazard). ~2-3 ngày, PR riêng |
| 3.2 | `google_sheets_store.py` (597 LOC + 6 file test) — mới gắn `DeprecationWarning` | Xóa trong 1 PR minor-version (store + 6 test + 3 field Settings cùng lúc), sau khi xác nhận không ai dùng backend `google` |
| 3.3 | `sheet_store.py` CSV vẫn là backend MẶC ĐỊNH dù sqlite được khuyến nghị | Quyết định VẬN HÀNH: đổi `STORE_BACKEND=sqlite` trong cron → soak vài tuần → hạ CSV. Code đã sẵn sàng (Protocol + bug sqlite đã fix) |
| 3.4 | Shims còn lại: `fanpage_agent/agent/` (4 file re-export, 1 importer là `cmd_agent_tick`), `adapters/llm_client.py` (1 test import) | PR nhỏ ~1 giờ, gate zero-importer |
| 3.5 | `tools/content/hashtag.py:298-496` trùng ~60% logic pool-building giữa 3 method `_generate_*` | Viết `tests/test_hashtag.py` characterization TRƯỚC rồi mới dedup (hiện không có test riêng — refactor mù) |

## Nhóm 4 — Không khắc phục / không đáng

- **Hai runtime song song** (root `agent.py` tool-loop vs `agents/` multi-agent): không phải bug — kiến trúc đang chuyển giao. Hợp nhất là quyết định sản phẩm (chọn runtime B, port phần còn lại), để roadmap quyết.
- **Exec-bit check trên Windows**: bất khả thi do OS — test đã skip có chủ đích.
- **Dev machine Python 3.14 vs production 3.11**: rủi ro thấp (lock file pin cho 3.11); CI Linux ở Increment 5 đóng nốt.

## Thứ tự đề xuất

```
Increment 2 (publish safety — rủi ro mở duy nhất)
  → xóa shims + google store (rẻ, dọn sạch)
  → Increment 3 (next-actions loop)
  → Increment 4 (page_id)
  → Increment 5 (CI + runbook + secret scan)
  → cuối cùng: root modules (3.1)
```
