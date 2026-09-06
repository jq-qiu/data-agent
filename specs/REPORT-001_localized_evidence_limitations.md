# REPORT-001 Localized Evidence Limitations

## 1. Feature

Render Evidence limitation codes as human-readable Chinese labels while preserving the stable English code for traceability. This improves interview and business-user readability without changing diagnosis calculations.

## 2. Source of Truth

1. The user's request to make report limitations readable in Chinese.
2. This specification.
3. `AGENTS.md`, `README.md`, and `IMPLEMENTATION_STATUS.md`.
4. `specs/ANA-007_evidence_report.md` and `ANA-007_COMPLETION.md`.
5. Current Evidence, Report Generator, Query Service, and regression tests.

## 3. Prerequisite Findings

- The report currently prints raw values such as `SYNTHETIC_CANDIDATE_DATA`,
  `NO_CAUSAL_DESIGN`, and `PRIMARY_METRIC_NOT_DECREASING`.
- These codes are stable identifiers and must remain traceable.
- Public `result.limitations` also exposes the raw codes.

## 4. In Scope

- Add a deterministic Chinese label map for every `EvidenceLimitation` value.
- Format limitations as `中文说明（英文代码）`.
- Use the label in the Report Generator limitation section.
- Use the label in the public Query Service limitations list.
- Add focused regression tests for representative labels.

## 5. Out of Scope

- No change to Evidence calculation, Analyzer math, planner, query building, or
  report conclusions.
- No translation of missing column identifiers, trace stages, or metric IDs.
- No frontend change; existing renderer consumes the already-localized text.

## 6. Allowed Files

- `specs/REPORT-001_localized_evidence_limitations.md`
- `app/diagnosis/evidence.py`
- `app/diagnosis/report.py`
- `app/services/query_service.py`
- `test/diagnosis/test_evidence_report.py`
- `test/api/test_query_api.py`
- `IMPLEMENTATION_STATUS.md`
- `REPORT-001_COMPLETION.md`

## 7. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test\diagnosis	est_evidence_report.py testpi	est_query_api.py -q
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts
uff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

## 8. Acceptance Criteria

1. Every EvidenceLimitation maps to a non-empty Chinese label.
2. Report limitations render as `中文说明（英文代码）`.
3. Public limitations use the same localized label.
4. Stable English codes remain present for traceability.
5. No analysis, evidence, or report conclusion logic changes.
6. Tests and static baselines do not regress.

## 9. Completion Boundary

After the REPORT-001 report, independent commit, and push, stop.
