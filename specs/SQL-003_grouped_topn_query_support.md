# SQL-003 Grouped TopN Query Support

## 1. Feature

Make grouped TopN open-data questions pass the existing NL2SQL safety boundary,
execute read-only against the isolated Olist warehouse, and always terminate the
public SSE stream explicitly when the one allowed SQL repair is exhausted.

For wording such as `2018 年各州前三的销售额的商品`, SQL-003 freezes the
result semantics as at most three products per customer state, ordered by V1
GMV descending and then `product_id` ascending as the deterministic tie-break.
Groups with fewer than three available products return all available products.

## 2. Source of Truth

1. The user's authorization and accepted exact-N/tie-break design in the current
   task.
2. This specification.
3. `IMPLEMENTATION_PLAN.md`.
4. `docs/01_product_scope.md`, `docs/02_data_and_metric_design.md`,
   `docs/03_metadata_and_nl2sql.md`, and `docs/06_evaluation.md`.
5. `AGENTS.md` and `README.md`.
6. `specs/SQL-001_nl2sql_adaptation.md`, `SQL-001_COMPLETION.md`,
   `specs/SQL-002_nl2sql_evaluation.md`, and `SQL-002_COMPLETION.md`.
7. `specs/ROUTE-001_hybrid_intent_router.md` and
   `ROUTE-001_COMPLETION.md`.
8. Current SQL Policy, AST Validator, prompts, query graph, Query Service,
   isolated Metadata, and regression behavior.

Historical SQL-002 Golden data, reports, and run artifacts remain immutable.

## 3. Prerequisite Findings

- ROUTE-001 is complete at commit `c753bd1`; local `main` and `origin/main`
  match and the worktree is clean.
- The reported question now routes deterministically to QUERY.
- The generated MySQL 8 SQL used the appropriate grouped-ranking shape:
  aggregate in a CTE, apply `ROW_NUMBER() OVER (PARTITION BY ...)`, and filter
  rank at three.
- Validation failed because `row_number` is absent from the function allowlist.
- The only repair replaced the window function with a correlated `COUNT(*)`.
  The Validator currently treats the `Star` inside `COUNT(*)` as forbidden
  `SELECT *`, and it also rejects aliases of registered CTE outputs.
- After the second validation failure, the one-repair graph ends without a
  result event. Query Service currently emits no replacement terminal event,
  so the frontend reports a missing terminal event.
- The failed request never reached EXPLAIN or SQL execution. Its approximately
  eight-minute duration is dominated by external model calls; latency
  optimization is a separate Feature.
- A later rerun showed the external model also emits `YEAR(purchase_date)`, which
  SQLGlot parses as `Year(TsOrDsToDate(...))`; the inner `ts_or_ds_to_date` node
  was incorrectly rejected despite `year` being allowlisted.
- A rerun also showed the repair can use a derived table `FROM (...) t` with
  qualified output columns. Derived-table aliases were not registered, so
  `t.state` was rejected as `unknown table alias: t`. Successful runs avoided
  both variants, which is why behavior appeared intermittent.

## 4. In Scope

- Version the SQL Policy from `sql-policy-v1` to `sql-policy-v1.1`.
- Add only `ROW_NUMBER` to the allowed function set for grouped TopN.
- Require every `ROW_NUMBER` node to be used through an `OVER` window with both
  `PARTITION BY` and `ORDER BY`.
- Permit the exact aggregate wildcard form `COUNT(*)` while continuing to
  reject `SELECT *`, qualified projection stars, and every other star context.
- Resolve aliases of known CTEs and derived tables (`FROM (...) t`) to their
  declared output columns, while rejecting unknown output columns and preserving
  physical table/column registration checks.
- Allow the SQLGlot internal `ts_or_ds_to_date` node only when it is the argument
  of an allowlisted time-component function such as `YEAR`, `MONTH`, `DAY`, or
  `QUARTER`.
- Update SQL generation and repair prompts with the accepted grouped TopN
  pattern, `ROW_NUMBER` restriction, exact-N behavior, and stable identifier
  tie-break.
- Preserve GMV as `SUM(fact_order_item.price)`, the canceled/unavailable status
  exclusion, registered JOINs, sensitive-column protection, row cap, timeout,
  and isolated database restriction.
- Make Query Service emit one safe `QUERY_VALIDATION_FAILED` SSE terminal error
  if the NL2SQL graph finishes without a result after validation/repair.
- Add AST, safety, CTE, window-shape, API terminal, and regression tests.
- Add a new four-case grouped TopN Golden and deterministic read-only evaluator;
  record only checksums, row/group counts, validation traces, and pass/fail facts.
- Execute the frozen reference queries through Validator, EXPLAIN, and the
  repository against `data_agent_v1_dw`.
