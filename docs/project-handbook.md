# Sổ tay dự án Fanpage Agent (Project Handbook)

> Cập nhật 2026-06-13, sau đợt refactor 16 commits (suite 659 passed). Tài liệu này là **bản đồ toàn dự án cho người mới**: hệ thống làm gì, từng tầng hoạt động ra sao, và — quan trọng nhất — **muốn sửa hay thêm logic thì đụng vào đâu** (mục 12). Tài liệu chị em: [code review](reports/2026-06-13-code-review.md) · [tồn đọng](reports/2026-06-13-outstanding-issues.md) · [refactor plan](plans/2026-06-13-refactor-plan.md) · [expansion plan](plans/2026-06-13-expansion-plan.md).

## 1. Dự án là gì

Agent tự động vận hành fanpage Facebook (niche hiện tại: skincare GenZ, tiếng Việt), chạy trọn vòng: **nghiên cứu** (trend, đối thủ, affiliate, câu hỏi khách) → **chiến lược** (pillar mix, lịch tuần) → **viết caption** (đa variant, đa persona) → **duyệt** (người qua Telegram, hoặc auto-approval có gate) → **đăng FB** → **đo metrics** → **tự học** (điều chỉnh trọng số chấm điểm topic, dự đoán engagement). Production: Docker + 9 cron jobs, operator tương tác qua Telegram.

- Python ≥3.11, pydantic v2, httpx, scrapling, ddgs. ~50k LOC, 87 file test.
- Dev trên Windows: chạy test bằng `PYTHONUTF8=1 .venv/Scripts/python -m pytest -m 'not slow' -q`.

## 2. Bản đồ kiến trúc

```
ENTRY POINTS (chung MỘT cây parser, không thể trôi dạt — test_cli_parity.py gác)
  python -m fanpage_agent.main <cmd>   ← cron ×9 + Docker (production)
  fanpage-agent <cmd>                  ← console script (pyproject)
        │
        ▼
  fanpage_cli/__init__.py  =  cli_commands/parser.py (khai báo 61 lệnh)
                            + cli_commands/main.py HANDLERS (dispatch dict)
                            + fanpage_cli/runtime.py (12 runtime actions)
                            + fanpage_cli/sheets.py (init-sheets)
        │
        ├── HAI "NÃO" SONG SONG ──────────────────────────────────────┐
        │                                                             │
  RUNTIME A (root agent.py)                              RUNTIME B (agents/)
  LLM tool-loop: LLM tự chọn tool                        8 agent choreography qua AgentBus
  từ 16 tool whitelist (tools_defs/)                     shared-state versioning, Harness gác
  Lệnh: agent-tick, agent-daemon                         Lệnh: tick, daemon, status
        │                                                             │
        └──────────────┬──────────────────────────────────────────────┘
                       ▼
  TOOLS LAYER  fanpage_agent/tools/{research,content,publishing,data,analytics}
               + scraping/ + affiliate/ + memory/ + audit/ + ops/
                       ▼
  ADAPTERS     store ×3 (sqlite ✦ khuyến nghị | CSV ✦ default | google ✦ deprecated)
               facebook_client · telegram_client · llm/ (factory→openai|mock) · page_registry
                       ▼
  DỮ LIỆU      data/agent/agent.db (UnifiedStore 17 bảng) · data/agent/memory.db
               artifacts/ (output cron) · data/*.csv (backend local)
```

**Vì sao có 2 runtime?** Runtime A là bản production ổn định (LLM quyết định hành động kế tiếp qua tool-calling). Runtime B là hướng phát triển hiện tại (multi-agent tự đề xuất việc, có harness an toàn). Cả hai dùng chung tools layer. Chưa hợp nhất — đây là quyết định roadmap, không phải bug.

## 3. Vòng đời nội dung (state machine quan trọng nhất)

