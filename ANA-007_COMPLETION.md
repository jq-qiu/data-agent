# ANA-007 Completion Report

## Feature

ANA-007 Evidence Report completed. `EvidenceChecker` and `ReportGenerator` are
separate deterministic stages: the checker converts accepted Analysis Results
into Validated Evidence, while the generator reads only that Evidence bundle to
produce a six-section JSON/Markdown report. Unsupported Evidence, missing data,
conflicts, and non-decline cases cannot become candidate conclusions.

## Changed Files

- `specs/ANA-007_evidence_report.md`
- `app/diagnosis/__init__.py`
- `app/diagnosis/evidence.py`
- `app/diagnosis/report.py`
- `app/scripts/evaluate_evidence_report_v1.py`
- `data/evaluation/evidence_report_golden_v1.json`
- `data/reports/ANA-007_evidence_report_evaluation.json`
- `test/diagnosis/test_evidence_report.py`
- `ANA-007_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_evidence_report.py -q
.\.venv\Scripts\python.exe -m app.scripts.evaluate_evidence_report_v1
.\.venv\Scripts\ruff.exe check app/diagnosis/evidence.py app/diagnosis/report.py app/diagnosis/__init__.py app/scripts/evaluate_evidence_report_v1.py test/diagnosis/test_evidence_report.py
.\.venv\Scripts\mypy.exe app/diagnosis/evidence.py app/diagnosis/report.py app/scripts/evaluate_evidence_report_v1.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## Test Results

- ANA-007 targeted tests: 26 passed.
- Full regression: 209 passed.

## Lint Results

- All ANA-007 implementation, evaluation, and test files pass targeted Ruff.
- Repository-wide Ruff reports 31 existing diagnostics, unchanged from the
  accepted ANA-006 baseline.

## Type Check Results

- ANA-007 implementation and evaluation files pass targeted mypy.
- Repository-wide mypy reports 36 existing errors in 11 files, unchanged from
  the accepted ANA-006 baseline.

## Evaluation Results

- Fixed Evidence/report contract cases: 10.
- Exact expected support/degradation/report outcomes: 10/10.
- Consecutive Evidence ID checks: 10/10.
- Complete Analysis Result, Query, and Metric-version lineage checks: 10/10.
- Safe serialized-output checks: 10/10.
- Unsupported Evidence used in conclusions: 0.
- Forbidden causal-language violations: 0.
- Cases cover high/medium/missing Traffic Evidence, supported/conflicting
  Promotion, supported Inventory, non-decline gating, reconciled Shapley,
  reconciled Dimension contribution, and incomplete Dimension degradation.

## Acceptance Criteria

- Evidence IDs and fact IDs are consecutive, unique, and deterministic.
- Every Evidence item carries exact Analysis Result IDs, Query IDs, and Metric
  versions; inconsistent or missing lineage fails closed.
- The GMV anomaly must be confirmed before any candidate Evidence is eligible
  for a conclusion.
- Candidate validation uses directional metric-chain consistency with no
  invented magnitude threshold and never reads Ground Truth labels at runtime.
- Missing primary metrics and directly conflicting chains are `unsupported`;
  incomplete but directionally consistent chains are explicitly limited.
- Candidate Evidence always discloses synthetic candidate data and absence of a
  causal design.
- Reconciled Shapley/Dimension outputs become high Evidence; incomplete or
  near-zero cases expose only supported numeric facts and limitations.
- Candidate ranking is deterministic by support, absolute primary change rate,
  and frozen factor order; unsupported Evidence is excluded.
- Report Generator accepts only a Validated Evidence bundle and emits the six
  frozen sections with Evidence, Analysis, and Query references on every
  statement.
- Unsupported Evidence cannot be referenced by a conclusion, and forbidden
  deterministic causal wording is rejected.
- No Ground Truth lookup, LLM call, database access, Graph/API wiring, Analyzer
  math change, or NL2SQL change was added.

## Known Issues

- EVAL-001 must still run the complete D01-D10 diagnosis regression and report
  real root-cause/evidence metrics and error analysis.
- Runtime Data Profile construction and diagnosis Graph/API wiring remain
  deferred; ANA-007 exposes pure node adapters only.
- Report prose is intentionally deterministic and conservative; no LLM wording
  layer is enabled in V1 safety-critical Evidence generation.
- Repository-wide Ruff and mypy findings predate ANA-007 and remain at the
  accepted 31/36 baseline.
- SQL-002 accuracy limitations and the previously documented Qdrant
  compatibility warning remain unchanged.

## Diff Review Summary

- Diff is limited to the ten files allowed by the ANA-007 Spec.
- Evidence Checker consumes only the frozen Analysis Plan and Analysis Result
  contracts; Report Generator consumes only Validated Evidence.
- Output contains no raw SQL, parameters, SQL fingerprints, validation traces,
  Ground Truth labels, credentials, or unconstrained model content.
- All report numbers are rendered directly from Evidence facts, and every
  statement includes Evidence, Analysis Result, and Query lineage.
- Candidate conclusions are limited to supported association Evidence;
  conflict, missing data, synthetic-data status, and no-causal-design limits
  remain visible.
- No API key, password, token, cookie, local configuration, raw Olist data, or
  production query result was added.
