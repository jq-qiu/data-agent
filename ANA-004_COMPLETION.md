# ANA-004 Completion Report

## Feature

ANA-004 Analysis Planner completed. The accepted Parsed Question and Capability Assessment now produce a deterministic, bounded, serializable plan with a Period Comparison gate and no SQL generation or execution.

## Changed Files

- `specs/ANA-004_analysis_planner.md`
- `app/diagnosis/__init__.py`
- `app/diagnosis/planner.py`
- `app/scripts/evaluate_analysis_planner_v1.py`
- `data/evaluation/analysis_planner_golden_v1.json`
- `data/reports/ANA-004_analysis_planner_evaluation.json`
- `test/diagnosis/test_analysis_planner.py`
- `ANA-004_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_analysis_planner.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_analysis_planner_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## Test Results

- ANA-004 targeted tests: 20 passed.
- Full regression: 144 passed.

## Lint Results

- Ruff reported 31 existing diagnostics.
- ANA-004 introduced no Ruff diagnostics and did not exceed the ANA-003 baseline of 31.

## Type Check Results

- mypy reported 36 existing errors in 11 files.
- ANA-004 introduced no mypy errors and did not exceed the ANA-003 baseline of 36 errors in 11 files.

## Evaluation Results

- Fixed cases: 10.
- Exact planning outcomes: 10/10.
- Plans within four-task limit: 10/10.
- Valid T1 dependency structures: 10/10.
- Parsed parameter reuse: 10/10.
- Unsupported method selections: 0.
- SQL fields emitted: 0.

## Acceptance Criteria

- Strict schemas reject unknown fields, more than four tasks, duplicate methods, non-consecutive IDs, invalid dependencies, and method-specific field misuse.
- Full capability yields the four frozen task classes in order; dimensions and factors are grouped and canonicalized.
- Partial capability omits only unavailable dimensions, factors, or methods and preserves stable missing-Evidence references.
- Missing Period capability and failed data quality return empty plans with distinct stable stop reasons.
- Planner tasks reuse the parsed Metric, periods, and Scope and never select unsupported or causal methods.
- Node output is JSON serializable and contains neither runtime dependencies nor SQL.
- Existing Parser, Capability Assessor, Query Graph, NL2SQL, Metadata configuration, data, database, and API were not changed.

## Known Issues

- Runtime construction of the request-scoped Data Capability Profile remains deferred.
- AnalysisTask execution and Controlled Query Builder are intentionally deferred to ANA-005.
- Repository-wide Ruff and mypy findings predate ANA-004 and remain at the accepted 31/36 baseline.
- SQL-002 accuracy limitations and the previously documented Qdrant compatibility warning remain unchanged.

## Diff Review Summary

- Diff is limited to the nine files allowed by the ANA-004 Spec.
- Planner is deterministic and bounded by schema and implementation; it has no retry or autonomous loop.
- No SQL, credential, connection string, raw Olist data, API key, password, token, or cookie was added.
- No database or external service was accessed by this Feature.
- `git diff --check` passed.