```
plan-week ──► calendar row: status=planned, approval_status=pending
                    │
        ┌───────────┼─────────────────┐
   (người duyệt)  (AutoApprovalEngine) (từ chối)
   approve-caption  5 gates             reject-caption
        │           │                   │
        ▼           ▼                   ▼
   approved     auto_approved       rejected (kết thúc)
        └─────┬─────┘
              ▼  scheduled-publish (5 gates) hoặc queue-publish
        status=published + permalink, reach=0
              ▼  auto-fetch-metrics / record-post-metrics
        post_metrics cập nhật → analytics → learning loop
```

**Gates của AutoApprovalEngine** ([auto_approval.py](../fanpage_agent/tools/content/auto_approval.py)): (1) chưa approved/published; (2) có `draft_caption_ref`; (3) không dính banned phrase trong hook/topic/cta; (4) không trùng topic với history; (5) `verify_plan()` pass. Tắt được từng gate qua `AutoApprovalConfig`.

**Gates của ScheduledPublishTool** ([scheduled_publish.py](../fanpage_agent/tools/publishing/scheduled_publish.py)): (1) chưa published; (2) approval_status ∈ {approved, auto_approved}; (3) có `final_caption_ref`; (4) date ≤ reference_date; (5) (tuỳ chọn) verify caption pass. Mỗi skip đều có `reason_code`.

**Verifier rules** ([verifier.py](../fanpage_agent/tools/content/verifier.py)): banned phrases (substring, không phân hoa thường); CTA bắt buộc mỗi ngày; chống trùng topic/hook với history (text normalize); tone: `tone_tags ⊆ brand_traits`, không chứa `things_to_avoid`, tuân `writing_rules` (rule phủ định "không/tránh/đừng/chớ" → pattern cấm).

## 4. Runtime A — root `agent.py` (LLM tool-loop)

**Tick flow** (`Orchestrator.run_tick`): (1) gọi `ops_status` lấy snapshot hệ thống → (2) build messages (system prompt + state JSON) → (3) vòng quyết định tối đa `max_actions_per_tick` (mặc định 5, tổng tool call ≤ `max_tick_calls`=15): LLM trả `tool_calls` → validate tên tool trong `allowed_actions` (whitelist 16 tool ở `AgentConfig`, [config.py](../config.py)) → `dispatch_tool()` ([tools.py](../tools.py)) → kết quả JSON đưa lại LLM; LLM không trả tool_calls = "WAIT" → dừng → (4) tổng kết → (5) gửi Telegram. LLM call retry 3 lần (5s/10s/20s). Daemon ([scheduler.py](../scheduler.py)): tick mỗi 7200s, lỗi thì backoff 60s→900s.

**16 tool LLM được phép gọi** (định nghĩa tại `fanpage_agent/tools_defs/`): `ops_status, run_daily, fill_calendar_gaps, list_calendar_items, approve/reject_calendar_item, list_triage_items, triage_community, approve/reject_triage_reply, write_caption, content_stats, scheduled_publish*, record_post_metrics, fetch_fb_comments, fetch_fb_data, send_telegram_message` (whitelist thực tế xem `AgentConfig.allowed_actions`).

## 5. Runtime B — multi-agent (`fanpage_agent/main.py` + `agents/` + `core/`)

**`create_pipeline()`** dựng: PerformanceMemory → LLMAdapter → 7 agent (Research, Strategist(+memory), Writer(+memory_dir), Designer, Community(+FB), Publisher(+FB,+memory), Analyst(+memory)) → AuditManager → AgentHarness → AgentBus → OrchestratorAgent(page_ids) → register tất cả.

**Choreography mỗi tick** (`OrchestratorAgent._tick`): (1) round-robin sang page kế (`_cycle_page`); (2) gather PipelineState + broadcast heartbeat vào `bus.shared_state`; (3) nếu thiếu content → set `pipeline_trigger=True`; (4) hỏi từng agent `self_driving_tick()` → list đề xuất `(action, params, priority)`, inject `page_id` vào params, dispatch qua bus (Harness validate trước khi agent chạy); (5) tổng kết + lưu state JSON.

**Chuỗi shared-state versioning** (cách agent "nói chuyện"): mỗi agent ghi `{"version": N, ...}` vào `shared_state[role]`; agent hạ nguồn so `upstream.version > my.processed_<upstream>_version` để biết có dữ liệu mới:

