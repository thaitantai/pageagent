# Ops Status

## Purpose

Check whether the main cron/audit artifacts exist and expose their latest JSON summaries without opening each artifact manually.

## Command

```bash
python3 -m fanpage_agent.main ops-status
```

Fail CI/watchdog when any existing artifact is older than its lane threshold:

```bash
python3 -m fanpage_agent.main ops-status --fail-on-stale
```

Override a lane threshold for one run:

```bash
python3 -m fanpage_agent.main ops-status --max-age-hours operator_digest=24,weekly_report=192
```

## Checks

- latest `artifacts/ops/daily-ops-*.json`
- `artifacts/ops/operator-digest.json`
- `artifacts/approvals/approval-audit.json`
- `artifacts/reports/weekly-report.json`
- `artifacts/research/research-brief.json`
- latest `artifacts/evals/eval-summary-*.json`

Freshness thresholds:

- `daily_ops_latest`: 30 hours
- `operator_digest`: 30 hours
- `approval_audit`: 30 hours
- `weekly_report`: 192 hours
- `research_brief`: 30 hours
- `eval_latest`: 30 hours

## Output shape

```json
{
  "artifacts_dir": "artifacts",
  "summary": {
    "existing": 5,
    "missing": 0,
    "fresh": 5,
    "stale": 0
  },
  "artifacts": [
    {
      "name": "operator_digest",
      "path": "artifacts/ops/operator-digest.json",
      "exists": true,
      "freshness": {
        "max_age_hours": 30.0,
        "age_hours": 1.25,
        "stale": false
      },
      "json_valid": true,
      "summary": {}
    }
  ]
}
```

## Verify

```bash
python3 -m unittest tests.test_ops_status_cli -v
python3 -m fanpage_agent.main ops-status
python3 -m fanpage_agent.main ops-status --fail-on-stale
```