- Update README, implementation status, and the SQL-003 completion report.

## 5. Out of Scope

- No ROUTE-001 or diagnosis intent change.
- No retrieval TopK, Metadata content/index, database schema, ETL, DWS, metric
  formula, AOV, AnalysisTask, Analyzer, Evidence, or diagnosis-report change.
- No `RANK`, `DENSE_RANK`, `LAG`, `LEAD`, arbitrary analytic function, recursive
  CTE, unlimited query, or multi-statement support.
- No promise that all comparisons, shares, medians, or arbitrary nested SQL are
  correct; SQL-003 evaluates only its frozen grouped TopN set.
- No additional repair attempt and no change to the one-repair graph topology.
- No external-model latency optimization, cache, concurrency redesign, model
  replacement, or frontend change.
- No rewrite of the SQL-002 Golden, baseline report, or run artifacts.
- No write query, DDL, data mutation, index rebuild, original `dw` access, or
  persisted real user/model payload.

## 6. Grouped TopN Contract

The preferred MySQL 8 shape is:

```text
registered aggregation CTE
  → ROW_NUMBER OVER (
      PARTITION BY registered group dimension
      ORDER BY registered metric DESC, stable registered identifier ASC
    )
  → outer filter rank_position <= N
  → deterministic group/rank ordering
```

`ROW_NUMBER`, not `RANK` or `DENSE_RANK`, freezes at most N rows per group.
The final product value is `product_id` because Metadata contains no product
name field. The Validator proves safety/schema compliance; the frozen evaluator
proves result shape and checksum for the reference queries.

## 7. Allowed Files

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

Any additional file requires a documented direct blocker and must remain inside
SQL-003.

## 8. Local Plan

1. Freeze grouped TopN SQL, malformed CTE/window/star probes, and exhausted-
   repair terminal behavior in tests and the four-case Golden.
2. Make the smallest AST-aware Validator changes for `COUNT(*)`, CTE aliases,
   and constrained `ROW_NUMBER`.
3. Add the grouped TopN contract to generation and correction prompts.
4. Add the safe Query Service terminal fallback without changing graph topology.
5. Run targeted tests, all historical NL2SQL references, the new read-only
   isolated-DW evaluator, and the reported-query validation/execution smoke.
6. Run full pytest, Ruff, mypy, documentation, secret, scope, and Diff Review.
7. Complete the report, create one SQL-003 commit, push it, and stop before
   latency or any other Feature.

## 9. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test\nl2sql\test_sql_validator.py test\nl2sql\test_grouped_topn.py test\api\test_query_api.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_grouped_topn_v1 --freeze-reference
.\.venv\Scripts\python.exe -m app.scripts.evaluate_grouped_topn_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

Real evaluation must use only validated read-only SQL against
`data_agent_v1_dw`. No connection detail or result row is written to Git or
completion output.

## 10. Acceptance Criteria

1. The logged first grouped-TopN SQL validates under `sql-policy-v1.1` with
   `row_number`, registered physical tables/columns/JOINs, and V1 GMV rules.
2. `COUNT(*)` validates, while `SELECT *`, qualified projection stars, and stars
   outside plain `COUNT(*)` remain rejected.
3. A CTE alias may expose only declared CTE output columns; unknown output,
   physical table, column, and JOIN references remain rejected.
4. `ROW_NUMBER` requires `OVER`, `PARTITION BY`, and `ORDER BY`; `RANK`,
   `DENSE_RANK`, and other unregistered functions remain rejected.
5. Prompts require aggregate-then-rank, exact-N `ROW_NUMBER`, and a stable
   identifier tie-break without inventing names, formulas, fields, or JOINs.
6. One failed repair still stops; Query Service emits exactly one safe terminal
   `QUERY_VALIDATION_FAILED` event when the graph ends without a result.
7. The new Golden contains exactly four fixed cases and its evaluator persists
   no raw rows, credentials, connection details, user logs, or model output.
8. All four references pass Validator, EXPLAIN, execution, checksum, per-group
   rank/limit, and deterministic-order checks against `data_agent_v1_dw`.
9. The existing 30 SQL-002 references still validate with identical declared
   table/column/JOIN traces, and dangerous SQL allowed remains zero.
10. Targeted/full pytest pass and Ruff/mypy do not regress the accepted 22/36
    baselines.
11. The diff is limited to the 15 allowed SQL-003 files and historical SQL-002
    evidence remains unchanged.
12. Intent routing, diagnosis logic, data, Metadata/indexes, frontend, original
    `dw`, and latency behavior remain unchanged.

## 11. Completion Boundary

After the SQL-003 completion report, independent commit, and push, stop. Any
model-latency optimization or broader analytical SQL improvement requires a new
Feature and explicit authorization.
