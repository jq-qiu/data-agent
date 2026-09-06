# FRONT-001 MVP Frontend

## 1. Feature

Add a versioned Vue 3/Vite frontend to the `data-agent` repository for the
completed single-turn QUERY and DIAGNOSIS API. Reuse the interaction lessons
from the unversioned prototype at `D:\py project\data-agent-front`, while
leaving that reference directory unchanged.

## 2. Source of Truth

1. Current user authorization to continue and to reuse or regenerate the
   frontend reference.
2. This specification.
3. `specs/API-001_minimal_demo.md` and `API-001_COMPLETION.md`.
4. `docs/01_product_scope.md` and `docs/05_agent_workflow.md`.
5. `IMPLEMENTATION_PLAN.md`, `AGENTS.md`, `README.md`, and
   `IMPLEMENTATION_STATUS.md`.
6. The current `/api/query` request and SSE event behavior.
7. The existing frontend at `D:\py project\data-agent-front` as read-only UI
   reference, not as a V1 facts source.

## 3. Prerequisite Findings

- API-001 is complete at commit `138a1be` and `origin/main` matches local HEAD.
- The backend accepts exactly one non-empty `question` or legacy `query` value
  and returns `progress`, `result`, or `error` events over SSE.
- QUERY results expose the legacy `data` row array. DIAGNOSIS results expose
  `answer`, `report_status`, `analysis_trace`, `evidence`, and `limitations`.
- The reference frontend is a minimal Vue 3/Vite project with no Git metadata.
  It sends legacy `query`, shows progress and tables, but cannot render the
  diagnosis contract or resiliently finalize a partial SSE buffer.
- Adding a clean `frontend/` package to the current repository preserves the
  original reference, gives the UI the same Git history as its API, and avoids
  inventing a second GitHub repository or remote.

## 4. In Scope

- Add a self-contained Vue 3/Vite package under `frontend/`.
- Use same-origin `/api/query` with the canonical `question` request field and
  a Vite development proxy to `http://127.0.0.1:8000`.
- Parse streamed SSE across arbitrary chunks, CRLF/LF separators, multiple
  `data:` lines, comments, and a final event without a trailing blank line.
- Surface stable progress steps and exactly one terminal result/error per UI
  request; allow the user to cancel an active request.
- Render QUERY rows in an accessible responsive table, including an explicit
  empty-result state.
- Render DIAGNOSIS Markdown as safe text structure, status, Evidence summaries,
  limitations, and an expandable safe Trace without `v-html`.
- Include the six frozen V1 questions as optional single-click examples while
  preserving the single-turn product boundary.
- Provide a responsive, keyboard-usable, non-technical Chinese interface with
  clear waiting, success, degraded, no-decline, error, and cancellation states.
- Add deterministic unit tests for the SSE parser and result classification.
- Verify a production build and a real local browser diagnosis request through
  the Vite proxy to the existing FastAPI service.
- Update repository navigation, implementation status, and completion record.

## 5. Out of Scope

- No backend Python, API schema, event contract, prompt, model, SQL, Metadata,
  Metric Registry, LangGraph, Analyzer, Evidence, report, data, or database
  change.
- No access to the original `dw`; no database write or data regeneration.
- No multi-turn memory, `conversation_id`, Checkpointer, login, tenant,
  permission, attachment, arbitrary command, or external business action.
- No chart inference from arbitrary columns and no client-side business math.
- No rendering of raw SQL, parameters, query rows inside Trace, credentials,
  connection details, Ground Truth, or runtime objects.
- No deployment, container, reverse proxy, CI, analytics, telemetry, or new
  GitHub repository in this Feature.
- No modification of `D:\py project\data-agent-front`.

## 6. UI Contract

The frontend sends:

```json
{"question": "为什么2018年5月GMV下降？"}
```

It treats `progress` events as mutable status for a named step. It treats the
first valid `result` or `error` as terminal, ignores later terminal events, and
always releases the active-request state when the stream closes, errors, or is
cancelled.

QUERY renders only the top-level `data` array as a result table. DIAGNOSIS
renders the top-level validated API fields. The Trace view is display-only and
must never derive a business conclusion or execute content.

## 7. Accessibility and Safety

- Use semantic headings, buttons, form labels, table headings, status regions,
  and visible keyboard focus.
- Respect `prefers-reduced-motion` and support narrow mobile layouts.
- Do not use `v-html`; backend Markdown and values remain text nodes.
- Do not persist questions or responses to local storage, cookies, logs, or
  analytics.
- The frontend contains no API key, database credential, token, cookie, or
  credentialed URL.

## 8. Allowed Files

- `specs/FRONT-001_mvp_frontend.md`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/.gitignore`
- `frontend/index.html`
- `frontend/vite.config.js`
- `frontend/src/main.js`
- `frontend/src/App.vue`
- `frontend/src/style.css`
- `frontend/src/lib/sse.js`
- `frontend/test/sse.test.js`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `FRONT-001_COMPLETION.md`

Any additional file requires a documented direct blocker and must remain
inside FRONT-001.

## 9. Local Plan

1. Freeze the SSE parser/classification behavior with Node unit tests.
2. Build the responsive single-page interface from the API-001 contract.
3. Install only the existing Vue/Vite dependency set and generate the lockfile.
4. Run unit tests and the production build.
5. Start the existing FastAPI service and Vite proxy, then verify a real
   DIAGNOSIS request and responsive visual states in the in-app browser.
6. Run the backend regression/static baselines and complete safety/Diff review.
7. Write completion/status records, create one independent commit, push, and
   stop.

## 10. Verification Commands

```powershell
npm test --prefix frontend
npm run build --prefix frontend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

The browser verification uses the local Vite URL and the existing FastAPI
service through the configured `/api` proxy. It records observed UI behavior
without persisting response bodies or credentials.

## 11. Acceptance Criteria

1. The new frontend is versioned inside the current repository; the reference
   frontend remains unchanged.
2. A non-empty question is sent with the canonical `question` field and only
   one request can be active at a time.
3. The parser correctly reconstructs arbitrarily chunked SSE and flushes the
   final unterminated event.
4. Progress, QUERY table, DIAGNOSIS report, Evidence, limitations, Trace,
   controlled error, empty result, and cancellation states are represented.
5. The six fixed questions are available as examples but each click remains a
   standalone single-turn request.
6. Diagnosis Markdown is rendered without raw HTML injection or client-side
   business computation.
7. The layout is usable on desktop and mobile, has visible focus, semantic
   status/table structure, and reduced-motion handling.
8. Frontend unit tests and production build pass.
9. A real local browser request reaches `/api/query` through the proxy and
   visibly completes a DIAGNOSIS flow.
10. Backend pytest passes and Ruff/mypy do not regress the accepted 22/36
    baselines.
11. Diff is limited to allowed FRONT-001 files and contains no secret or
    persisted API response payload.
12. No backend business logic or later Feature is changed.

## 12. Completion Boundary

After completion report, status update, independent commit, and push, stop.
Any deployment, V1.1 conversation, backend refinement, or separate frontend
repository requires a new Feature.
