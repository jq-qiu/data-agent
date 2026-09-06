# REPORT-001 Completion Report

## Feature

REPORT-001 Localized Evidence Limitations. Evidence limitation codes now render as stable Chinese labels followed by their English code, so interview and business-user reports are readable while remaining traceable.

## Changed Files

- `specs/REPORT-001_localized_evidence_limitations.md`
- `app/diagnosis/evidence.py`
- `app/diagnosis/report.py`
- `app/services/query_service.py`
- `test/diagnosis/test_evidence_report.py`
- `IMPLEMENTATION_STATUS.md`
- `REPORT-001_COMPLETION.md`

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test\diagnosis	est_evidence_report.py testpi	est_query_api.py -q
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts
uff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

## Test Results

- Focused Evidence/API tests: 58 passed.
- Full backend pytest: 290 passed.

## Lint Results

- Repository Ruff remains 22 existing diagnostics.

## Type Check Results

- Repository mypy remains 36 existing errors in 11 files while checking 107 source files.

## Evaluation Results

- Every `EvidenceLimitation` value now has a non-empty Chinese label.
- Report limitations render as `中文说明（英文代码）`, for example `合成候选因素数据（SYNTHETIC_CANDIDATE_DATA）`.
- Public `result.limitations` uses the same localized labels.

## Acceptance Criteria

1. Passed: every EvidenceLimitation maps to a non-empty Chinese label.
2. Passed: report limitations render as `中文说明（英文代码）`.
3. Passed: public limitations use the same localized label.
4. Passed: stable English codes remain present.
5. Passed: no analysis, evidence, or report conclusion logic changed.
6. Passed: tests and Ruff/mypy baselines did not regress.

## Known Issues

- Missing column identifiers and trace-stage names remain English because they are schema identifiers, not Evidence limitation codes.

## Diff Review Summary

The change is presentation-only: it adds a label map and applies it in the report limitation section and public limitations list. No Evidence calculation, Analyzer math, planner, query building, or report conclusion changed. Commit and push synchronization are verified separately after this report is committed.
