# API-001 Minimal API and Demo

## 1. Feature

Expose the accepted single-turn QUERY and DIAGNOSIS paths through one FastAPI
SSE endpoint, preserve the existing frontend request/event compatibility, add a
safe diagnosis Trace, and run the six frozen V1 Demo questions end to end.

## 2. Source of Truth

1. Current user authorization to continue and the read-only frontend reference
   at `D:\py project\data-agent-front`.
2. This specification.
3. `IMPLEMENTATION_PLAN.md`, including the fixed Demo.
4. `docs/01_product_scope.md`.
5. `docs/02_data_and_metric_design.md`.
6. `docs/03_metadata_and_nl2sql.md`.
7. `docs/04_analysis_methodology.md`.
8. `docs/05_agent_workflow.md`.
9. `docs/06_evaluation.md`.
10. Accepted SQL-001 and ANA-001 through ANA-007 contracts.
11. Accepted EVAL-001/FIX-001 Gate 5 results.
12. `AGENTS.md`, `README.md`, and existing API behavior.

## 3. Prerequisite Findings

- Gate 5 passed and API-001 is the only remaining V1 Feature in the plan.
- The existing `POST /api/query` accepts `{ "query": "..." }` and streams
  `progress`, `result`, and `error` events. The existing Vue frontend depends on
  that shape and is not a Git repository.
- The six frozen Demo questions deterministically route to two QUERY requests
  and four DIAGNOSIS requests; every DIAGNOSIS request parses successfully.
- The isolated Olist DWS covers 2016-09-04 through 2018-09-03. May 2018 GMV is
  992871.75 and April 2018 GMV is 993592.98, so the frozen decline exists.
- Traffic, Promotion, and Inventory component columns in the accepted Olist DWS
  are all null by design. Runtime warehouse diagnosis must therefore omit those
  unsupported methods and disclose the missing Evidence. It must not select a
  D01-D10 Synthetic Case or read Ground Truth at runtime.
- The live HTTP Demo exposed parallel metadata recalls sharing one request-scoped
  SQLAlchemy `AsyncSession`. Serialize only those metadata reads at the API
  dependency boundary because one async session cannot provision concurrent
  connections; keep the accepted NL2SQL Graph topology unchanged.

## 4. In Scope

- Keep `POST /api/query` and its SSE transport.
- Accept the canonical single-turn `question` field and the legacy `query`
  field, with exactly one non-empty value required.
- Route every request with the accepted deterministic Intent Router.
- Preserve the existing NL2SQL Graph for QUERY without changing its prompts,
  retrieval, generation, validation, correction, or execution behavior.
- Serialize parallel metadata repository reads that share the API request's one
  async session, without changing graph edges or repository query semantics.
- Wire the accepted Parser, Capability Assessor, Planner, Controlled Query
  Executor, Analyzer, Evidence Checker, and Report Generator into a bounded
  diagnosis LangGraph.
- Build a truthful runtime warehouse capability profile using fixed read-only
  aggregate probes that pass the shared SQL Validator and Repository EXPLAIN
  before execution.
- Emit stable `progress`, `result`, and `error` SSE events. QUERY results retain
  the legacy `data` row array. DIAGNOSIS results expose `intent`, Markdown
  `answer`, safe `analysis_trace`, validated `evidence`, and `limitations`.
- Return UNSUPPORTED as a controlled result with a stable limitation rather
  than invoking either data path.
- Ensure error events expose only stable codes/messages, never raw exception
  text.
- Preserve the original SQL text across a successful validation handoff so the
  execution node revalidates the same accepted input rather than reparsing
  SQLGlot's normalized rendering. This fixes the Demo-exposed `IF` -> `CASE`
  representation mismatch without changing the SQL function allowlist,
  validation policy, repair limit, or generated business SQL.
- Add API/schema/orchestration/runtime-profile tests and a sanitized fixed-Demo
  run report.
- Update README/status/completion records to the final verified V1 state.

## 5. Out of Scope

- No change to NL2SQL prompts, model choice, retrieval TopK, SQL repair policy,
  SQL Validator policy, or SQL-002 scoring.
- No change to Parser rules, Capability rules, Planner task selection, Query
  Builder SQL, Analyzer math, Evidence rules/ranking, or report wording.
- No use of Ground Truth or D01-D10 Case IDs in the runtime API.
- No database write, DDL, data regeneration, original `dw` access, or mutation
  of accepted Metadata indexes.
- No login, tenant, permission, conversation history, Checkpointer, attachment,
  arbitrary command, causal inference, or unlimited loop.
- No frontend implementation in this Feature. `data-agent-front` is inspected
  read-only for compatibility and may be updated in a separately scoped task.
- No unrelated Ruff/mypy cleanup and no Feature after API-001.

## 6. API and Trace Contract

Requests:

