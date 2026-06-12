# Code Review toàn diện — 2026-06-13

Phạm vi: toàn bộ repo (~50.5k LOC Python, 301 file, 84 file test). Phương pháp: khảo sát sâu 3 hướng song song (kiến trúc core / business logic / tests-CLI-ops), xác minh trực tiếp từng phát hiện trọng yếu theo file:line.

## 1. Tổng quan sức khỏe theo khu vực

| Khu vực | LOC | Điểm | Nhận xét ngắn |
|---|---|---|---|
| `audit/` (auditor.py) | 335 | 🟢 9/10 | Append-only SQLite, WAL, retention — mẫu mực |
| `memory/` | 604 | 🟢 8/10 | Sạch (đã vá leak connection 2026-06-13) |
| `models.py`, `utils.py`, `throttle.py` | 452 | 🟢 8/10 | Pydantic models gọn; TokenBucket có sẵn nhưng ít nơi dùng |
| `core/` (harness, bus, types) | 677 | 🟢 8/10 | Harness policy + audit tốt; reason code còn free-text |
| `agents/` (8 agents) | 4 109 | 🟡 7/10 | Đang phát triển mạnh; strategist trùng 70% với tools/content |
| `tools/publishing/` | 1 988 | 🟡 6/10 | 5 chỗ `except Exception` nuốt lỗi; gọi private method của store |
| `tools/content/` | 2 277 | 🟡 6/10 | hashtag.py trùng ~60% logic nội bộ; strategist trùng liên-module |
| `tools/analytics/` | 1 000 | 🟡 7/10 | Ổn; dashboard formatter to |
| `tools/research/` | 4 856 | 🟠 5/10 | Lớn nhất, lazy-init nuốt lỗi, URL hardcode, 20 file phân mảnh |
| `scraping/` | 1 199 | 🟠 5/10 | Không rate-limit, httpx.Client tạo mỗi call, timeout hardcode |
| `affiliate/` | 1 568 | 🟢 7/10 | Secrets qua env var đúng chuẩn (đã kiểm tra — KHÔNG hardcode) |
| `adapters/` (store ×3, LLM ×3 tầng) | ~4 500 | 🟠 5/10 | 3 backend trùng interface không Protocol; LLM 3 tầng indirection |
| CLI (×2 hệ) | 3 585 | 🔴 4/10 | 50 lệnh tồn tại SONG SONG ở 2 cây parser |
| Tests | 84 file | 🟢 8/10 | Cô lập env tốt, mock đủ LLM/FB/Telegram; ~55% module coverage |

## 2. Phát hiện nghiêm trọng nhất (đã sửa ngay trong 2 commit đầu)

### 2.1 🔴 P0 — Repo hỏng ở HEAD: package `tools/data/` chưa bao giờ được commit
Pattern `.gitignore` dòng 9 là `data/` **không neo gốc** → match mọi thư mục tên `data` ở mọi độ sâu, bao gồm `fanpage_agent/tools/data/`. Commit tái cấu trúc `9f1222f` (services/ → tools/) đã tạo thư mục này nhưng git lặng lẽ bỏ qua. Hậu quả: **bất kỳ ai clone repo đều không import nổi `fanpage_agent.tools`** (`tools/__init__.py:43` import `tools.data.data_fetch`).
- `MetricsAutoFetchTool`: khôi phục từ `9f1222f^:fanpage_agent/services/metrics_auto_fetch.py`.
- `DataFetchTool`: mất hoàn toàn khỏi lịch sử — tái dựng từ đặc tả trong `tests/test_data_fetch.py` (5 test) + 3 call site. 5/5 test pass.
- Fix gốc: neo pattern `/data/`, `/artifacts/`. → commit `76ad1ef`.

### 2.2 🟠 Suite test chưa bao giờ chạy được trên Windows (44 fail)
Nguyên nhân gộp: console cp1252 không in được tiếng Việt (~35 test CLI subprocess), `Path.rename` không overwrite, exec-bit không tồn tại, POSIX-absolute path bị coi là relative, **sqlite connection leak thật** (`with conn` của sqlite3 chỉ commit, không close — giữ file handle). → commit `0c76de6`, kết quả **647 passed / 0 failed** (chạy với `PYTHONUTF8=1`).

