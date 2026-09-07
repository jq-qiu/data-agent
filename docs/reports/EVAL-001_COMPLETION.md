# EVAL-001 Completion Report

## Feature

EVAL-001 Diagnosis Regression completed as a real, read-only baseline against
the isolated `data_agent_v1_dw` Synthetic Evidence tables. The evaluator runs
the frozen Intent, Parser, Capability, Planner, Controlled Query, Analyzer,
Evidence, and Report chain and records deterministic metrics and one primary
error category per failed case. Gate 5 did not pass; no upstream diagnosis
algorithm was changed to fit the Ground Truth labels.

## Changed Files

- `specs/EVAL-001_diagnosis_regression.md`
- `app/evaluation/__init__.py`
- `app/evaluation/diagnosis.py`
- `app/scripts/evaluate_diagnosis_v1.py`
- `data/evaluation/diagnosis_golden_v1.json`
- `data/reports/EVAL-001_diagnosis_regression.json`
- `eval_runs/EVAL-001_v1/summary.json`
- `eval_runs/EVAL-001_v1/diagnosis_results.csv`
- `eval_runs/EVAL-001_v1/error_analysis.md`
- `test/evaluation/test_diagnosis_regression.py`
- `EVAL-001_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m py_compile app/evaluation/diagnosis.py app/scripts/evaluate_diagnosis_v1.py
.\.venv\Scripts\python.exe -m pytest test/evaluation/test_diagnosis_regression.py -q
.\.venv\Scripts\ruff.exe check app/evaluation app/scripts/evaluate_diagnosis_v1.py test/evaluation/test_diagnosis_regression.py
.\.venv\Scripts\mypy.exe app/evaluation app/scripts/evaluate_diagnosis_v1.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_diagnosis_v1
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## Test Results

- EVAL-001 targeted tests: 9 passed.
- Full regression: 218 passed.

## Lint Results

- All EVAL-001 implementation, runner, and test files pass targeted Ruff.
- Repository-wide Ruff reports 31 existing diagnostics, unchanged from the
  accepted ANA-007 baseline.

## Type Check Results

- The pure EVAL-001 scoring module introduces no targeted mypy finding.
- Targeting the live runner also reaches three accepted errors in
  `app/conf/app_config.py` and `app/repositories/mysql/dw/dw_mysql_repository.py`.
- Repository-wide mypy reports 36 existing errors in 11 files, unchanged from
  the accepted ANA-007 baseline.

## Evaluation Results

- Cases attempted: 10; complete successful chains: 4/10 (D01, D05, D07, D09).
- Single Cause Hit@1: 2/6.
- Root Cause Recall@3: 4/10.
- Evidence Precision: 4/4; Evidence Recall: 4/10.
- Numeric Consistency: 4/10.
- Maximum reconciliation error among completed results: 0.000000.
- Unsupported Claim Count: 0.
- Causal-language Violation Count: 0.
- D09 no-decline correctness: 1/1.
- D10 correct degradation: 0/1 because its Scope failed before degradation.
- Errors: 5 Schema Linking and 1 Evidence Validation; all other frozen error
  categories are zero.
- Latency: mean 368.935100 ms, median 293.217500 ms, maximum 1103.221000 ms.
- Token usage and cost: unavailable because the controlled run made no LLM call.
- Gate 5: failed.

These are functional-regression numerators and denominators, not production
accuracy or generalization claims.

## Acceptance Criteria

- The versioned D01-D10 Golden Dataset and scoring denominators are frozen.
- Every case entered the real isolated-DW component chain; no mock query result
  or hard-coded Gate result was used.
- All persisted artifacts exclude raw SQL, row payloads, bind parameters,
  credentials, connection details, and Ground Truth database rows.
- Every failed case has one primary frozen error category and appears in the
  row-level result and error analysis.
- Numeric, Evidence, unsupported-claim, causal-language, no-decline, and
  degradation metrics are derived from actual per-case observations.
- The runner asserts the database name is exactly `data_agent_v1_dw` and only
  issues controlled read-only queries.
- No diagnosis threshold, query, Analyzer formula, Evidence rule, report wording,
  Graph, API, NL2SQL, or business logic was modified.
- Full pytest passes and Ruff/mypy remain at the accepted 31/36 baselines.
- Gate 5 outcome is false and is reported without inflating the score.

## Known Issues

- D03, D04, D06, D08, and D10 use Synthetic Scope values that are not registered
  in the current Metadata Catalog value vocabulary, so exact Scope grounding
  stops with Schema Linking Error.
- D02 reaches Evidence validation but Category-scope decomposition carries
  `gmv` and `category_order_count` lineage while the frozen decomposition
  Evidence contract requires `gmv`, `order_count`, and `aov` lineage.
- Gate 5 is not satisfied, so API-001 must not start under the implementation
  plan's prerequisite rules. Remediation belongs in a separately scoped upstream
  Feature; it is not authorized inside EVAL-001.
- SQL-002 accuracy limitations, the Qdrant compatibility warning, and the
  repository-wide 31 Ruff/36 mypy baseline remain unchanged.

## Diff Review Summary

- Diff is limited to the twelve files allowed by the EVAL-001 Spec.
- The evaluator reads Ground Truth only inside the evaluation boundary for
  expected labels and Synthetic case selection; application runtime does not
  gain Ground Truth access.
- The live run is fail-closed: stage exceptions become typed observations and do
  not silently count as successful or numerically consistent.
- Generated JSON/CSV/Markdown artifacts contain only safe case-level metrics,
  status, latency, lineage-derived checks, and controlled error classification.
- No API key, password, token, cookie, credentialed URL, raw Olist row, SQL text,
  bind value, or original `dw` operation was added.