```
pipeline_trigger → Researcher (brief) → Strategist (schedule + strategy_packet)
→ Writer (ContentPackage, 5 tone persona) → Designer (visual_brief)
→ Publisher (publish_due → FB) → Community (self_reply, triage)
Analyst chạy theo timer (weekly_report 24h, pattern_analysis 12h)
```

**HarnessPolicy** ([core/harness.py](../fanpage_agent/core/harness.py)) chặn theo thứ tự: blocked_actions → per-role allowlist → capability check → payload ≤120k chars → `approval_required_actions` (publish_now, force_publish, publish_post, publish_package, publish_due, delete_post — cần `task.context["approved"]=True`) → `require_page_context_actions` (draft/publish/write cần page_id). Bị chặn không raise — trả `AgentResult(success=False)` + audit event `harness_status="blocked"`.

**page_context đi đâu**: vào từ `Settings.pages` (env `FB_PAGES` JSON) → `create_pipeline(pages)` → orchestrator inject `page_id` vào mọi task → agent `_resolve_page_id()` hoặc nhận `page_context` dict (Writer lọc whitelist key); `PageRegistry.page_context(page_id)` cấp cho research-standalone.

## 6. Hệ Research (subsystem lớn nhất, ~7.6k LOC)

**`ResearchTool.build_brief()`** ([research.py](../fanpage_agent/tools/research/research.py)) — 7 bước: (1) đọc history/metrics/comments/campaign từ store; (2) phân tích: overused (topic ≥2 bài), top performer (sort theo leads→engagement_rate→reach); (3) các nhánh discovery theo flag: `fetch_external_trends` (search_query_builder 7-tier → TrendScraper → TrendAnalyzer cluster), `discover_product_topics`, `discover_offers`, `scan_competitor_pages` (+CompetitorLearningEngine), affiliate qua `AffiliateRegistry.discover_all()`; (4) EvidenceExtractor + ResearchQualityGate; (5) OfferEvaluator vòng lặp ≤3 round tìm thêm evidence cho offer chưa đủ (ready khi score ≥0.5); (6) chấm điểm topic; (7) lưu `research_briefs` vào UnifiedStore làm dữ liệu học.

**Công thức chấm topic** (trọng số ĐỘNG, đọc từ bảng `goal_weights` theo goal của topic; mặc định): brand_relevance 0.25 · novelty 0.16 · content_potential 0.18 · source_confidence 0.14 · fanpage_fit 0.14 · customer_value 0.10 · duplication_penalty 0.03. Cộng thêm: perf_boost (≤+0.15, điều chỉnh theo variance), lifecycle boost (explore +0.10, mature +0.08, retire −0.30); trừ: risk medium −0.08, **affiliate thiếu evidence −0.18 và cap content_potential 0.45**.

**ResearchPacket & handoff policy** ([research_packet.py](../fanpage_agent/tools/research/research_packet.py)) — bảng quyết định an toàn cho Writer:

| Điều kiện | status | max_safe_use |
|---|---|---|
| high_risk topic ∨ confidence <0.35 ∨ affiliate blocker (URL <2, nguồn/domain <2, avg_conf <0.6, thiếu disclosure) | `blocked` | `draft_questions_only` (Writer KHÔNG được viết claim — daily_ops sinh checklist nghiên cứu thay caption) |
| có gate_reason bất kỳ (confidence <0.5, có warning, nguồn chờ duyệt...) | `needs_review` | `draft_with_citations` |
| sạch | `ready` | `draft_with_claims` |

