# SQL-008 NL2SQL Metric/Calendar Real-Model Rerun

Rerun the frozen 30-case NL2SQL Golden Dataset after SQL-006 using the SQL-007
Live/Replay evaluator, while keeping all historical SQL-002 and SQL-005 artifacts immutable.

## In Scope

- Run all 30 Golden cases in Live mode against the configured isolated V1 services.
- Use frozen reference checksums and write a new SQL-008 report/run directory.
- Record the Live candidate runs to the Git-ignored local replay cache.
- Rerun from Replay without external services and verify the evaluation body is identical.
- Report real metrics, error categories, safety probes, and cache identity.
- Update current documentation and Completion Report.

## Out of Scope

- No Golden Dataset, prompt, Validator, SchemaLinkingPlan, Policy, or runtime code change.
- No remediation of failures found by this run; remediation requires SQL-009.
- No modification of SQL-002 or SQL-005 reports and run directories.
- No replay cache, credentials, connection data, or raw production results may be committed.

## Allowed Files

- `data/reports/SQL-008_nl2sql_metric_calendar_evaluation.json`
- `eval_runs/sql-008-metric-calendar-v1/**`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- This Spec and its Completion Report

## Commands

```powershell
.\.venv\Scripts\python.exe -m app.scripts.evaluate_nl2sql_v1 `
  --run-id sql-008-metric-calendar-v1 `
  --report data/reports/SQL-008_nl2sql_metric_calendar_evaluation.json `
  --run-dir eval_runs/sql-008-metric-calendar-v1 `
  --skip-reference --mode live `
  --replay-cache .tmp/sql-008-metric-calendar-v1.json
```

Then rerun to temporary report/run paths with `--mode replay` and compare the
evaluation, safety, gate, version, model, database, and cache digest fields.

## Acceptance

- All 30 cases and all six five-case buckets are recorded.
- Frozen reference checksums verify for all 30 cases.
- Dangerous SQL allowed count remains zero and every failure is classified.
- Live and Replay evaluation bodies are identical.
- Historical SQL-002/SQL-005 artifacts remain byte-identical in Git.
- Full pytest, Ruff, and mypy pass.
