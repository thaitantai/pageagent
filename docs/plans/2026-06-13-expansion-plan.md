# Expansion Plan — 2026-06-13

Nguyên tắc: ưu tiên NỐI các component đã tồn tại nhưng chưa được wire, thay vì xây subsystem mới. Trạng thái nền (đã xác minh trong code):

- `PerformancePredictor` (`tools/research/learning_predictor.py`) train trên `UnifiedStore.get_brief_feedback()`, persist qua `save_predictor_state` — **chỉ chạm tới được qua CLI `learn`**, chưa hề nối vào luồng duyệt.
- `VariantScorer` + `enrich_items_with_variant_scores()` (`cli_commands/content.py`) đã có, nhưng `deliver-approval-queue` cần flag `--score-variants` mà cron `run_approval_queue.sh` KHÔNG truyền → production duyệt bài không có điểm số.
- `strategy_packet.v1` (`agents/strategist.py:415-449`) mang `needs_human_review`/evidence status nhưng formatter Telegram (`formatters/triage.py`) không render.
- Reason codes publish-block có ở 2 chỗ (`cli_commands/publishing.py:62`, `triage.py:79`) nhưng `HarnessPolicy.is_action_allowed` chỉ trả free-text.
- `CommunityAgent._auto_reply` (`agents/community.py:456`) post thẳng lên FB chỉ gate bằng quality score — trong khi lane duyệt người (`approved-triage-replies`) đã tồn tại.
- Multi-page: `PageRegistry`, orchestrator round-robin, `page-status` CLI, `PerformanceMemory.page_id` đều có; **`UnifiedStore` chưa có cột `page_id` nào**.
- Không có CI (`.github/` không tồn tại) dù `ops-status --fail-on-stale` và `hermes-cron-status` là check làm sẵn.

## Increment 1 — Score-before-approval (LÀM NGAY, spec chi tiết §dưới)
Mọi caption operator thấy trên Telegram mang: (a) variant score theo pattern lịch sử, (b) predicted engagement + confidence từ predictor, (c) evidence/needs-review status. Thuần wiring, rủi ro thấp nhất, và **sinh ra dữ liệu** (score lúc duyệt ↔ outcome lúc đo metrics) mà Increment 3 cần.

## Increment 2 — Publish safety: reason codes + dry-run + sensitive-reply routing
- `core/reason_codes.py` (~30 LOC): hằng số chung (`blocked_action, role_not_allowed, missing_capability, payload_too_large, approval_required, missing_page_context`).
- `HarnessPolicy.is_action_allowed` trả `(allowed, reason, code)`; `HarnessEvent` thêm `reason_code`; thêm `auto_reply_sensitive` vào `approval_required_actions`.
- `CommunityAgent._auto_reply`: phân loại sensitivity tái dùng keyword/escalation của `CommunityTriageTool` — sensitive → `upsert_triage_items(status="pending")`, KHÔNG BAO GIỜ post thẳng.
- `ScheduledPublishTool` + CLI thêm `--dry-run` (mirror `ContentQueueTool`).

## Increment 3 — Weekly report → structured next-actions → Strategist intake
- `build_weekly_report` sinh `next_actions: [{action_type, target, evidence, priority}]` (`boost_pillar, retire_topic, shift_posting_hour, recalibrate_predictor, add_sources_for_topic`).
- `StrategistAgent._feedback_context` đọc `artifacts/reports/weekly-report.json`, apply + ghi `applied_actions` vào strategy_packet. Không có file → behavior hiện tại giữ nguyên.
- Phụ thuộc Increment 1 (cần cặp score↔outcome được log).

## Increment 4 — Per-page store separation + page-health
- `UnifiedStore`: cột `page_id` DEFAULT `'main'` (calendar, research_briefs, queue, topic_performance, predictor state) — copy pattern migration ALTER TABLE từ `memory/core.py`.
- `--page-id` cho các lệnh cron-facing; `page-status` → `page-health` (freshness, queue depth, pending approvals, token check) tái dùng `ops/sla.py`.
- Làm SAU 1–3 để migration cover các field mới một lần duy nhất.

