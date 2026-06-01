# Ops Status

## Purpose

Check whether the main cron/audit artifacts exist and expose their latest JSON summaries without opening each artifact manually.

## Command

```bash
python3 -m fanpage_agent.main ops-status
```

## Checks

- latest `artifacts/ops/daily-ops-*.json`
- `artifacts/ops/operator-digest.json`
- `artifacts/reports/weekly-report.json`
- `artifacts/research/research-brief.json`
- latest `artifacts/evals/eval-summary-*.json`

## Output shape

```json
{
  "artifacts_dir": "artifacts",
  "summary": {
    "existing": 5,
    "missing": 0
  },
  "artifacts": [
    {
      "name": "operator_digest",
      "path": "artifacts/ops/operator-digest.json",
      "exists": true,
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
```