### 2.3 🟠 Bug tiềm ẩn: `scheduled-publish` crash với backend sqlite
[scheduled_publish.py:70](../../fanpage_agent/tools/publishing/scheduled_publish.py#L70) gọi `store._read_calendar_rows()` — method chỉ có trên `LocalSheetStore`. Chạy `--store-backend sqlite` → `AttributeError`. Sẽ sửa ở Phase 3 (Store Protocol).

## 3. Sơ đồ kiến trúc thực tế (2 runtime song song)

```
                       ┌──────────────── ENTRY POINTS ────────────────┐
                       │                                              │
   cron ×11 + Docker   │   pyproject console scripts                  │
   python -m fanpage_agent.main      fanpage-agent      fanpage-manager
            │                             │                   │
            ▼                             ▼                   ▼
   main.py cli() ── 12 runtime actions    fanpage_cli/ (51 lệnh)   manager_cli.py
            │ fallback                    │ 50 lệnh TRÙNG legacy
            ▼                             ▼
   legacy_cli.py (shim 8 LOC) ──► cli_commands/ (61 lệnh, parser 745 LOC)
            │                              │
            ▼                              ▼
   ┌─ Runtime B: agents/ ─┐      ┌─ tools/ (research|content|publishing|data|analytics) ─┐
   │ Orchestrator + 7 agent│      │  + scraping/ + affiliate/ + memory/ + audit/          │
   │ AgentBus + Harness    │      └────────────────────┬───────────────────────────────--─┘
   └──────────┬───────────┘                            │
              ▼                                        ▼
   ┌─ Runtime A: root agent.py ─┐        adapters/: llm/ (factory→openai|mock)
   │ Orchestrator LLM tool-loop │        store ×3: sqlite_store(2392) | sheet_store(663,
   │ + scheduler.py daemon      │        DEFAULT) | google_sheets_store(597, deprecated)
   └────────────────────────────┘        facebook_client | telegram_client | page_registry
```

Hai "não" tồn tại song song: **Runtime A** (root `agent.py` — LLM tool-loop, được test nhiều) và **Runtime B** (`agents/` multi-agent + harness — hướng phát triển hiện tại, 5 commit gần nhất). `fanpage_agent/agent/` (4 file) chỉ là shim re-export của Runtime A.

## 4. Ma trận trùng lặp CLI (đo bằng parser thực, 2026-06-13)

| Nhóm | Số lệnh | Ghi chú |
|---|---|---|
| Có ở CẢ HAI cây | **50** | Trùng cả tên; flags lệch nhẹ vài lệnh |
| Chỉ ở `cli_commands/` (legacy) | 11 | `auto-content-cycle, build-strategy, fetch-fb-data, learn, queue-*` (×6), `search-trends` |
| Chỉ ở `fanpage_cli/` | 1 | `init-sheets` |
| Runtime actions (main.py) | 12 | `tick, daemon, backup, restore, list-backups, check-db, harness-status, roadmap-status, research-standalone, page-status, competitor-learn, status` |

**Production thực tế đi qua `python -m fanpage_agent.main`** (toàn bộ `scripts/run_*.sh`, Dockerfile, docker-compose) → cây legacy mới là cây "sống"; `fanpage_cli/` là entry point pyproject nhưng chưa được cron dùng.

## 5. Top hotspots còn lại (sau 2 commit fix đầu)

| # | Vị trí | Vấn đề |
|---|---|---|
| 1 | `tools/research/research.py:72-103` | 3 chuỗi lazy-init `except Exception` nuốt sạch lỗi — brief thiếu dữ liệu mà caller không biết |
| 2 | CLI ×2 cây (50 lệnh trùng) | Mỗi sửa đổi phải làm 2 nơi; flags đã bắt đầu lệch |
| 3 | `tools/content/strategist.py` vs `agents/strategist.py` | ~70% logic trùng, `_infer_pillar()` cho kết quả khác nhau giữa 2 bản |
| 4 | `scraping/multi_source_search.py` | Không rate-limit, `httpx.Client` mỗi call, timeout hardcode; `throttle.TokenBucket` có sẵn mà không dùng |
| 5 | `tools/research/competitor_page_discovery.py:92-96` | Hardcode `http://localhost:8899` + mutate private `_backends` |
| 6 | Store ×3 không có Protocol | Thêm method = sửa 3 nơi, không type-check được; đã gây bug 2.3 |
| 7 | `tools/publishing/scheduled_publish.py:145-249` | 5 chỗ `except Exception` không log context |
| 8 | `tools/content/hashtag.py:298-496` | 3 method `_generate_*` trùng ~60% logic build pool (chưa có test riêng) |
| 9 | LLM 3 tầng: `llm_adapter` → `llm_client` (shim) → `llm/` | Indirection thừa 1 tầng |
| 10 | `pyproject.toml` | deps lệch requirements.txt; `py-modules` ship tên generic (`config`, `tools`...) ra site-packages; subpackage `tools/content|publishing|analytics|data` **thiếu `__init__.py`** → wheel build sẽ thiếu module (chỉ editable install che lấp) |

## 6. Điểm tốt đáng giữ

- `audit/auditor.py`: chuẩn mực — append-only, context manager, WAL, retention.
- Test isolation: `conftest.py` xóa toàn bộ app env mỗi test; mock LLM schema-aware.
- `core/harness.py`: policy gate + audit trail cho mọi action của agent.
- `throttle.py`: TokenBucket + retry-on-429 sạch (đã dùng đúng ở `facebook_client.py:36`).
- ResearchPacket + handoff policy (`ready/blocked/needs-review`): thiết kế evidence-gating tốt.

## 7. Trạng thái sau ngày review

| Mốc | Trạng thái |
|---|---|
| Baseline test | 🟢 647 passed / 0 failed (Windows, `PYTHONUTF8=1`) |
| P0 .gitignore + tools/data | 🟢 commit `76ad1ef` |
| Windows compat + sqlite leak | 🟢 commit `0c76de6` |
| Phase 1 quick wins (1.1–1.5) | 🟢 5 commits (SearXNG→Settings, dọn nuốt lỗi, rate-limit, deps+lock+packaging, `Settings.require`) |
| Phase 2 strategist core | 🟢 `3d03377` — `strategy_core.py` chung, 2 taxonomy cạnh nhau |
| Phase 3 store Protocol + bug sqlite | 🟢 `9d114d5` — kèm fix leak connection UnifiedStore + rollback mất history |
| Phase 4 LLM flatten | 🟢 `a018f43` |
| Phase 5 CLI consolidation | 🟢 `61e683a`+`bf849f1`+`3d69359` — 1 cây parser + 1 dispatch table, xóa ~2k LOC trùng, parity test |
| Increment 1 score-before-approval | 🟢 `7bf4cc4` — predictor nối vào approval queue + daily packet + Telegram (kèm fix bug `--score-variants` xóa items) |
| Suite cuối | 🟢 659 passed / 0 failed |
| Expansion Increment 2-5 | Chưa làm — xem [expansion plan](../plans/2026-06-13-expansion-plan.md) |
