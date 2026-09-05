# EVAL-001 Diagnosis Regression

## 1. Feature

Run and record the first complete D01-D10 functional regression of the frozen
V1 diagnosis component chain against the isolated Synthetic Evidence tables in
`data_agent_v1_dw`.

## 2. Source of Truth

1. Current user authorization and safety constraints.
2. This specification.
3. `IMPLEMENTATION_PLAN.md`.
4. `docs/01_product_scope.md`.
5. `docs/02_data_and_metric_design.md`.
6. `docs/04_analysis_methodology.md`.
7. `docs/05_agent_workflow.md`.
8. `docs/06_evaluation.md`.
9. `data/config/synthetic_v1.json` and accepted DATA-003 artifacts.
10. Accepted ANA-001 through ANA-007 contracts.

## 3. In Scope

- A versioned D01-D10 Diagnosis Golden Dataset with questions, Scope, expected
  outcome, expected candidate factors, and degradation requirements.
- A pure deterministic scoring module with the frozen metric denominators and
  Gate 5 rules.
- A live read-only evaluation runner covering Intent, Parser, Capability,
  Planner, Controlled Query execution, Analyzer, Evidence, and Report stages.
- Real per-case results, latency, numeric reconciliation, unsupported-claim,
  causal-language, and degradation checks.
- Versioned summary, row-level results, and error analysis artifacts.
- Unit tests for scoring, denominators, failure classification, and Gate logic.

## 4. Out of Scope

- Changing any diagnosis algorithm, threshold, prompt, query, Analyzer formula,
  Evidence rule, or report wording to fit Ground Truth labels.
- Runtime Ground Truth access outside this evaluation runner.
- NL2SQL re-evaluation, API/Graph wiring, UI/demo work, model calls, database
  writes, DDL, data regeneration, or changes to the original `dw` database.
- Production generalization claims; D01-D10 are a functional regression only.
- API-001 and later work.

## 5. Allowed Files

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

## 6. Frozen Dataset

- D01-D02: Traffic Drop.
- D03-D04: Promotion End.
- D05-D06: Stockout.
- D07: Traffic + Promotion.
- D08: Traffic + Stockout.
- D09: no confirmed decline/no clear Evidence.
- D10: confirmed decline with Visitors missing; must degrade with no supported
  candidate conclusion.

Region-only cases request Region contribution. Category-scoped cases request
Region and Category contributions. Every case requests Traffic, Promotion, and
Inventory validation; Capability Assessment must remove unavailable methods.

## 7. Live Evaluation Boundary

- Assert the configured target database name is exactly `data_agent_v1_dw`.
- Use `QueryDataSource.SYNTHETIC_CASE` and the case's bound D01-D10 identifier.
- Every SQL statement must pass the shared Validator and Repository EXPLAIN
  before read-only execution.
- Do not print or persist raw SQL, parameters, connection details, credentials,
  full query rows, or source business values.
- Golden artifacts contain only versioned synthetic inputs/labels, never
  credentials or production results.

## 8. Metrics

All ratios report numerator and denominator, plus a decimal value when the
denominator is non-zero.

- Single Cause Hit@1: correct first candidate across D01-D06 (denominator 6).
- Root Cause Recall@3: matched Ground Truth factor labels across the ten cause
  labels in D01-D08 (denominator 10).
- Evidence Precision: matched supported candidate Evidence divided by all
  supported candidate Evidence emitted.
- Evidence Recall: matched supported candidates divided by all Ground Truth
  factor labels.
- Numeric Consistency: cases whose report validation, lineage checks, and all
  applicable Shapley/Dimension reconciliations pass (denominator 10).
- Contribution Reconciliation Error: maximum absolute recorded reconciliation
  difference.
- Unsupported Claim Count: report conclusions referencing unsupported Evidence.
- Correct Degradation: D10 returns `DEGRADED`, no ranked candidate, and exposes
  missing Visitors Evidence (denominator 1).
- No-decline correctness: D09 returns `NO_DECLINE` and no candidate ranking.
- Causal-language Violation Count: occurrences of the frozen forbidden phrases.

Latency is recorded per case and summarized by mean, median, and maximum.
Token/cost are `unavailable` because this controlled evaluation performs no LLM
calls. Every failed case receives exactly one primary error category from the
frozen taxonomy.

## 9. Gate 5

Pass only when:

- all 10 cases execute;
- Numeric Consistency is 10/10;
- Unsupported Claim Count is 0;
- Causal-language Violation Count is 0;
- D10 Correct Degradation is 1/1;
- Root Cause Recall@3 is at least 8/10.

All other metrics are reported honestly without inventing a target.

## 10. Acceptance Criteria

1. D01-D10 run through the real isolated-DW controlled chain.
2. Results contain no raw SQL, row payload, parameters, credentials, or
   connection details.
3. Metric numerators/denominators follow the frozen definitions.
4. Numeric/report lineage is checked case by case.
5. D09 and D10 boundary behavior is explicitly evaluated.
6. Every failure has one primary error category and is present in error
   analysis.
7. Gate 5 outcome is derived from real results and not hard-coded.
8. Full pytest passes and Ruff/mypy do not regress their accepted baselines.
9. Diff is limited to allowed EVAL-001 files.

## 11. Validation Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/evaluation/test_diagnosis_regression.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_diagnosis_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
```
