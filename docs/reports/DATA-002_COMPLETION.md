# DATA-002 Completion Report

## Feature

DATA-002 DWD and Diagnosis DWS.

The isolated `data_agent_v1_dw` database now contains normalized Olist DWD dimensions/facts and the two diagnosis DWS tables at their frozen grains. This completes DATA-002 only; Gate 1 remains in progress until DATA-003 supplies reproducible Synthetic Evidence and Ground Truth.

## Changed Files

- `specs/DATA-002_dwd_dws.md`: freezes exact scope, grains, metric rules, safety constraints, and acceptance checks.
- `app/data_foundation/__init__.py`: declares the deterministic data-foundation package.
- `app/data_foundation/olist.py`: defines DWD/DWS schemas, deterministic ETL, idempotent build audit, and reconciliation queries.
- `app/scripts/build_data_foundation.py`: provides the controlled build command and sanitized JSON report.
- `test/data/test_data_foundation.py`: tests table grains, ratio exclusion, one-to-many inflation protection, order-count semantics, logical foreign keys, and idempotency.
- `data/reports/DATA-002_data_foundation.json`: records the successful real build and full reconciliation result.
- `IMPLEMENTATION_STATUS.md`: records DATA-002 completion and the DATA-003 resume point.
- `DATA-002_COMPLETION.md`: records this completion evidence.

The ignored local configuration continues to select `data_agent_v1_dw`. No credential, full connection string, Olist raw file, or local database artifact is included.

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/data/test_data_foundation.py
.\.venv\Scripts\python.exe -m app.scripts.build_data_foundation
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check app/data_foundation app/scripts/build_data_foundation.py test/data/test_data_foundation.py
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

The real build command was run twice. Independent read-only SQL then rechecked fact counts, both DWS grains, three GMV totals, valid overall Order Count, and the deliberately unsafe payment-item Join result.

The first real DDL attempt failed safely with MySQL code 1142 because the least-privilege account lacks `REFERENCES`. Physical foreign keys were replaced with a fixed seven-relation logical-key registry and mandatory zero-orphan checks. The next attempt failed safely because the account also lacks `DELETE`; the builder was tightened to require empty targets on first build and to refuse automatic overwrite thereafter. No privilege expansion or destructive cleanup was required. An intermediate controlled test then exposed two implicit SQLAlchemy joins that had depended on physical FK metadata; both were changed to explicit join predicates before the successful build.

## Test Results

- DATA-002专项测试：3 passed in 1.02 seconds.
- Full pytest regression: 31 passed in 2.17 seconds.
- Real MySQL first accepted build: success, not reused.
- Real MySQL second accepted build: success, reused the same batch.
- Independent target reconciliation: passed.

## Lint Results

- New DATA-002 Python files: all targeted Ruff checks passed.
- Full repository Ruff result: 51 existing diagnostics.
- ENG-001 Ruff baseline: 51 diagnostics.
- Baseline delta: 0.

## Type Check Results

- Full mypy result: 40 existing errors in 14 files; 64 source files checked.
- ENG-001 mypy baseline: 40 errors in 14 files.
- Baseline delta: 0.
- Targeted mypy reaches one pre-existing `app/conf/app_config.py` error through the command wrapper; the new foundation module adds no diagnostic.

## Evaluation Results

未评测。DATA-002 has no model evaluation suite. Its deterministic Gate evidence is reported under Acceptance Criteria; complete Gate 1 evaluation is deferred until DATA-003 exists.

## Acceptance Criteria

- [x] Six dimension tables and five fact tables use the frozen primary-key grains.
- [x] All seven declared logical foreign-key orphan counts are 0.
- [x] Fact rows equal ODS rows: 99,441 orders; 112,650 items; 103,886 payments; 99,441 deliveries; 99,224 reviews.
- [x] `dim_date` contains 774 contiguous dates across the Olist purchase-date range.
- [x] `dws_sales_region_daily` contains 10,689 unique date-state rows.
- [x] `dws_sales_category_daily` contains 56,665 unique date-state-category rows.
- [x] Valid-order DWD GMV, region DWS GMV, and category DWS GMV each equal 13,494,400.74.
- [x] GMV uses item price, excludes freight, and does not use payment value.
- [x] The region DWS Order Count sum equals 98,207 valid orders.
- [x] Category Order Count sums to 99,002 and is explicitly not used as overall Order Count.
- [x] The unsafe payment-item Join inflates GMV to 14,105,767.00 and is detected; accepted DWS totals remain correct.
- [x] No ratio column is persisted; all DATA-003 Synthetic base columns and `synthetic_version` are `NULL`.
- [x] The second real run reused the same accepted batch without duplicate rows.
- [x] DATA-002专项 tests and full pytest pass.
- [x] Ruff and mypy do not exceed the ENG-001 baselines.
- [x] No DATA-003, Metadata, NL2SQL, LangGraph, Analyzer, or API behavior was implemented.
- [x] DATA-002 is isolated to one commit and push.

## Known Issues

- MySQL physical foreign-key constraints are absent because the least-privilege DW account does not have `REFERENCES`. The build fails unless all seven logical relationship orphan counts are zero.
- The accepted builder never automatically deletes or overwrites DWD/DWS data. A corrupted accepted build requires explicit operator remediation rather than silent repair.
- The repository retains the documented Ruff baseline of 51 diagnostics.
- The repository retains the documented mypy baseline of 40 errors in 14 files.

## Diff Review Summary

The change set is limited to DATA-002 schemas, deterministic ETL/reconciliation, its command wrapper, controlled tests, a sanitized report, the Feature Spec, persistent status, and this report. ODS and DWD source values remain untouched by Synthetic logic; all Synthetic columns remain `NULL`. No AOV implementation, Metric Registry, Metadata, NL2SQL, LangGraph, diagnosis, or API business logic changed. The original `dw` database was not written. Raw data, local configuration, secrets, and connection strings remain excluded from Git.
