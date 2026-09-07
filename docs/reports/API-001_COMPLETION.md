# API-001 Completion Report

## Feature

API-001 Minimal API and Demo completed. `POST /api/query` supports the canonical
`question` and legacy `query` shapes, preserves the accepted QUERY path, and
adds the bounded seven-stage DIAGNOSIS path with controlled UNSUPPORTED and
error results. Runtime diagnosis uses only validated read-only warehouse data
from `data_agent_v1_dw` and safely degrades when candidate Evidence is absent.

## Changed Files

- `specs/API-001_minimal_demo.md`
- `app/agent/diagnosis_graph.py`
- `app/diagnosis/runtime.py`
- `app/api/dependencies.py`
- `app/api/routers/query_router.py`
- `app/api/schemas/query_schema.py`
- `app/services/query_service.py`
- `app/agent/nodes/validate_sql.py`
- `app/agent/nodes/execute_sql.py`
- `app/scripts/run_api_demo_v1.py`
- `data/reports/API-001_minimal_demo.json`
- `test/api/test_query_api.py`
- `README.md`
- `API-001_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test\api\test_query_api.py
.\.venv\Scripts\ruff.exe check app\api\dependencies.py test\api\test_query_api.py specs\API-001_minimal_demo.md
.\.venv\Scripts\mypy.exe app\api\dependencies.py app\services\query_service.py app\agent\diagnosis_graph.py app\diagnosis\runtime.py
.\.venv\Scripts\python.exe -m app.scripts.run_api_demo_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

Read-only inspection also confirmed the isolated warehouse name, real DWS date
bounds, aggregate row counts, May/April 2018 GMV movement, and absence of
Traffic, Promotion, and Inventory component values. The frontend reference at
`D:\py project\data-agent-front` was inspected without modification.

## Test Results

- API-001 focused tests: 14 passed.
- Full regression: 242 passed.
- Tests cover strict request shapes, legacy SSE compatibility, deterministic
  routing, safe QUERY/DIAGNOSIS results, real-capability degradation, the seven
  diagnosis stages, same-source SQL validation handoff, and serialized metadata
  access for a shared request-scoped async session.

## Lint Results

- All API-001 implementation, script, and test files pass targeted Ruff.
- Repository-wide Ruff reports 22 existing diagnostics, below the accepted
  31-diagnostic baseline. API dependency annotation cleanup removed eight
  in-scope `B008` findings; no unrelated lint cleanup was performed.

## Type Check Results

- No API-001 mypy finding remains.
- Repository-wide mypy reports 36 existing errors in 11 files, unchanged from
  the accepted FIX-001 baseline.

## Evaluation Results

- Fixed V1 HTTP/SSE Demo questions attempted: 6/6.
- Successful controlled `result` terminal events: 6/6.
- QUERY routes: 2; DIAGNOSIS routes: 4.
- HTTP 200 plus SSE content type: 6/6.
- Safe public Trace checks: 6/6.
- QUERY row results: 1 row for each of the two questions.
- DIAGNOSIS statuses: three `DEGRADED`; one `NO_DECLINE` for the scoped São
  Paulo request against the real Olist period.
- Latency: mean 58,467.103 ms; maximum 208,327.703 ms.
- Token usage and cost: unavailable from the configured model client.

This is a six-question functional Demo with real configured services, not a
production accuracy or generalization claim.

## Acceptance Criteria

- Canonical `question` and compatible legacy `query` requests work; blank,
  mixed, or extra-field requests fail validation.
- QUERY preserves the accepted NL2SQL Graph and legacy `data` array.
- DIAGNOSIS runs Parser, Capability Assessor, Planner, Query Executor,
  Deterministic Analyzer, Evidence Checker, and Report Generator in bounded
  order without recomputing business numbers in the API layer.
- Runtime capability probes follow Validate -> EXPLAIN -> Execute and select
  only registered DWS tables in `data_agent_v1_dw`.
- Empty real candidate columns cause explicit degradation; the runtime API does
  not read Ground Truth or select a Synthetic Case ID.
- The Demo-proven normalized SQL representation mismatch is fixed by
  revalidating the same source SQL at execution, without changing the function
  allowlist or correction limit.
- Parallel metadata recalls sharing one API request session are serialized at
  the dependency boundary without changing the accepted graph topology.
- UNSUPPORTED and execution failures expose stable controlled output without
  raw exception text.
- Public and persisted Trace data excludes raw SQL, parameters, rows,
  fingerprints, credentials, connection details, cookies, tokens, Ground
  Truth labels, and runtime objects.
- Six fixed questions complete successfully through the FastAPI HTTP/SSE path.
- Full pytest passes; Ruff and mypy do not regress their accepted baselines.
- The frontend reference was not modified and no later Feature was started.

## Known Issues

- The Qdrant Python client 1.16.2 warns that the server is 1.19.0; the real
  Demo nevertheless completed 6/6.
- The two QUERY requests depend on an external LLM and were slow: approximately
  138 and 208 seconds. The four deterministic diagnosis requests each completed
  in about 0.8 to 1.2 seconds.
- Repository-wide Ruff retains 22 legacy diagnostics and mypy retains 36 errors
  in 11 files; neither set is introduced by API-001.
- Real Olist Traffic, Promotion, and Inventory candidate fields are empty, so
  corresponding reports correctly degrade rather than claim unsupported causes.
- Frontend redesign remains a separate future Feature.

## Diff Review Summary

- Diff is limited to the fifteen files allowed by the API-001 Spec.
- The accepted QUERY graph, prompts, retrieval TopK, SQL allowlist, repair
  limit, Parser rules, Planner selection, Query Builder SQL, Analyzer math,
  Evidence ranking, and report wording are unchanged.
- Validator/executor edits only preserve the already accepted SQL source across
  handoff; the execution node still revalidates and the Repository still runs
  EXPLAIN before read-only execution.
- The metadata-session guard is request-local and serializes only the three V1
  reads reached concurrently by existing graph branches.
- The Demo artifact stores only question-level routing/status/count/latency and
  safe Trace checks. It contains no answer body, data rows, SQL, parameters,
  credentials, connection strings, or Ground Truth payloads.
- No API key, password, token, cookie, original `dw` access, database write,
  DDL, data regeneration, Metadata rebuild, frontend change, or later Feature
  was introduced.
