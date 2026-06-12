# Refactor Plan — 2026-06-13

Nguồn chuẩn khi implement. Bối cảnh và bằng chứng: xem [code review](../reports/2026-06-13-code-review.md). Gate mỗi phase: `PYTHONUTF8=1 pytest -m 'not slow'` xanh (baseline 647 passed) → commit riêng.

## Phase 0 — Hoàn thành 2026-06-13
- ✅ P0: khôi phục `tools/data/` + neo `.gitignore` (`76ad1ef`).
- ✅ Windows compat + sqlite connection leak (`0c76de6`).
- ✅ Ma trận CLI: 50 lệnh trùng / 11 chỉ-legacy / 1 chỉ-fanpage_cli (xem report §4).

## Phase 1 — Quick wins

### 1.1 SearXNG URL → Settings
- `config.py`: thêm `searxng_base_url: str = "http://localhost:8899"` (`from_env` tự map `SEARXNG_BASE_URL` qua vòng lặp uppercase-field).
- `scraping/multi_source_search.py`: `SearXNGBackend` nhận URL từ caller; `MultiSourceSearchClient` thêm constructor param `backends` (hết mutate `_backends` private).
- `tools/research/competitor_page_discovery.py:92-96`: dùng settings + param mới.
- Test gate: `test_competitor_page_discovery.py`, `test_config.py`, `test_research_sources.py`.

### 1.2 Dọn nuốt lỗi im lặng — GIỮ semantics fallback, chỉ log + thu hẹp + surface
- `tools/research/research.py:72-103`: tách 3 helper `_default_*()`; catch `(ImportError, OSError, sqlite3.Error)`; `logger.warning` kèm tên component.
- `tools/publishing/scheduled_publish.py` (5 chỗ): giữ skip-and-continue, log kèm `calendar_id`, append vào field lỗi của `ScheduledPublishResult`.
- `tools/publishing/content_queue.py:99-108`: log path khi `JSONDecodeError/OSError`.
- `tools/content/auto_content.py:362-365`: log + key `gap_analysis_error` (additive).

### 1.3 Rate-limit + connection pooling cho scraping
- Copy pattern `facebook_client.py:36`: 1 `TokenBucket`/backend (mặc định rộng ~30 req/min, override được qua constructor), 1 `httpx.Client`/backend instance.
- Test mock không được block: default capacity phải đủ lớn.

### 1.4 Vệ sinh dependencies
- pyproject `[project.optional-dependencies]`: `google = [google-api-python-client>=2, google-auth>=2]`, `scraping = [scrapling, curl_cffi, browserforge, playwright]`.
- **Sửa packaging bug**: thêm `__init__.py` cho `tools/content|publishing|analytics` (wheel build thiếu module nếu không có — chỉ editable install che lấp).
- KHÔNG đụng `py-modules` (xem Deferred).

### 1.5 `Settings.require(*fields)`
- Raise `ConfigError` liệt kê env var thiếu; gọi ở đầu handler publish/deliver. KHÔNG validate trong `__init__` (hàng chục test build Settings rỗng).

## Phase 2 — Strategist convergence
- Tạo `fanpage_agent/tools/content/strategy_core.py` (pure functions, không LLM/IO): `infer_pillar()` (map keyword hợp nhất — conflict ưu tiên bản `agents/strategist.py:527` vì mới hơn), `compute_pillar_mix()`, weekly-frequency, trend-idea scoring, variant-scoring helpers.
- `StrategistTool` và `StrategistAgent` cùng gọi core. KHÔNG xóa file, KHÔNG đổi public API/schema.
- Gated: dedup `hashtag.py:298-496` CHỈ sau khi viết `tests/test_hashtag.py` characterization.
- Test gate: `test_strategist.py`, `test_agents.py`, `test_approval_variant_scoring.py`, `test_variant_scorer.py`, `test_orchestrator_integration.py`.

## Phase 3 — Store Protocol + fix bug scheduled_publish
- Tạo `adapters/store_protocol.py`: `@runtime_checkable Protocol` từ giao 3 backend (Calendar/Triage/Metrics) — typing additive.
- **Fix bug**: `scheduled_publish.py:70` → `list_calendar_items()` (verify đủ field `calendar_id/approval_status/status/date/caption_ref`); thiếu thì thêm public `read_calendar_rows()` cho cả 3 store.
- Cân nhắc promote API mà `DataFetchTool._upsert_metric_rows/_write_history` đang duck-type (`_append_history_entry`, metric-row upsert) thành method public trong Protocol.
- `store_factory.build_store()`: annotate return type; `DeprecationWarning` cho backend `google`.
- Test mới: scheduled publish với `UnifiedStore`; isinstance contract test parametrized trong `test_store_factory.py`.

## Phase 4 — LLM flatten
- `llm_adapter.py` import thẳng `fanpage_agent.adapters.llm`; grep-replace mọi import `llm_client` nội bộ. GIỮ `llm_client.py` làm shim (test import qua nó). Chỉ đổi import, không đổi logic.

## Phase 5 — CLI consolidation (3 commit, rủi ro cao nhất)

**Bất biến**: `python -m fanpage_agent.main <name>` (cron+docker+~40 test subprocess) VÀ `fanpage-agent <name>` giữ nguyên tên lệnh/flags. KHÔNG sửa cron scripts.

Ma trận (đo 2026-06-13): 50 lệnh trùng; 11 chỉ-legacy (`auto-content-cycle, build-strategy, fetch-fb-data, learn, queue-*×6, search-trends`); 1 chỉ-fanpage_cli (`init-sheets`); 12 runtime actions trong `main.py`.

- **5a — Dedup bodies**: với 50 lệnh trùng, `fanpage_cli` đăng ký flags theo bộ của `cli_commands` (cron đang dùng) nhưng `_handler` = handler import trực tiếp từ `fanpage_agent.cli_commands.<module>`. Thêm 11 lệnh chỉ-legacy vào `fanpage_cli` (cùng cách). **Parity snapshot test**: walk 2 cây argparse, assert trùng tên lệnh + flags.
- **5b — Flip fallback**: `main.py:cli()` fall-through → `fanpage_cli.main()`. Gom 12 runtime actions vào `fanpage_cli/runtime.py`. Gate: parity test + `test_cli.py` + `test_cron_wrapper_scripts.py`.
- **5c — Demote**: `cli_commands/parser.py` + `cli_commands/main.py` xóa CHỈ KHI grep zero importers; handler modules ở lại làm application layer.

## Phase 6 — Deferred (KHÔNG làm đợt này)
| Mục | Lý do hoãn |
|---|---|
| Di dời root modules / bỏ `py-modules` | Dual-module-instance hazard (`config.Settings` ≠ `fanpage_agent.config.Settings`, `_settings_cache` ×2); 14 import root trong tests |
| Xóa `google_sheets_store.py` | 6 file test riêng; đợt này chỉ DeprecationWarning |
| Xóa `sheet_store.py` | Là DEFAULT backend production (`STORE_BACKEND:-local`) |
| Xóa shims `agent/`, `legacy_cli.py`, `llm_client.py` | PR "shim removal" riêng, gate zero-importer |
| Validate Settings tại construction | Phá hàng chục test; đã có `require()` opt-in |

## Verification tổng
- Mỗi phase: `PYTHONUTF8=1 pytest -m 'not slow'` ≥ 647 passed.
- Cuối: `python -m fanpage_agent.main ops-status` + `fanpage-agent --help` smoke.
