# Fanpage Agent Next Steps Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task when doing larger follow-up rounds.

**Goal:** Chuyển fanpage-agent từ mức `local runtime + eval` sang mức `vận hành được` với Telegram delivery thật, store thật, và cron-ready workflows.

**Architecture:** Giữ kiến trúc single orchestrator. Mỗi bước tiếp theo chỉ thêm 1 lane vận hành thực tế: delivery trước, rồi store, rồi automation. Mọi lane mới phải đi qua formatter/verifier/artifact hiện có, không tạo workflow song song mới.

**Tech Stack:** Python 3.11+, urllib stdlib HTTP clients, Pydantic settings/models, existing CLI (`argparse`), local CSV fallback, Telegram Bot API, Google Sheets adapter sau, cron sau.

---

## Current status snapshot

### Done
- `OpenAICompatibleClient` đã chạy được thật qua OpenAI-compatible HTTP API.
- `eval-all` đã chạy được cho research/planner/writer/verifier.
- Local artifacts + preview formatter đã có.

### Missing to become operational
- Gửi Telegram thật từ project runtime
- Google Sheets store thật bên cạnh local CSV fallback
- Cron-ready commands / jobs để chạy daily + weekly không cần tay
- Community triage lane sau cùng

---

## Phase 1 — Telegram sender thật (IMPLEMENT NOW)

### Task 1: Mở rộng config cho Telegram runtime
**Objective:** Cho runtime đọc đủ token/chat/base URL từ env.

**Files:**

- Modify: `fanpage_agent/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Verification:**
```bash
python3 -m unittest tests.test_config -v
```text

Expected: pass, có assert cho telegram fields.

### Task 2: Tạo Telegram adapter
**Objective:** Có HTTP client gửi message text qua Telegram Bot API.

**Files:**

- Create: `fanpage_agent/adapters/telegram_client.py`
- Test: `tests/test_telegram_client.py`

**Behavior:**

- require `TELEGRAM_BOT_TOKEN`
- require `TELEGRAM_CHAT_ID` hoặc override qua CLI
- POST tới `/bot<TOKEN>/sendMessage`
- parse JSON response
- raise lỗi rõ nếu HTTP/network/API fail

**Verification:**
```bash
python3 -m unittest tests.test_telegram_client -v
```

Expected: pass với fake local server / patched urlopen.

### Task 3: Thêm CLI `send-telegram-preview`
**Objective:** Đọc artifact JSON, render bằng formatter hiện có, gửi thật lên Telegram.

**Files:**

- Modify: `fanpage_agent/main.py`
- Test: `tests/test_send_telegram_cli.py`
- Reuse: `fanpage_agent/services/telegram_formatter.py`

**CLI contract:**
```bash
python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type plan \
  --input-file artifacts/plans/weekly-plan-....json
```

Optional:

- `--chat-id`
- `--disable-web-page-preview` (optional future, not needed now)

**Verification:**
```bash
python3 -m unittest tests.test_send_telegram_cli -v
```

Expected: CLI gửi thành công tới fake Telegram endpoint và trả JSON result.

### Task 4: Smoke run end-to-end cho Telegram delivery
**Objective:** Chứng minh flow artifact -> formatter -> sender -> API call chạy được.

**Files:**

- No new code, run smoke only

**Verification:**
```bash
python3 -m unittest discover -s tests -v
python3 -m fanpage_agent.main send-telegram-preview ...
```

Expected: full suite pass, smoke CLI pass.

---

## Phase 2 — Google Sheets store thật (NEXT)

### Task 5: Mở rộng config cho Google Sheets
**Files:**

- Modify: `fanpage_agent/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Fields:**

- `GOOGLE_SHEETS_ID`
- `GOOGLE_SERVICE_ACCOUNT_FILE`
- optional `GOOGLE_SHEETS_TABS_PREFIX`

### Task 6: Tạo `GoogleSheetsStore`
**Files:**

- Create: `fanpage_agent/adapters/google_sheets_store.py`
- Test: `tests/test_google_sheets_store.py`

**Minimum operations:**

- append plan rows
- read post history
- read post metrics
- approve/reject/publish update row

### Task 7: Chọn store qua config/CLI
**Files:**

- Modify: `fanpage_agent/main.py`
- Maybe create: `fanpage_agent/adapters/store_factory.py`
- Test: update CLI tests

**Rule:** local CSV remains fallback; Google Sheets is opt-in.

---

## Phase 3 — Cron-ready workflows (NEXT AFTER SHEETS)

### Task 8: Tạo command cho daily operator packet delivery
**Files:**

- Modify: `fanpage_agent/main.py`
- Maybe create: `fanpage_agent/services/delivery.py`
- Tests: `tests/test_delivery_cli.py`

**Goal:** Một command build daily packet rồi gửi Telegram luôn.

### Task 9: Tạo command cho weekly report delivery
**Files:**

- Modify: `fanpage_agent/main.py`
- Tests: `tests/test_weekly_report_delivery_cli.py`

### Task 10: Tạo cron specs/docs
**Files:**

- Create: `docs/cron/daily-ops.md`
- Create: `docs/cron/weekly-report.md`

**Goal:** Dễ map sang Hermes cron jobs sau này.

---

## Phase 4 — Community triage lane (LATER)

### Task 11: Tạo triage service + schema
**Files:**

- Modify: `fanpage_agent/models.py`
- Create: `fanpage_agent/services/community_triage.py`
- Tests: `tests/test_community_triage.py`

### Task 12: Add CLI for draft reply
**Files:**

- Modify: `fanpage_agent/main.py`
- Tests: `tests/test_triage_cli.py`

---

## Execution order
1. **Telegram sender thật**
2. **Google Sheets store thật**
3. **Cron-ready workflows**
4. **Community triage**

## Why this order
- Telegram delivery có thể verify ngay mà không phụ thuộc Google credentials.
- Sheets store nên làm sau khi delivery lane đã rõ shape output.
- Cron nên build trên commands đã ổn định.
- Triage là lane mở rộng, không phải lõi vận hành đầu tiên.

---

## This round scope
**This implementation round will execute Phase 1 only:** Telegram sender thật + CLI send flow + tests + smoke run.

## Done definition for this round
- Có adapter Telegram thật trong codebase
- Có CLI `send-telegram-preview`
- Unit test cho adapter pass
- CLI test pass
- Full suite pass
- Smoke run với fake local Telegram endpoint pass
