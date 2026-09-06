# SQL-003 Completion Report

## Feature

SQL-003 Grouped TopN Query Support. The NL2SQL safety policy is versioned to `sql-policy-v1.1` and now permits a narrowly constrained grouped TopN shape: aggregate in a registered CTE, rank with `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)`, and filter rank position in an outer query with a stable identifier tie-break. `COUNT(*)` is distinguished from forbidden projection stars, CTE aliases resolve only to declared outputs, and Query Service emits a safe terminal error when the one allowed repair exhausts without a result.

## Changed Files

- `specs/SQL-003_grouped_topn_query_support.md`
- `conf/sql_policy.yaml`
- `app/nl2sql/validator.py`
- `app/services/query_service.py`
- `prompts/generate_sql.prompt`
- `prompts/correct_sql.prompt`
- `test/nl2sql/test_sql_validator.py`
- `test/nl2sql/test_grouped_topn.py`
- `test/api/test_query_api.py`
- `data/evaluation/grouped_topn_golden_v1.json`
- `app/scripts/evaluate_grouped_topn_v1.py`
- `data/reports/SQL-003_grouped_topn_evaluation.json`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `SQL-003_COMPLETION.md`

## Added Dependencies

None. SQL-003 uses the existing SQLGlot, Pydantic, SQLAlchemy, and Python standard library dependencies.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test\nl2sql\test_sql_validator.py test\nl2sql\test_grouped_topn.py test\api\test_query_api.py -q
.\.venv\Scripts\python.exe -m app.scripts.evaluate_grouped_topn_v1 --freeze-reference
.\.venv\Scripts\python.exe -m app.scripts.evaluate_grouped_topn_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

A read-only script also validated all 30 SQL-002 reference SQL statements and compared their declared table, column, and JOIN traces. It made no external model call.

## Test Results

- SQL-003 targeted suite: 49 passed, 0 failed in 7.96 seconds.
- Full backend regression: 283 passed, 0 failed in 13.24 seconds.
- Tests cover `COUNT(*)`/projection-star separation, CTE output aliasing, constrained window shapes, rejection of `RANK`/`DENSE_RANK`/`LAG`, one-repair terminal fallback, and the four-case Golden contract.

## Lint Results

- All SQL-003 implementation, evaluator, and test files pass targeted Ruff.
- Repository Ruff reports 22 existing diagnostics, unchanged from ROUTE-001.

## Type Check Results

- No mypy finding points to a SQL-003 implementation file.
- Repository mypy reports 36 existing errors in 11 files while checking 107 source files. The source-file count increased by the new evaluator module; the error count and affected-file count remain unchanged.

## Evaluation Results

- SQL-003 grouped TopN reference evaluation: 4/4 passed. Every reference passed Validator, EXPLAIN, controlled execution, frozen checksum, rank-sequence, per-group limit, and deterministic-order checks against `data_agent_v1_dw`.
- SQL-002 compatibility: 30/30 reference SQL statements still validate with identical table, column, and JOIN traces under `sql-policy-v1.1`.
- The reported `2018 年各州前三的销售额的商品` shape validates through GT01 semantics with V1 GMV and the accepted status exclusion.
- No external-model SQL-generation accuracy or latency was measured; grouped TopN result correctness is established only for the four frozen references.

## Acceptance Criteria

1. Passed: the logged grouped-TopN shape validates under `sql-policy-v1.1` with `row_number`, registered physical tables/columns/JOINs, and V1 GMV rules.
2. Passed: `COUNT(*)` validates while `SELECT *`, qualified projection stars, and stars outside plain `COUNT(*)` remain rejected.
3. Passed: CTE aliases may reference only declared output columns; unknown CTE output and physical alias/column/JOIN references remain rejected.
4. Passed: `ROW_NUMBER` requires OVER, PARTITION BY, and ORDER BY; `RANK`, `DENSE_RANK`, and `LAG` remain rejected.
5. Passed: generation and repair prompts require aggregate-then-rank, exact-N `ROW_NUMBER`, and a stable identifier tie-break.
6. Passed: one failed repair still stops, and Query Service emits exactly one safe `QUERY_VALIDATION_FAILED` terminal event when the graph ends without a result.
7. Passed: the Golden contains exactly four fixed cases and the evaluator persists only checksums, row/group counts, validation traces, and pass/fail facts.
8. Passed: all four references pass Validator, EXPLAIN, execution, checksum, per-group rank/limit, and deterministic-order checks against `data_agent_v1_dw`.
9. Passed: all 30 SQL-002 references still validate with identical declared traces and dangerous SQL allowed remains zero.
10. Passed: targeted/full pytest pass and Ruff/mypy remain at the accepted 22/36 baselines.
11. Passed: the diff is limited to the 15 allowed SQL-003 files and historical SQL-002 evidence remains unchanged.
12. Passed: intent routing, diagnosis logic, data, Metadata/indexes, frontend, original `dw`, and latency behavior remain unchanged.

## Known Issues

- Grouped TopN correctness is proven only for the four frozen references, not for arbitrary grouped analytical SQL.
- The runtime still requires the configured external model and services; SQL-003 does not improve the previously observed multi-minute LLM latency.
- Repository Ruff and mypy retain the documented 22/36 pre-existing baselines.

## Diff Review Summary

The change keeps strong safety rules first and limits window-function support to a single constrained grouped-TopN shape. `COUNT(*)` is allowed only as an aggregate argument, not as a projection wildcard. CTE output validation is scoped to the alias target declared by each CTE. Query Service adds a terminal fallback without changing graph topology or the one-repair rule. The evaluator persists no raw rows, credentials, connection details, or model payloads. Final review found no intent-router, diagnosis, data, Metadata/index, frontend, deployment, or historical SQL-002-report modification. Commit and push synchronization are verified separately after this report is committed.