**Learning loop** (chạy qua lệnh `learn`): `research_briefs` (điểm dự đoán) ⊕ metrics thật → variance → `WeightOptimizer` chỉnh trọng số kiểu PID (|corr| ≥0.25 tăng, <0.10 giảm; biên trong `_WEIGHT_LIMITS`) → ghi `learned_weights`/`goal_weights`; `ConfidenceCalibrator` chỉnh evidence floor (±0.03) + engagement baseline (smooth 90/10); `LifecycleManager` chuyển stage topic (explore→active ≥3 bài; active→mature ≥8; mature→retire >60 ngày im; decay half-life 21 ngày); `PerformancePredictor` hồi quy log-linear `log(eng+1)=a·score+b` (cần ≥5 brief có engagement; drift khi MAPE>40%) — từ Increment 1 điểm dự đoán này hiện trên approval queue qua `quality_block()` (không bao giờ raise, untrained → null).

**Scraping**: `MultiSourceSearchClient` = SearXNG (self-host, docker-compose, 30 req/min) + DDG (20 req/min) + VNCrawler (5 site VN cố định, cache 1h); `WebSearchClient` (DDG cũ) có TokenBucket + audit riêng. **Affiliate**: AccessTrade (REST, token header, parse commission "8.4%"/"140.000đ") + Shopee (GraphQL, HMAC-SHA256 sign) → `AffiliateRegistry` dedup theo tên chuẩn hoá, lọc `min_commission_rate`, sinh 2 angle (education + buying_guide) thành `ProductTopicCandidate`.

## 7. Models & prompts (hợp đồng dữ liệu)

Tất cả model pydantic ở [models.py](../fanpage_agent/models.py): `BrandProfile` (pillar, audience, tone, banned_phrases, approval_flow, CTA pattern) — load từ JSON qua `brand_loader`; `WeeklyPlan/PlanDay`; `CaptionPackage/CaptionVariant`; `VerificationResult`; `ResearchBrief/ResearchTopicScore (thang 0-10)/ResearchEvidence/TrendItem`; `ContentStrategy/StrategyIdea`; `PostHistoryEntry/PostMetric`; `CommunityTriageItem`; `AnalyticsReport`. Runtime B dùng dataclass riêng ở [core/types.py](../fanpage_agent/core/types.py) (`ContentPackage/ContentVariant` — KHÁC CaptionPackage). Prompts ở `fanpage_agent/prompts/*.md` load qua `PromptLoader` (cache + template format): writer system định nghĩa 5 persona + 6 hook style + 80-150 từ; planner system bắt JSON thuần.

## 8. Persistence

**UnifiedStore** (`data/agent/agent.db`, [sqlite_store.py](../fanpage_agent/adapters/sqlite_store.py)) — 17 bảng:

| Nhóm | Bảng | Ai ghi / ai đọc |
|---|---|---|
| Nội dung | `calendar`, `post_history`, `post_metrics`, `content_queue`, `hashtag_usage` | planner/approve/publish ghi; mọi lệnh ops + research đọc |
| Triage | `triage_items` | community triage ghi; approval lane đọc |
| Learning | `research_briefs`, `learned_weights`, `goal_weights`, `topic_goals`, `topic_performance`, `topic_lifecycle`, `learning_runs` | build_brief + learn ghi; _score_topics đọc |
| Competitor | `competitors`, `competitor_snapshots`, `competitor_products`, `competitor_candidates`, `competitor_gaps` | competitor-learn ghi; research/strategist đọc |

3 backend cùng thoả `FanpageStore` Protocol ([store_protocol.py](../fanpage_agent/adapters/store_protocol.py), contract test trong `test_store_factory.py`): sqlite (trên) · **local CSV (MẶC ĐỊNH production)**: content_calendar/post_history/post_metrics/triage/hashtag_performance.csv · google (deprecated, có DeprecationWarning). Ngoài ra: `memory.db` (PerformanceMemory: published_posts + performance_patterns — pillar/format/tone/hook_style/posting_hour, kèm backup rotation) và audit DB (append-only, retention 30 ngày, purge lúc init).

## 9. Adapters