## Increment 5 — Release hardening
- `.github/workflows/ci.yml`: pytest + `ops-status` smoke + `hermes-cron-status` contract. Lưu ý Windows: chạy với `PYTHONUTF8=1`; CI Linux không cần.
- `docs/runbook.md`: token hết hạn, queue kẹt, artifact stale, metrics backlog.
- Secret scan lịch sử git (gitleaks/trufflehog).
- Làm CUỐI: CI đóng băng interface — chạy sau khi 1–4 ổn định.

## KHÔNG xây đợt này
- Web dashboard multi-page (chưa có web surface nào; Telegram digest + page-health CLI đủ).
- LLM-judge eval set cho hook/pillar (chưa có labeled data — Increment 1/3 sinh dữ liệu trước).
- Auto-tuning weights không người duyệt (mẫu quá nhỏ: predictor cần ≥5 brief, drift MAPE>40%).
- Per-page daemon riêng (round-robin đủ cho <3 page).

---

# Đặc tả chi tiết Increment 1 (nguồn chuẩn khi implement)

## A. Schema payload

Mỗi item trong approval queue payload được enrich thêm key `quality` (additive — consumer cũ không vỡ):

```json
{
  "calendar_id": "...",
  "topic": "...",
  "quality": {
    "variant_score": 0.78,
    "variant_score_breakdown": {"hook": 0.8, "pillar": 0.7, "format": 0.85},
    "predicted_engagement": 142.5,
    "prediction_confidence": "medium",
    "predictor_status": "trained",
    "evidence_status": "ready"
  }
}
```

- `variant_score*`: từ `VariantScorer` (đường `enrich_items_with_variant_scores` hiện có).
- `predicted_engagement`: `PerformancePredictor.predict(...)`; `prediction_confidence`: bucket từ `get_quality()` (`high/medium/low`).
- `predictor_status`: `"trained" | "untrained"`. Untrained → `predicted_engagement: null`, KHÔNG crash, KHÔNG block delivery.
- `evidence_status`: từ `strategy_packet.needs_human_review`/handoff policy khi item sinh từ agent path; không có → omit.

## B. Điểm chạm code

| File | Thay đổi |
|---|---|
| `cli_commands/content.py::enrich_items_with_variant_scores` | Thêm `PerformancePredictor(store)`; attach block `quality` mỗi item; mọi exception predictor → `predictor_status: "untrained"` + log warning |
| `cli_commands/triage.py::cmd_deliver_approval_queue` | Scoring **default-ON**; thêm `--no-score-variants` opt-out (cron script giữ nguyên) |
| `tools/publishing/daily_ops.py::build_packet` | Attach `quality` block cạnh `handoff_policy` |
| `tools/publishing/formatters/triage.py::format_approval_queue` | Render: `⭐ score · 📈 ~eng (confidence) · 🧪 evidence` mỗi item; `⚠️ needs review` khi `needs_human_review` |

## C. Layout Telegram (format_approval_queue)

```
📋 Approval Queue (3 chờ duyệt)

1. [cal_123] Routine sáng cho da dầu — 2026-06-15
   ⭐ 0.78 · 📈 ~142 eng (medium) · 🧪 evidence: ready
   ✅ /approve_cal_123 · ❌ /reject_cal_123

2. [cal_124] Retinol cho người mới — 2026-06-16
   ⭐ 0.61 · 📈 — (predictor untrained) · ⚠️ needs review
   ...
```

## D. Test matrix

| Test | Fixture | Assert |
|---|---|---|
| `test_approval_variant_scoring.py` (mở rộng) | store seed qua `save_predictor_state` (slope/intercept cố định) | item có `quality.predicted_engagement` đúng công thức |
| nt. | store KHÔNG có predictor state | `predictor_status == "untrained"`, `predicted_engagement is None`, exit code 0 |
| `test_approval_queue_delivery_cli.py` (mở rộng) | chạy KHÔNG flag | scoring chạy (default-on); với `--no-score-variants` → không có block `quality` |
| `test_daily_ops.py` (mở rộng) | packet build | `quality` block tồn tại cạnh `handoff_policy` |
| formatter golden-string | payload mẫu 2 item (trained + untrained) | match layout §C |

## E. Acceptance
1. Telegram approval-queue hiện score + predicted engagement mỗi item; daily packet JSON có block `quality`.
2. Predictor chưa train → hiển thị `untrained`, không crash, không block.
3. Không lane duyệt mới; exit codes/flags lệnh cũ giữ nguyên; cron script không cần sửa.
