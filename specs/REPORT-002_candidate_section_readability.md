# REPORT-002 Candidate Section Readability

## 1. Feature

Make the candidate-evidence report section distinguish supported candidates from unsupported/excluded candidates, so a single-cause Synthetic demo reads as one hit plus explicit exclusions instead of an unclear block of limitations.

## 2. Source of Truth

1. The user's request to improve candidate-evidence readability.
2. This specification.
3. `AGENTS.md`, `README.md`, and `IMPLEMENTATION_STATUS.md`.
4. `specs/ANA-007_evidence_report.md`, `specs/REPORT-001_localized_evidence_limitations.md`.
5. Current Report Generator and Evidence bundle behavior.

## 3. Prerequisite Findings

- In D01, Traffic is a high-support candidate while Promotion and Inventory are unsupported because their primary metrics did not decrease.
- The previous report showed only supported candidates in section 5 and then listed every candidate limitation in section 6, making the result hard to read.

## 4. In Scope

- Add explicit unsupported-candidate statements to the candidate section.
- Keep supported-candidate statements first.
- Remove duplicate candidate limitation rows from the limitations section; retain missing Evidence and recommendation text.
- Use the existing localized limitation labels.

## 5. Out of Scope

- No change to Evidence calculation, Analyzer math, ranking, or report conclusions.
- No frontend change.
- No translation of schema identifiers.

## 6. Allowed Files

- `specs/REPORT-002_candidate_section_readability.md`
- `app/diagnosis/report.py`
- `test/diagnosis/test_evidence_report.py`
- `IMPLEMENTATION_STATUS.md`
- `REPORT-002_COMPLETION.md`

## 7. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test\diagnosis	est_evidence_report.py -q
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts
uff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

## 8. Acceptance Criteria

1. Supported candidates remain before unsupported candidates in section 5.
2. Unsupported candidates appear with a Chinese explanation of their limitation.
3. The limitations section no longer repeats candidate limitation rows.
4. Missing Evidence and recommendation text remain present.
5. Report shape, Evidence logic, and baselines do not regress.

## 9. Completion Boundary

After the REPORT-002 report, independent commit, and push, stop.
