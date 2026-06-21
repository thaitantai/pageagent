# Fanpage Agent

> Fanpage Agent là runtime duy nhất đang được phát triển liên tục cho việc lập kế hoạch, tạo nội dung, duyệt, xuất bản, chăm sóc cộng đồng và báo cáo hiệu quả fanpage.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Architecture](#architecture)
- [Architecture Decisions](#architecture-decisions)
- [Deployment](#deployment)
- [Development](#development)
- [Ghi chú](#ghi-chu)

## Features

| Trạng thái | Tính năng |
|------------|-----------|
| ✅ | Tick cycle: gather → decide → auto-generate → publish → repeat |
| ✅ | Facebook API publishing với PerformanceMemory recording |
| ✅ | Auto self-reply: LLM-generated comment ngay sau publish |
| ✅ | Quality gate: generic pattern rejection (9 patterns), 10-200 char bounds |
| ✅ | Facebook Insights: reach / engaged_users / engagement_rate qua /insights edge |
| ✅ | Writer: 6 hook patterns (education, problem, emotion, story, list, curiosity) với deterministic rotation |
| ✅ | Rotating hashtag pool per pillar |
| ✅ | Visual brief field trong ContentVariant |
| ✅ | CommunityAgent: live comment fetch + triage từ Facebook API |
| ✅ | Weekly analytics report cron |
| ✅ | Research Agent: topic discovery, trend analysis, offer evaluation |
| ✅ | AccessTrade affiliate API tích hợp |
| ✅ | Competitor page discovery từ Facebook |
| ✅ | Multi-agent pipeline: Research → Strategist → Writer → Designer → Publisher |
| ✅ | Hermes cron status reporter |
| ✅ | Settings auto-load từ .env |
| ✅ | replied_comments.json dedup tracking |

## Documentation Entry Points

Khi cần phát triển hoặc chỉnh sửa hệ thống, dùng entrypoint tài liệu theo thứ tự này:

1. `docs/roadmaps/roadmap-next.md`
   Dùng để xác định phase ưu tiên của sản phẩm.
2. `docs/roadmaps/agents/README.md`
   Dùng để chọn roadmap theo agent khi workstream gắn với một agent cụ thể.
3. `docs/specs/.../active/`
   Dùng để đọc source of truth hiện hành cho behavior và boundaries của capability đang sửa.
4. `docs/plans/.../active/`
   Dùng để xác định module/file cần sửa, task và verification.
5. `docs/operations/doc-taxonomy.md`
   Dùng để hiểu taxonomy tài liệu và rule `active/archive`.

Rule ngắn:
- Không implement trực tiếp từ roadmap.
- Lấy behavior từ spec active.
- Lấy module/file cần sửa từ plan active.
- Nếu spec hoặc plan chưa tồn tại, tạo chúng trước khi mở rộng capability đáng kể.

## Quick Start

1. Copy env template:

```bash
cp .env.example .env
```

2. Điền `LLM_API_KEY` thật của OpenRouter vào `.env`.

3. Đặt `LLM_MODEL` là model ưu tiên, và `LLM_MODEL_CANDIDATES` là danh sách fallback, ví dụ:
```env
LLM_MODEL=google/gemma-3-27b-it:free
LLM_MODEL_CANDIDATES=meta-llama/llama-3.3-8b-instruct:free,mistralai/mistral-small-3.2-24b-instruct:free,qwen/qwen3-14b:free
LLM_MAX_TOKENS=900

# nếu account có credit, có thể dùng:

# LLM_MODEL=openai/gpt-4.1-mini

# LLM_MODEL_CANDIDATES=

# LLM_MAX_TOKENS=1200
```

4. Repo giờ tự đọc `.env`, nên không cần `source .env` thủ công nữa. Khi model đầu fail kiểu `No endpoints found`, `404`, `402 insufficient credits`, client sẽ tự thử model kế tiếp trong `LLM_MODEL_CANDIDATES`. `LLM_MAX_TOKENS` cho phép hạ request size khi account credit thấp.

### Chạy test

```bash
python3 -m unittest discover -s tests -v
```

### Roadmap và trạng thái phát triển

Roadmap giai đoạn tiếp theo nằm tại `docs/roadmaps/roadmap-next.md`.
Package boundary notes nằm tại `fanpage_agent/README.md`.

```bash
python3 -m fanpage_agent.main roadmap-status
python3 -m fanpage_agent.main harness-status --data-dir data/agent --limit 5
```

## Usage

### Weekly plan

```bash
python3 -m fanpage_agent.main plan-week \
  --brand-file data/sample/brand_profile.json \
  --start-date 2026-06-01 \
  --days 3 \
  --save
```

### Caption package

```bash
python3 -m fanpage_agent.main write-caption \
  --brand-file data/sample/brand_profile.json \
  --topic "5 dấu hiệu da đang thiếu nước" \
  --pillar education \
  --objective engagement \
  --format post_short \
  --save
```

### Research brief

```bash
python3 -m fanpage_agent.main deliver-research-brief \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --comment-file data/comment_inbox.csv \
  --campaign-file data/campaign_notes.json \
  --save
```

### Daily packet

```bash
python3 -m fanpage_agent.main deliver-daily-packet \
  --brand-file data/sample/brand_profile.json \
  --run-date "$(date +%F)" \
  --days 1 \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --comment-file data/comment_inbox.csv \
  --campaign-file data/campaign_notes.json \
  --write-calendar \
  --save \
  --store-backend local
```

`run-daily --write-calendar --save` và `deliver-daily-packet --write-calendar --save`
sẽ lưu thêm `artifacts.caption_package` và ghi `draft_caption_ref` vào row calendar.

### Telegram preview

```bash
export TELEGRAM_BOT_TOKEN=your-bot-token
export TELEGRAM_CHAT_ID=your-chat-id

# Plan preview
python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type plan \
  --input-file artifacts/plans/weekly-plan-brand_abc-2026-06-30.json

# Approval preview
python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type approval \
  --input-file artifacts/approvals/approval-queue.json

# Research preview
python3 -m fanpage_agent.main send-telegram-preview \
  --artifact-type research \
  --input-file artifacts/research/research-brief.json
```

### Approval queue

```bash
# List pending items
python3 -m fanpage_agent.main list-calendar-items \
  --calendar-file data/content_calendar.csv \
  --approval-status pending

# Deliver queue digest
python3 -m fanpage_agent.main deliver-approval-queue \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --approval-status pending \
  --limit 5
```

### Post metrics

```bash
python3 -m fanpage_agent.main record-post-metrics \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --calendar-id weekly-plan-brand_abc-2026-06-25-1 \
  --reach 1800 \
  --engagements 126 \
  --leads 11 \
  --recorded-at 2026-06-26T08:00:00
```

### Metrics backlog

```bash
python3 -m fanpage_agent.main list-calendar-items \
  --calendar-file data/content_calendar.csv \
  --status published \
  --metrics-pending

python3 -m fanpage_agent.main deliver-metrics-backlog \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --status published \
  --metrics-pending \
  --limit 5
```

### Community triage

```bash
# Triage comments
python3 -m fanpage_agent.main triage-community \
  --brand-file data/sample/brand_profile.json \
  --comment-file data/comment_inbox.csv \
  --triage-file data/comment_triage.csv \
  --write-store

# Approve triage reply
python3 -m fanpage_agent.main approve-triage-reply \
  --triage-file data/comment_triage.csv \
  --triage-id <TRIAGE_ID> \
  --approved-by Tai \
  --approved-at 2026-06-24T09:00:00 \
  --assigned-to closer-1

# Mark as sent
python3 -m fanpage_agent.main mark-triage-reply-sent \
  --triage-file data/comment_triage.csv \
  --triage-id <TRIAGE_ID> \
  --sent-at 2026-06-24T09:15:00 \
  --reply-permalink https://facebook.com/comment/123 \
  --assigned-to closer-1

# Resolve triage item
python3 -m fanpage_agent.main resolve-triage-item \
  --triage-file data/comment_triage.csv \
  --triage-id <TRIAGE_ID> \
  --resolved-at 2026-06-24T10:00:00 \
  --assigned-to closer-1

# Deliver triage digest
python3 -m fanpage_agent.main deliver-triage-community \
  --brand-file data/sample/brand_profile.json \
  --triage-file data/comment_triage.csv \
  --from-store \
  --status new \
  --limit 3
```

### Hermes cron status

```bash
hermes cron list
python3 -m fanpage_agent.main hermes-cron-status
python3 -m fanpage_agent.main ops-status
python3 -m fanpage_agent.main ops-status --fail-on-stale
```

### Operator digest

```bash
python3 -m fanpage_agent.main deliver-operator-digest \
  --calendar-file data/content_calendar.csv \
  --history-file data/post_history.csv \
  --metrics-file data/post_metrics.csv \
  --triage-file data/comment_triage.csv \
  --limit 5 \
  --skip-empty \
  --save \
  --store-backend local
```

## Architecture

Fanpage Agent is a multi-agent orchestrator that runs as a Docker daemon and auto-generates content for Facebook.

### Architecture Decisions

Formal architectural decisions live in [`docs/adr/`](docs/adr/README.md).
Start there when you need the current rules for:

- external provider integration through adapters
- approval boundaries before live publishing
- durable state versus audit or artifact outputs
- root compatibility surfaces versus package-owned logic

### Pipeline

```text
🕐 Daemon (tick 600s)
  ├─ 1. Gather state (calendar, community, performance, system)
  ├─ 2. Decide actions
  │     ├─ auto-generate if calendar empty or periodic
  │     └─ refresh_metrics every 3 ticks
  ├─ 3. Run pipeline (when content needed):
  │      Research → Strategist → Writer → Designer → Publisher
  │        ├─ Writer: 6 hook patterns, deterministic rotation, rotating hashtag pool per pillar
  │        ├─ ContentVariant: visual_brief field for template paths
  │        └─ Publisher:
  │            ├─ publish to Facebook via API
  │            ├─ auto self-reply (LLM comment right after publish)
  │            ├─ track_performance (reach/impressions via /insights edge)
  │            └─ record to PerformanceMemory
  ├─ 4. CommunityAgent (each tick)
  │     ├─ fetch new comments from Facebook API
  │     ├─ triage + LLM auto-reply (quality-gated)
  │     └─ replied_comments.json dedup
  └─ 5. Analyst (weekly report, low priority)
```

### Agents

| Agent | Role | Key Capabilities |
|---|---|---|
| **Orchestrator** | Master tick loop, state gathering, decision making | gather_state → decide_actions → delegate to agents |
| **ResearchAgent** | Web search for trending topics | Topic discovery, trend analysis |
| **StrategistAgent** | Plan weekly content strategy | Pillar matching, format selection |
| **WriterAgent** | Generate captions and variants | 6 hook patterns (education, problem, emotion, story, list, curiosity), deterministic rotation, rotating hashtag pool per pillar, visual_brief field |
| **DesignerAgent** | Create visual briefs | Image prompt generation |
| **PublisherAgent** | Publish + track + self-reply | Facebook Graph API publish, auto LLM comment after post, Facebook /insights edge fetch (reach, engaged_users, engagement_rate), PerformanceMemory recording, periodic refresh_metrics |
| **CommunityAgent** | Comment fetch, triage, auto-reply | Live Facebook comment fetch, LLM reply generation, quality gate (substring pattern matching, 10–200 char filtering), generic reply rejection, replied_comments.json dedup |
| **AnalystAgent** | Performance reporting | Weekly analytics via Hermes cron |

### Quality Gate — Comment Filtering

All auto-generated replies pass through a quality gate before being posted:

- **Generic pattern rejection** — 9 patterns blocked (cảm ơn bạn/em/chị/anh, thanks bạn, ok bạn/em/chị/anh)
- **Length bounds** — min 10 chars, max 200 chars
- **Substring matching** — `in` operator for broader detection
- Replies that pass → posted to Facebook
- Replies that fail → logged + skipped (no crash)

### Facebook Insights Tracking

After each publish, the pipeline:

1. Calls `GET /{api_version}/{post_id}/insights?metric=post_impressions_unique,post_engaged_users`
2. Records `reach`, `engaged_users`, `engagement_rate`
3. Stores in PerformanceMemory via `record_metrics_update(package_id, variant_id, reach, engagements)`
4. Every 3 ticks, `refresh_metrics` batch-updates all existing posts (data available after ~24h)

### Memory System

- **PerformanceMemory** — SQLite-backed store tracking posts, patterns, and recommendations
- Tables:
  - `published_posts` — fb_post_id, pillar, format, variant_id, package_id, reach, engagements, engagement_rate, recorded_at
- Records: pillar performance, format effectiveness, hook styles, posting hour patterns, tone analysis
- Auto-generates actionable recommendations from learned patterns

### Data Files

Runtime data belongs in the project-level `data/` directory. Keep the top of `data/` as an index of purpose-based folders; do not leave loose CSV/JSON/DB files there.

```text
data/
├── agent/                 # Runtime state for the autonomous agent
│   ├── memory.db          # PerformanceMemory SQLite DB
│   ├── memory_snapshots/  # Rotated memory.db snapshots for restore
│   ├── state.json         # Tick state (calendar, community, performance, system)
│   ├── state.json.lock    # Concurrency lock
│   └── replied_comments.json
├── research_packets/      # Generated ResearchPacket JSON outputs
├── sample/                # Safe sample inputs for docs/tests
├── real/                  # Local live operator inputs; ignored by git
└── snapshots/             # Manual pre-run or pre-live snapshots of project data
```

## Deployment

### Docker

```bash
# Build image
docker build -t fanpage-agent:latest -f Dockerfile .

# Run container (interval=600s, writer_temp=0.7, hooks_temp=0.8, writer_max_tokens=3000)
docker rm -f fanpage-agent 2>/dev/null
docker run -d --name fanpage-agent --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/artifacts:/app/artifacts \
  fanpage-agent:latest

# Check logs
docker logs fanpage-agent --tail 20

# Watch live output
docker logs -f fanpage-agent

# Run single tick (CLI)
python3 -m fanpage_agent.main tick

# Run daemon (foreground)
python3 -m fanpage_agent.main daemon

# Check container health
docker ps --filter name=fanpage-agent --format "{{.Status}}"
```

### Cron Jobs

| Name | Schedule | Description |
|---|---|---|
| `fanpage-agent-status` | `0 */6 * * *` | container health + memory report via no-agent script |
| `fanpage-agent-weekly-report` | `0 2 * * 1` | Weekly analytics report (posts, reach, engagement, patterns) |

Detailed cron documentation at `docs/cron/`:
- [Hermes jobs](docs/cron/hermes-jobs.md) — 9 deployed jobs with schedule and wrapper contract
- [Daily ops](docs/cron/daily-ops.md), [Research brief](docs/cron/research-brief.md), [Approval queue](docs/cron/approval-queue.md)
- [Operator digest](docs/cron/operator-digest.md), [Approval audit](docs/cron/approval-audit.md)
- [Weekly report](docs/cron/weekly-report.md), [Metrics backlog](docs/cron/metrics-backlog.md)
- [Community triage](docs/cron/community-triage.md), [Approved triage replies](docs/cron/approved-triage-replies.md)

## Development

### Release notes

Project releases use git-cliff to generate `CHANGELOG.md` from Git history.

```bash
# Preview release notes for the next version
./scripts/changelog.sh v0.2.0

# Update CHANGELOG.md before tagging/deploying
./scripts/changelog.sh v0.2.0 --write
```

The command uses `cliff.toml` and should run as part of the deployment checklist before creating the Git tag. See `docs/operations/deploy.md` for the full deploy checklist.

### Next implementation tasks

- **P1:** A/B testing variants — writer generates 2+ variants, `VariantScorer` ranks them from performance memory
- **P2:** Daily community digests — cron job that fetches comments and delivers triage summary to Telegram
- **P2:** Dashboard HTML/Markdown tổng hợp cron health + artifact health + reach/engagement metrics
- **P3:** Multi-language support for auto-replies based on comment language detection

### Ghi chú

- Bản này đã có lane OpenAI-compatible thật.
- Đã có eval-all tối thiểu.
- Đã có Telegram delivery thật cho artifact preview.
- Đã có triage persistence + approve/reject/mark-replied/resolve/reopen workflow.
- Đã có store-backed triage digest delivery với filter theo status/priority/assigned_to.
- Đã verify Google Sheets live read/write/readback cho calendar; triage state path có local + Google adapter parity.
