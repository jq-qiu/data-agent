# SQL-001 Completion Report

## Feature

SQL-001 NL2SQL Adaptation. The existing single-turn LangGraph query path now consumes the accepted Olist `metadata-v1` registry and enforces deterministic read-only, schema, JOIN, metric, grain, row-limit, timeout, and one-repair policies before any query reaches the isolated `data_agent_v1_dw` database. SQL-002 evaluation and diagnosis logic were not implemented.

## Changed Files

- `specs/SQL-001_nl2sql_adaptation.md`: frozen scope, safety policy, plan, commands, and acceptance criteria;
- `conf/sql_policy.yaml`, `app/nl2sql/**`: versioned SQL policy, AST validator, execution trace, and repair routing;
- `app/entities/**`, `app/mappers/**`: backward-compatible V1 metadata fields while preserving legacy mapper writes;
- `app/repositories/mysql/meta/meta_mysql_repository.py`: V1 table, column, metric, relationship, and shortest-path lookups;
- `app/repositories/qdrant/**`, `app/repositories/es/value_es_repository.py`: V1 metadata and canonical-value retrieval;
- `app/repositories/mysql/dw/dw_mysql_repository.py`: validated-query-only EXPLAIN/execution with timeout and row cap;
- `app/agent/**`, `app/services/query_service.py`, `app/api/dependencies.py`: V1 context injection, mandatory validation, revalidation after one repair, and controlled execution;
- `prompts/**`: registry-only formulas/JOINs, Olist examples, and explicit grain warnings;
- `test/nl2sql/**`: validator, routing, adapter, prompt, mapper, retrieval, and execution tests;
- `pyproject.toml`, `uv.lock`: SQL AST parser dependency;
- `IMPLEMENTATION_STATUS.md`, `SQL-001_COMPLETION.md`: status and completion evidence.

## Added Dependencies

- `sqlglot==28.10.1` (declared as `sqlglot>=27,<29`) for MySQL AST parsing and normalization.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/nl2sql
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

Additional read-only smoke checks used the V1 MySQL, Qdrant, Elasticsearch, embedding, and LLM services. Only validated SQL was explained and executed against `data_agent_v1_dw`; no credential or connection string was printed.

## Test Results

- SQL-001 targeted tests: 26 passed;
- full pytest regression: 68 passed in 5.55 seconds;
- real LangGraph smoke for `2018年5月GMV是多少` selected `dws_sales_region_daily`, passed validation and EXPLAIN, and returned one row with GMV 992,871.75;
- additional validated SQL smoke returned AOV 145.305393 for May 2018 and five category rows for the May 2018 Top 5 query;
- live value grounding resolved `圣保罗州` only to `dim_region.state_code = SP`;
- live relationship lookup resolved `fact_order` to `dim_region` through the registered order-customer and customer-region path.

## Lint Results

Ruff executed against the full repository and reported 31 existing diagnostics. The ENG-001 baseline was 51; SQL-001 introduced no new Ruff category or failure and reduced the count by removing diagnostics in directly touched files. Remaining diagnostics are disclosed and were not expanded into unrelated cleanup.

## Type Check Results

mypy executed against `app` and reported 36 errors in 11 files. The ENG-001 baseline was 40 errors in 14 files; the final SQL-001 implementation adds no error in the new `app/nl2sql` package or modified Agent nodes. Remaining errors are pre-existing client, configuration, legacy mapper/repository, and legacy metadata-service issues.

## Evaluation Results

SQL-002's formal 30-case NL2SQL evaluation was not run and Gate 3 is not claimed. SQL-001 performed real integration smoke only: three accepted analytical SQL shapes plus one complete LangGraph request succeeded on the isolated DW, and unsafe/static-policy cases were verified by unit tests.

## Acceptance Criteria

- PASS: runtime field, metric, and value recall uses the META-001 V1 MySQL/Qdrant/Elasticsearch targets;
- PASS: V1 tables, columns, metrics, formulas, status filters, allowed dimensions, relationships, and grain warnings enter structured Agent context;
- PASS: prompts forbid common-sense metric invention and unregistered JOINs;
- PASS: comments, variables, multi-statements, DML/DDL, system schemas, file access, dangerous functions, stars, unknown schema objects, unregistered JOINs, and sensitive identifier projection are rejected before EXPLAIN;
- PASS: DWD GMV status/formula rules, AOV component rules, category-order grain rules, and payment-item fanout protection are deterministic and tested;
- PASS: validation success is the only route to execution; one failed validation may repair once, and repaired SQL returns to the same validator;
- PASS: normalized SQL is capped at 500 rows and database validation/execution each have a 10-second timeout;
- PASS: real isolated-DW validation, EXPLAIN, execution, V1 retrieval, and full LangGraph smoke succeeded;
- PASS: all tests pass and Ruff/mypy are below their ENG-001 baselines;
- PASS: SQL-002 dataset/evaluation and all diagnosis features remain out of scope.

## Known Issues

- The formal SQL-002 30-case evaluation is intentionally not yet implemented, so no Execution Accuracy, Result Match Accuracy, Join Accuracy, Value Mapping Accuracy, or Repair Success Rate is claimed.
- Ruff retains 31 diagnostics and mypy retains 36 errors in 11 files from the documented engineering baseline. SQL-001 did not broaden scope to repair unrelated modules.
- Qdrant client 1.16.2 continues to report a compatibility warning against server 1.19.0; V1 retrieval succeeds in live smoke.

## Diff Review Summary

- scope review: only SQL-001 policy, runtime adaptation, validation, tests, report, dependency, and status files changed; formatter-only changes outside the allowed list were removed;
- execution review: generated and repaired SQL cannot reach the database without a fresh `ValidatedSQL` object; EXPLAIN and execution use the same normalized SQL;
- data safety review: all real smoke access was read-only and targeted only `data_agent_v1_dw`; the original `dw` database and accepted data/metadata builds were not modified;
- metric/grain review: registry GMV/AOV/category-order rules and unsafe item-payment fanout are enforced before database access;
- security review: the diff contains no API Key, password, Token, Cookie, or full connection string;
- whitespace review: `git diff --check` passed;
- downstream review: SQL-002 evaluation, QUERY/DIAGNOSIS routing, AnalysisTask, Controlled Query Builder, Analyzer, AOV decomposition, and diagnosis reporting were not implemented.