- **FacebookClient**: cần `FB_PAGE_ID`+`FB_PAGE_TOKEN` (`Settings.require`); TokenBucket 180 req/h; retry 429 backoff; post_to_page/post_photo/get_page_posts (tự phân trang)/get_comments/get_post_insights; mọi call bọc audit.
- **TelegramClient**: cần `TELEGRAM_BOT_TOKEN`; `TELEGRAM_BASE_URL` override được (test dùng fake server). Lưu ý các digest triage gửi `parse_mode=None` để khỏi vỡ Markdown.
- **LLM** (`adapters/llm/`): factory theo `LLM_PROVIDER` (`mock-local` | `openai-compatible`). OpenAI client: thử `LLM_MODEL` → fallback từng model trong `LLM_MODEL_CANDIDATES`, **ghi nhớ model thành công** cho call sau; bóc JSON khỏi code fence; không streaming. Mock: deterministic, dùng cho test + dev.
- **Config resolution** ([config.py](../config.py)): default field → `.env` (tự dò từ cwd lên cha, tắt bằng `FANPAGE_AGENT_DISABLE_DOTENV=1`) → `os.environ` → env dict truyền tay. Validate tại USE-BOUNDARY bằng `settings.require(*fields)` (ConfigError liệt kê đủ biến thiếu), KHÔNG validate lúc khởi tạo. Multi-page: `FB_PAGES` JSON → `PageRegistry` (page default = legacy FB_PAGE_ID nếu có, không thì entry đầu).

## 10. CLI & vận hành

**62 lệnh** trên một cây (xem nhóm trong [parser.py](../fanpage_agent/cli_commands/parser.py)): planning (plan-week, *-calendar-gaps), research (research-brief, learn, search/research-trends), content (run-daily, write-caption, generate-hashtags, build-strategy, auto-content-cycle), publishing (publish-post, scheduled-publish, queue-*×6, approve/reject-*), triage (triage-community + 8 lệnh lifecycle), deliver-* (10 digest Telegram), analytics (weekly-report, dashboard, eval-all, fetch-fb-*), ops (ops-status, hermes-cron-status), agent (agent-tick/daemon = Runtime A), runtime (tick/daemon/status = Runtime B, backup/restore, research-standalone, page-status, competitor-learn), `fanpage-manager` riêng cho config/connect/status.

**Cron (Hermes)** — hợp đồng khai báo trong `EXPECTED_HERMES_CRON_JOBS` (parser.py), check bằng `hermes-cron-status`:

| Giờ UTC | Job → lệnh | Artifact |
|---|---|---|
| 00:30 | research brief → `deliver-research-brief --save` | artifacts/research/research-brief.json |
| 01:00 | daily packet → `deliver-daily-packet --save` | artifacts/ops/daily_ops_latest.json |
| 01:30 | approval queue → `deliver-approval-queue --save` (scoring default-ON) | artifacts/approvals/… |
| 02:00 | operator digest; **Thứ 2**: weekly report | artifacts/ops/… · reports/… |
| 03:00 / 03:30 | approval audit / metrics backlog | artifacts/audits/… · metrics/… |
| mỗi 2h (+15') | triage community / approved replies | artifacts/triage/… |

`ops-status --fail-on-stale` so mtime artifact với `OPS_ARTIFACT_FRESHNESS_HOURS` (30h mặc định, weekly 192h). Docker: image 3 stage, deps cài từ `requirements.lock` (sinh bằng `uv pip compile --python-version 3.11`), compose kèm service `searxng` cổng 8899.

## 11. Test

`conftest.py` xoá toàn bộ app env mỗi test (không lộ .env dev); subprocess test dùng `isolated_subprocess_env()`; mock LLM/FB/Telegram (fake HTTP server cho Telegram). 87 file: ~24 CLI subprocess, ~35 logic core, 12 adapters, còn lại delivery/affiliate. Chưa có test TRỰC TIẾP cho: `models.py`, `prompts/`, `agents/designer.py`, `agents/publisher.py`, `core/bus.py`, `core/harness.py` (đều được phủ gián tiếp qua orchestrator/integration). Test bất biến đáng biết: `test_cli_parity.py` (2 entry point 1 cây), `test_store_factory.py` (3 backend thoả Protocol), `test_package_boundaries.py` (không lộ .db/.env vào package), `test_cron_wrapper_scripts.py` (hợp đồng cron).

## 12. CẨM NANG: sửa / thêm logic ở đâu

| # | Muốn… | Đụng vào (theo thứ tự) |
|---|---|---|
| 1 | **Thêm lệnh CLI** | (1) khai báo subparser trong `cli_commands/parser.py`; (2) viết `cmd_*` trong module domain (`cli_commands/{publishing,triage,…}.py`); (3) thêm vào dict `HANDLERS` trong `cli_commands/main.py`. Xong — cả 2 entry point tự có lệnh; `test_cli_parity.py` tự phủ |
| 2 | **Thêm tool cho LLM (Runtime A)** | (1) viết hàm trong tools layer; (2) wrapper + `TOOL_DEFINITIONS` + `REGISTRY_BUILDERS` trong `tools_defs/<domain>.py`; (3) merge trong root `tools.py`; (4) thêm tên vào `AgentConfig.allowed_actions` (root `config.py`) |
| 3 | **Thêm agent thứ 9 (Runtime B)** | (1) `agents/newagent.py` kế thừa BaseAgent (role, capabilities, handle_task, self_driving_tick); (2) thêm enum `AgentRole` (`core/types.py`); (3) khởi tạo + `register_all` trong `main.py:create_pipeline`; (4) nếu cần chính sách: sửa `HarnessPolicy` |
| 4 | **Thêm action cho agent có sẵn** | nhánh mới trong `handle_task` + khai báo trong `capabilities` + (nếu tự kích hoạt) đề xuất trong `self_driving_tick`; nếu nhạy cảm → thêm vào `approval_required_actions` của HarnessPolicy |
| 5 | **Thêm method store** | (1) khai báo trong Protocol (`adapters/store_protocol.py`); (2) implement ở CẢ 3 backend (sqlite/sheet/google); (3) contract test trong `test_store_factory.py` sẽ bắt thiếu |
| 6 | **Thêm setting/env mới** | (1) field mới trong root `config.py:Settings` (from_env tự map ENV hoa); (2) ghi vào `.env.example`; (3) nơi dùng gọi `settings.require()` nếu bắt buộc |
| 7 | **Thêm cron job** | (1) entry trong `EXPECTED_HERMES_CRON_JOBS` (parser.py); (2) wrapper `scripts/run_*.sh` (cd PROJECT_DIR rồi exec); (3) lệnh CLI theo recipe #1; (4) nếu có artifact → thêm `OPS_ARTIFACT_FRESHNESS_HOURS`; (5) doc `docs/cron/*.md` |
| 8 | **Thêm digest Telegram** | (1) mixin `format_*` mới trong `tools/publishing/formatters/` + gắn vào `TelegramFormatterTool` (formatters/base.py); (2) method `deliver_*` trong `tools/publishing/delivery.py`; (3) lệnh `deliver-*` theo recipe #1. Payload có URL/underscore → `parse_mode=None` |
| 9 | **Thêm rule kiểm duyệt caption/plan** | method `_check_*` trong `tools/content/verifier.py`, gọi từ `verify_plan` / `verify_caption_package`; muốn rule chặn auto-approval → tự động có vì engine gọi verifier |
| 10 | **Thêm search backend** | class kế thừa `SearchBackend` trong `scraping/multi_source_search.py` (kèm TokenBucket); truyền qua param `backends=` của `MultiSourceSearchClient` |
| 11 | **Thêm affiliate provider** | (1) `affiliate/new_network.py` (is_configured + search_products → AffiliateProduct); (2) Config class + field trong `affiliate/config.py` (đọc env); (3) enum trong `affiliate/base.py`; (4) nhánh `_init_providers` trong `affiliate/registry.py`. build_brief tự dùng |
| 12 | **Chỉnh chấm điểm topic research** | trọng số mặc định + biên: `learning_optimizer.py` (`_WEIGHT_LIMITS`); công thức: `research.py:_score_topics`; gate an toàn: `research_packet.py:research_handoff_policy`; quality: `research_insights.py:ResearchQualityGate` |
| 13 | **Thêm/đổi giọng viết** | persona: `agents/writer.py` `_TONE_PERSONAS`; prompt nền: `prompts/writer_system.md` (sửa file .md là đủ, PromptLoader tự load); tool path: `adapters/llm/mock.py` + `openai.py` generate_caption_package |
| 14 | **Đổi keyword phân loại pillar / triage** | pillar: `tools/content/strategy_core.py` (`KEYWORD_GROUPS` + 2 taxonomy — MỘT nguồn cho cả 2 strategist); triage comment: keyword đầu file `tools/publishing/community_triage.py` |
| 15 | **Đổi lịch tick / số action mỗi tick** | Runtime A: `AgentConfig` (interval, max_actions_per_tick, max_tick_calls); Runtime B: interval cố định trong `self_driving_tick` từng agent (vd strategist 4h/8h, analyst 24h/12h) |

## 13. Gotchas tổng hợp (đọc trước khi sửa sâu)

1. **`.gitignore` phải neo gốc** — pattern `data/` không neo từng nuốt mất cả package `tools/data/` khỏi git. Mọi thư mục runtime: `/data/`, `/artifacts/`.
2. **sqlite `with conn:` chỉ commit, KHÔNG close** — cả `memory/core.py` lẫn `sqlite_store.py` đã chuyển `_conn()` thành contextmanager commit+close. Code mới đụng sqlite phải theo pattern này (Windows giữ file handle là không xoá/ghi đè được).
3. **2 hệ "variant" trùng tên khác schema**: `CaptionVariant` (models.py, tool path) ≠ `ContentVariant` (core/types.py, Runtime B). Convert qua `_content_package_from_caption_item` (cli_commands/content.py).
4. **VariantScorer trả điểm 0-100, predictor nhận 0-1** — `quality_block()` tự normalize; đừng đưa thẳng.
5. **`dispatch_tool` nuốt TypeError** (root tools.py): tool thiếu args sẽ bị gọi lại `fn()` không tham số thay vì raise — tool mới phải có default cho mọi param.
6. **Scoring approval queue default-ON** từ Increment 1; enrich trả SUMMARY và mutate items in-place — đừng gán kết quả đè lên items (bug cũ đã sửa, đừng tái phạm).
7. **CommunityAgent._auto_reply post thẳng FB** không qua duyệt — tồn đọng ưu tiên #1 (Increment 2), cân nhắc trước khi bật auto_reply.
8. **`Settings` khởi tạo dễ dãi có chủ đích** — validate bằng `require()` ở nơi dùng; đừng thêm validator bắt buộc vào `__init__` (vỡ hàng chục test).
9. **Backend mặc định là CSV (`local`)**, sqlite chỉ là khuyến nghị — feature mới đụng store phải chạy được trên CẢ HAI (Protocol + contract test giúp, nhưng logic dữ liệu vẫn phải nghĩ cho CSV).
10. **`FB_PAGES` JSON hỏng bị bỏ qua im lặng** (config.py) — multi-page "biến mất" thường do JSON sai.
11. **Triage/affiliate phân loại bằng substring tiếng Việt** — "review" khớp cả "preview"; thêm keyword phải nghĩ tới khớp nhầm.
12. **Audit purge chỉ chạy lúc init**; topic_performance decay phải gọi chủ động (`learn`) — không có background job.
13. **OPS_ARTIFACT_FRESHNESS_HOURS là dict tĩnh trong code** — đổi ngưỡng = sửa parser.py (chưa có env override).
14. Test trên Windows: bắt buộc `PYTHONUTF8=1`; exec-bit test skip trên Windows là đúng thiết kế.

## 14. Tồn đọng & việc tiếp theo

Toàn bộ tồn đọng (đều khắc phục được) + thứ tự đề xuất: xem [outstanding issues](reports/2026-06-13-outstanding-issues.md). Tóm tắt thứ tự: **Increment 2** (publish safety: sensitive-reply qua duyệt, dry-run, reason codes) → xóa shims + google store → **Increment 3** (next-actions loop) → **Increment 4** (page_id trong UnifiedStore) → **Increment 5** (CI + runbook + secret scan) → cuối cùng di dời root modules.
