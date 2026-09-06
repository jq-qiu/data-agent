# DEMO-001 Completion Report

## Feature

DEMO-001 Synthetic Diagnosis Demo. A dedicated API endpoint and frontend section now run the complete GMV-diagnosis evidence chain against bound Synthetic Evidence cases, so an interviewer can see Traffic Drop, Promotion End, and Stockout demonstrations instead of only the real Olist degradation.

## Changed Files

- `specs/DEMO-001_synthetic_diagnosis_demo.md`
- `app/diagnosis/runtime.py`
- `app/services/query_service.py`
- `app/api/routers/query_router.py`
- `frontend/src/App.vue`
- `test/api/test_query_api.py`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `DEMO-001_COMPLETION.md`

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest testpi	est_query_api.py -q
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts
uff.exe check .
.\.venv\Scripts\mypy.exe app
cd frontend
npm test
npm run build
git diff --check
git status --short --branch
```

A real read-only smoke built the D01/D03/D05 Synthetic capability profiles and completed the D01 diagnosis graph against `data_agent_v1_dw`.

## Test Results

- API-focused tests: 26 passed.
- Full backend pytest: 289 passed.
- Frontend Node tests: 5 passed.
- Vite production build: passed; 11 modules transformed.

## Lint Results

- Repository Ruff remains 22 existing diagnostics, unchanged.

## Type Check Results

- Repository mypy remains 36 existing errors in 11 files while checking 107 source files.

## Evaluation Results

- D01/D03/D05 profile probes returned non-empty Traffic/Promotion/Inventory columns for the selected case.
- D01 complete diagnosis graph produced `final_report`, `validated_evidence`, and candidate sections without reading Ground Truth labels.
- The public result path is labeled through existing `SYNTHETIC_CANDIDATE_DATA` Evidence limitations.

## Acceptance Criteria

1. Passed: the demo endpoint accepts exactly D01-D10 and rejects unknown case IDs with HTTP 422.
2. Passed: Synthetic profile is built from actual `analysis_*` table content, not Ground Truth labels.
3. Passed: D01 full diagnosis chain completed; D01/D03/D05 profiles were real-smoke verified.
4. Passed: existing `/api/query` behavior and tests are unchanged.
5. Passed: frontend demo buttons are labeled synthetic and use the existing report renderer.
6. Passed: tests, Ruff, mypy, and frontend build retain accepted baselines.
7. Passed: no Ground Truth label, expected factor, credential, raw SQL, or user payload is exposed by the diff.

## Known Issues

- The frontend demo requires the single-process server to be restarted after this commit.
- D01/D03/D05 were real-smoke verified at the backend graph level; no browser-level automated UI assertion was run.
- Synthetic cases remain explicitly synthetic and are not real Olist observations.

## Diff Review Summary

The change adds a case-bound synthetic profile provider, a synthetic diagnosis stream, a guarded demo route, and frontend buttons. It does not alter warehouse diagnosis, Analyzer math, Evidence/report logic, Ground Truth reads, NL2SQL, data, or deployment. Commit and push synchronization are verified separately after this report is committed.
