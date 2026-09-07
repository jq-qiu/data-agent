# ANA-005 Completion Report

## Feature

ANA-005 Analysis Task Executor and Controlled Query Builder completed. Accepted Analysis Plans now map to at most five Registry-checked, parameterized, read-only queries, each of which passes the shared SQL Validator and Repository EXPLAIN before execution. Outputs contain structured rows and traceable lineage without raw SQL or bound values. ANA-006 mathematics were not implemented.

## Changed Files

- `specs/ANA-005_controlled_query_builder.md`
- `app/diagnosis/__init__.py`
- `app/diagnosis/query.py`
- `app/nl2sql/validator.py`
- `app/repositories/mysql/dw/dw_mysql_repository.py`
- `app/scripts/evaluate_analysis_task_executor_v1.py`
- `data/evaluation/analysis_task_executor_golden_v1.json`
- `data/reports/ANA-005_analysis_task_executor_evaluation.json`
- `test/diagnosis/test_analysis_task_executor.py`
- `ANA-005_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_analysis_task_executor.py
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_analysis_task_executor.py test/nl2sql/test_sql_validator.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_analysis_task_executor_v1
.\.venv\Scripts\python.exe -m app.scripts.evaluate_analysis_task_executor_v1 --live
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## Test Results

- ANA-005 targeted tests: 17 passed.
- ANA-005 plus shared SQL Validator regression: 37 passed.
- Full regression: 161 passed.

## Lint Results

- Ruff reported 31 existing diagnostics.
- ANA-005 introduced no Ruff diagnostics and did not exceed the ANA-004 baseline of 31.

## Type Check Results

- mypy reported 36 existing errors in 11 files.
- ANA-005 introduced no mypy errors and did not exceed the ANA-004 baseline of 36 errors in 11 files.

## Evaluation Results

- Fixed query-contract cases: 8.
- Exact Query Role/table/count outcomes: 8/8.
- Bound-parameter checks: 8/8.
- Trace safety checks: 8/8.
- Consecutive Query ID checks: 8/8.
- Validate/EXPLAIN/Execute order checks: 8/8.
- Five-query hard-limit checks: 8/8.
- Real isolated-DW Smoke: 5/5 queries validated, explained, executed, and returned rows against Synthetic Case D02 in `data_agent_v1_dw`.
- Live report contains only Query IDs, roles, row counts, fingerprints, table names, and pass state; it contains no raw SQL, bound values, credentials, or business result values.

## Acceptance Criteria

- Builder construction rejects any missing frozen table, column, Metric ID, or Metric version.
- The complete four-task plan generates exactly five physical queries in fixed order and cannot exceed the hard limit.
- Dates, Region, Category, and Case ID are named parameters and are never interpolated into builder SQL.
- Every query passes the shared read-only/Schema/function/grain/row-limit policy and Repository EXPLAIN before execution.
- SQL validation failure reaches neither EXPLAIN nor Execute; result shape mismatch is rejected before State output.
- Results contain consecutive Query IDs, SHA-256 fingerprints, Catalog/Metric/Policy versions, validation trace, and structured rows.
- Overall/Region decomposition uses only Region DWS Order Count; Category Order Count is selected only under one Category Scope.
- Candidate queries return additive numerators and denominators and perform no ratio mathematics.
- Synthetic source requires a bound Case ID; Warehouse source forbids it.
- Node output contains no raw SQL, parameter map, Client, Repository, or Registry.
- Real Smoke accessed only `data_agent_v1_dw` using validated read-only SELECT queries; no write SQL or original `dw` access occurred.
- Existing diagnosis planning, NL2SQL Graph, Metadata/Metric configuration, DWS data, and API were not modified.

## Known Issues

- Runtime wiring into the diagnosis Graph is intentionally deferred until downstream Analyzer and Evidence stages exist.
- ANA-005 returns additive query inputs; all financial math, contribution logic, and anomaly decisions are intentionally deferred to ANA-006.
- The shared SQL Validator required a narrow AST fix so boolean `AND` is not treated as a callable function; its function allowlist and all other safety rules remain unchanged.
- Repository-wide Ruff and mypy findings predate ANA-005 and remain at the accepted 31/36 baseline.
- SQL-002 accuracy limitations and the previously documented Qdrant compatibility warning remain unchanged.

## Diff Review Summary

- Diff is limited to the eleven files allowed by the amended ANA-005 Spec.
- Existing DW Repository signatures remain backward compatible; only optional named parameters were added.
- The only SQL Validator change excludes boolean connector AST nodes from callable-function checking; SQL safety and function allowlists were not relaxed.
- Controlled queries contain only fixed table/column identifiers and named bindings; no LLM or arbitrary SQL path exists.
- No API key, password, token, cookie, credentialed connection string, raw Olist data, or local sensitive configuration was added.
- `git diff --check` passed.
