# Changelog

All notable changes to Fanpage Agent are documented in this file.

## [0.1.0] - 2026-06-05

### Features

- Bootstrap fanpage agent workflows, cron wrappers, operator digests, approval flow, and scheduled publish helpers.
- Add analytics, scraping, Facebook client, fanpage-manager CLI, Dockerfile, and docker-compose support.
- Improve Writer Agent with GenZ tone personas, pillar hashtags, smart scheduling, hook rotation, format rotation, and content quality scoring.
- Add seasonal topic fallback and operations artifact freshness checks.

### platform

- Upgrade daemon to multi-agent architecture with Orchestrator, Strategist, Writer, Designer, Community, and Analyst agents.
- Add PerformanceMemory SQLite learning, content pipe, community fetch, weekly analytics, metrics cron, and faster daemon interval.
- Add publisher memory fixes, auto-reply, quality gate, self-reply, reply tracking cache, and visual brief support.
- Add Facebook Insights integration with real reach/impressions, track_performance after publish, and periodic refresh_metrics.

### Bug fixes

- Avoid Telegram Markdown parse_mode failures for triage digests.
- Fix weekly-report cron script to use deliver-weekly-report for Telegram delivery.
- Fix FB API deprecated error and missing metrics_csv in agent-tick.
- Fix publisher memory recording and settings .env auto-load.

### Documentation

- Document Hermes cron deployment.
- Update README with Phase 4/4b status, Insights, quality gate, self-reply, hook patterns, visual_brief, and refresh_metrics.

### Maintenance

- Reset test data for live testing and update Outfit Nha Gau calendars/history/comment inbox.
- Add gitignore coverage for egg-info and harden cron/Telegram/LLM fallbacks.