```json
{"question": "为什么2018年5月GMV下降？"}
```

or the backward-compatible form:

```json
{"query": "2018年5月GMV是多少？"}
```

Exactly one field is accepted. Unknown fields, blank values, or both fields are
rejected by request validation.

SSE event kinds remain:

- `progress`: stable step and `running | success | error` status;
- `result`: final controlled output;
- `error`: stable public error code and message.

QUERY result events retain `data` for the existing table renderer and add the
selected Intent plus a safe validation Trace. DIAGNOSIS result events contain:

```json
{
  "type": "result",
  "intent": "DIAGNOSIS",
  "answer": "...",
  "analysis_trace": [],
  "evidence": [],
  "limitations": []
}
```

The Trace may include stage names/status, parsed parameters, supported methods,
task/query/result/Evidence IDs, query roles, registered tables/columns/JOINs,
grain warnings, versions, and reconciliation status. It must not include raw
SQL, bind parameters, query rows, SQL fingerprints, credentials, connection
details, cookies, tokens, Ground Truth labels, or runtime objects.

## 7. Runtime Data Boundary

- Assert the configured database and SQL Policy both select exactly
  `data_agent_v1_dw`.
- Runtime capability probes use only the registered Olist diagnosis DWS tables.
- Every probe follows Validate -> EXPLAIN -> Execute and returns only aggregate
  non-null counts plus date bounds internally.
- The capability profile marks a column non-empty only when the real aggregate
  count is positive.
- User diagnosis queries use `QueryDataSource.WAREHOUSE` with no Synthetic Case
  ID. Missing candidate components produce the existing explicit degradation.

## 8. Allowed Files

- `specs/API-001_minimal_demo.md`
- `app/agent/diagnosis_graph.py`
- `app/diagnosis/runtime.py`
- `app/api/dependencies.py`
- `app/api/routers/query_router.py`
- `app/api/schemas/query_schema.py`
- `app/services/query_service.py`
- `app/agent/nodes/validate_sql.py` (validation handoff only)
- `app/agent/nodes/execute_sql.py` (same-input revalidation only)
- `app/scripts/run_api_demo_v1.py`
- `data/reports/API-001_minimal_demo.json`
- `test/api/test_query_api.py`
- `README.md`
- `docs/reports/API-001_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

Any additional file requires a documented direct blocker and must remain inside
API-001.

## 9. Local Plan

1. Add strict request/SSE and safe public-result tests.
2. Implement validated runtime warehouse profiling.
3. Build the bounded diagnosis LangGraph from the accepted node adapters.
4. Route QUERY/DIAGNOSIS/UNSUPPORTED in the existing Query Service, preserve
   legacy QUERY events, and fix only the proven validator/executor handoff.
5. Add the sanitized six-question Demo runner and API-focused tests.
6. Run a real isolated-service Demo, a live HTTP smoke, full pytest, Ruff,
   mypy, secret/safe-artifact scans, and Diff Review.
7. Write completion/status records, create one commit, push, and stop.

## 10. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/api/test_query_api.py
.\.venv\Scripts\python.exe -m app.scripts.run_api_demo_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

## 11. Acceptance Criteria

1. Canonical `question` and legacy `query` requests work; invalid mixed/blank or
   extra-field requests fail validation.
2. Intent Router selects the unchanged QUERY, DIAGNOSIS, or UNSUPPORTED branch.
3. QUERY still runs the accepted NL2SQL Graph and preserves legacy table data.
   A validated repaired query is revalidated from the same source text before
   execution; normalized-rendering changes cannot create a false rejection.
   Parallel metadata recalls do not operate on the same async session at once.
4. DIAGNOSIS runs the seven accepted stages in finite order and returns the
   existing validated report without recomputing business numbers in the API.
5. Runtime capability is derived from real registered DWS aggregate probes;
   empty candidate fields correctly degrade rather than being fabricated.
6. UNSUPPORTED and execution failures use stable safe public output.
7. No emitted or persisted Trace contains raw SQL, parameters, query rows,
   fingerprint, credentials, connection details, Ground Truth, or runtime
   dependencies.
8. The six frozen Demo questions are all attempted and each produces a valid
   controlled terminal event; exact real results, latency, and any failures are
   recorded without a production accuracy claim.
9. A live FastAPI HTTP/SSE smoke proves routing and framing at `/api/query`.
10. The old frontend request/event contract remains compatible; the frontend
    directory is not modified.
11. Full pytest passes and Ruff/mypy do not regress the accepted 31/36 baseline.
12. Diff is limited to the allowed API-001 files and no later Feature starts.

## 12. Completion Boundary

After the report, status, independent commit, and push are complete, stop.
API-001 is the final Feature in the current MVP V1 implementation plan; any
frontend redesign or V1.1 work requires a new separately scoped Feature.
