# ANA-006 Completion Report

## Feature

ANA-006 Deterministic Analyzer completed. Validated query results now produce
strict numeric outputs for period comparison, GMV Shapley decomposition,
Region/Category GMV contribution, and requested Traffic/Promotion/Inventory
factor changes. The Feature performs no LLM reasoning, Evidence judgment,
business conclusion, report generation, Graph wiring, or database access.

## Changed Files

- `specs/ANA-006_deterministic_analyzer.md`
- `app/diagnosis/__init__.py`
- `app/diagnosis/analyzer.py`
- `app/scripts/evaluate_deterministic_analyzer_v1.py`
- `data/evaluation/deterministic_analyzer_golden_v1.json`
- `data/reports/ANA-006_deterministic_analyzer_evaluation.json`
- `test/diagnosis/test_deterministic_analyzer.py`
- `ANA-006_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_deterministic_analyzer.py -q
.\.venv\Scripts\python.exe -m app.scripts.evaluate_deterministic_analyzer_v1
.\.venv\Scripts\ruff.exe check app/diagnosis/analyzer.py app/diagnosis/__init__.py app/scripts/evaluate_deterministic_analyzer_v1.py test/diagnosis/test_deterministic_analyzer.py
.\.venv\Scripts\mypy.exe app/diagnosis/analyzer.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## Test Results

- ANA-006 targeted tests: 22 passed.
- Full regression: 183 passed.

## Lint Results

- All ANA-006 implementation, evaluation, and test files pass targeted Ruff.
- Repository-wide Ruff reports 31 existing diagnostics, unchanged from the
  accepted ANA-005 baseline.

## Type Check Results

- `app/diagnosis/analyzer.py` passes targeted mypy.
- Repository-wide mypy reports 36 existing errors in 11 files, unchanged from
  the accepted ANA-005 baseline.

## Evaluation Results

- Fixed numeric scenarios: 10.
- Exact expected numeric/degradation outcomes: 10/10.
- Consecutive Analysis Result ID checks: 10/10.
- Complete Metric lineage checks: 10/10.
- Five-result hard-limit checks: 10/10.
- Safe serialized-output checks: 10/10.
- Evaluated cases cover period decline, zero baseline, Shapley reconciliation,
  zero-order degradation, opposing dimension effects, appearing/disappearing
  members, incomplete dimensions, near-zero totals, all three candidate
  factors, and missing ratio denominators.

## Acceptance Criteria

- Period delta and change rate use deterministic Decimal arithmetic; a zero
  baseline returns a null rate and stable warning.
- GMV Shapley contributions use the frozen two-factor formula and reconcile to
  the total GMV delta within an absolute tolerance of 0.01.
- Non-zero GMV with zero Order Count fails closed; zero GMV with zero Order
  Count degrades without inventing AOV or contributions.
- Dimension analysis treats absent period members as zero, permits negative and
  greater-than-100% opposing contributions, and suppresses ratios for near-zero
  totals or incomplete group coverage.
- Category contribution uses GMV only and never treats category Order Count as
  overall Order Count.
- Candidate analysis computes Conversion, Promotion Coverage, and Inventory
  Fill Rate from additive aggregated numerators and denominators and returns
  null on missing/zero denominators.
- Only candidate factors requested by the Analysis Plan are emitted.
- Results contain stable IDs, exact Query IDs, Metric versions, typed values,
  reconciliation, and stable warnings; they contain no SQL or query trace.
- Numeric-domain, missing/duplicate query, lineage-version, and reconciliation
  violations fail with stable typed error codes.
- No existing NL2SQL, LangGraph, AOV/GMV definition, data, metadata, API, or
  diagnostic business-report logic was changed.

## Known Issues

- Evidence support/refutation, candidate ranking, claim validation, and report
  generation remain intentionally deferred to ANA-007.
- The deterministic Analyzer is not wired into the runtime diagnosis Graph;
  wiring remains deferred until all downstream stages are complete.
- Repository-wide Ruff and mypy findings predate ANA-006 and remain at the
  accepted 31/36 baseline.
- SQL-002 accuracy limitations and the previously documented Qdrant
  compatibility warning remain unchanged.

## Diff Review Summary

- Diff is limited to the nine files allowed by the ANA-006 Spec.
- Analyzer input is restricted to frozen Analysis Plan and Query Result
  contracts; it cannot issue queries or call an LLM.
- All derived arithmetic uses Decimal precision 28 and stable six-decimal
  serialization; binary floating-point inputs are rejected.
- Degraded cases explicitly suppress unsupported ratios/contributions and emit
  stable warnings instead of fabricating numeric values.
- Serialized Analysis Results exclude raw SQL, parameters, SQL fingerprints,
  validation traces, credentials, connection strings, and business claims.
- No API key, password, token, cookie, local configuration, raw Olist data, or
  production query result was added.
