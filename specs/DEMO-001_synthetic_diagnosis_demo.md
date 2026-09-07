# DEMO-001 Synthetic Diagnosis Demo

## 1. Feature

Add a bounded synthetic-diagnosis demo entry to the API and frontend so an
interviewer can watch the complete GMV anomaly-diagnosis evidence chain using
Synthetic Evidence, instead of seeing only the real Olist degradation where
Traffic, Promotion, and Inventory fields are empty.

## 2. Source of Truth

1. The user's request to prepare an interview demo.
2. This specification.
3. `AGENTS.md`, `README.md`, `IMPLEMENTATION_PLAN.md`, and
   `IMPLEMENTATION_STATUS.md`.
4. `docs/01_product_scope.md`, `docs/02_data_and_metric_design.md`,
   `docs/04_analysis_methodology.md`, and `docs/05_agent_workflow.md`.
5. `specs/DATA-003_synthetic_evidence.md`,
   `specs/ANA-001_intent_router.md`, `specs/ANA-002_analysis_question_parser.md`,
   `specs/ANA-003_capability_assessment.md`, `specs/ANA-004_analysis_planner.md`,
   `specs/ANA-005_analysis_task_executor.md`, `specs/ANA-006_deterministic_analyzer.md`,
   and `specs/ANA-007_evidence_report.md`.
6. Current `QueryDataSource.SYNTHETIC_CASE` query layouts, D01-D10 frozen
   questions, `analysis_*` tables, diagnosis graph, Query Service, API router,
   and frontend.

## 3. Prerequisite Findings

- The diagnosis query layer already supports `QueryDataSource.SYNTHETIC_CASE`
  and has `analysis_sales_region_daily` / `analysis_sales_category_daily`
  layouts.
- D01-D10 frozen questions exist in `data/evaluation/diagnosis_golden_v1.json`,
  and `data/config/synthetic_v1.json` defines their generated evidence.
- The public API currently always builds a warehouse capability profile and a
  warehouse query context, so it cannot demonstrate complete candidate-factor
  validation on real Olist data.
- Ground Truth labels and expected factors must not be read at runtime. The demo
  must construct capability from actual `analysis_*` table content.

## 4. In Scope

- Add a `SyntheticCapabilityProfileProvider` that probes non-empty columns and
  date bounds for one bound `case_id` using validated read-only SQL.
- Add a `QueryService.synthetic_diagnosis_events` path using
  `QueryDataSource.SYNTHETIC_CASE` and the selected case ID.
- Add a dedicated demo API endpoint accepting only D01-D10 case IDs and mapping
  each to its frozen demonstration question text.
- Keep synthetic results explicitly labeled `SYNTHETIC_CANDIDATE_DATA` in public
  limitations without exposing Ground Truth labels.
- Add a frontend demo section with three representative cases: D01 Traffic Drop,
  D03 Promotion End, and D05 Stockout.
- Add unit tests for demo routing, provider validation, and synthetic labeling.
- Update README/status and the completion report.

## 5. Out of Scope

- No change to QUERY/DIAGNOSIS intent routing.
- No change to warehouse diagnosis behavior, Analyzer formulas, Evidence logic,
  or report wording.
- No runtime reading of Ground Truth labels or expected factors.
- No change to DATA-003 generation, DWS, Metadata content, or indexes.
- No new candidate factor, causal claim, or V1.1 real-world factor.
- No latency optimization or production deployment work.

## 6. Allowed Files

- `specs/DEMO-001_synthetic_diagnosis_demo.md`
- `app/diagnosis/runtime.py`
- `app/services/query_service.py`
- `app/api/routers/query_router.py`
- `frontend/src/App.vue`
- `test/api/test_query_api.py`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/DEMO-001_COMPLETION.md`

Any additional file requires a documented direct blocker and must remain inside
DEMO-001.

## 7. Local Plan

1. Add a synthetic capability provider that probes only the selected case.
2. Add a synthetic diagnosis event stream in Query Service.
3. Add the demo endpoint and case/question mapping.
4. Add the frontend demo section with synthetic labeling.
5. Run focused tests, full backend pytest, frontend tests/build, Ruff, mypy,
   documentation, secret/scope, and Diff Review.
6. Complete the report, create one commit, push, and stop.

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest testpi	est_query_api.py
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

## 9. Acceptance Criteria

1. The demo endpoint accepts exactly D01-D10 and rejects invalid case IDs.
2. It constructs a synthetic capability profile from actual `analysis_*` rows
   without reading Ground Truth labels.
3. D01/D03/D05 run the complete diagnosis chain and return labeled synthetic
   limitations.
4. Existing warehouse `/api/query` behavior is unchanged.
5. Frontend demo buttons are labeled synthetic and display the existing report.
6. Tests, Ruff, mypy, and frontend build do not regress accepted baselines.
7. No Ground Truth label, expected factor, credential, raw SQL, or user payload
   is persisted or exposed publicly.

## 10. Completion Boundary

After the DEMO-001 report, independent commit, and push, stop.
