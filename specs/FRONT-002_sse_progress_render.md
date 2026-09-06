# FRONT-002 SSE Progress Render Fix

## 1. Feature

Fix the Vue frontend so SSE progress events received incrementally from the FastAPI endpoint are rendered immediately instead of appearing only after the whole request finishes.

## 2. Source of Truth

1. The current user report and authorization to fix the streaming display.
2. This specification.
3. `AGENTS.md`.
4. `README.md`.
5. `IMPLEMENTATION_STATUS.md`.
6. `specs/DEPLOY-001_single_process_runtime.md` and `DEPLOY-001_COMPLETION.md`.
7. Current frontend `App.vue` and SSE parser behavior.

## 3. Prerequisite Findings

- A direct HTTP stream against `127.0.0.1:8000/api/query` confirmed the backend emits SSE events progressively: the first events arrive at about 0.4 seconds and later stage events arrive as each stage finishes.
- The frontend created `exchange` as a plain object, pushed it into a `ref([])`, then continued to mutate that plain object. Vue therefore did not track those mutations; the progress list stayed visually unchanged until a later unrelated render, when all accumulated state appeared at once.
- No backend, SQL, graph, or SSE-generator change is required.

## 4. In Scope

- Make the per-request `exchange` object reactive before it is pushed into `exchanges`.
- Ensure incremental progress, terminal state, and result updates trigger Vue rendering immediately.
- Preserve existing parsing, cancellation, terminal classification, and display behavior.

## 5. Out of Scope

- No backend, API, SQL, diagnosis, data, database, Metadata, or deployment logic change.
- No SSE parser format change.
- No new stream buffering or proxy configuration.
- No latency optimization.

## 6. Allowed Files

- `specs/FRONT-002_sse_progress_render.md`
- `frontend/src/App.vue`
- `IMPLEMENTATION_STATUS.md`
- `FRONT-002_COMPLETION.md`

## 7. Local Plan

1. Change the per-request `exchange` literal to `reactive({...})`.
2. Run the existing frontend test suite and production build.
3. Confirm no backend regression is needed and static baselines remain unchanged.
4. Complete the report, create one commit, push, and stop.

## 8. Verification Commands

```powershell
cd frontend
npm test
npm run build
```

The backend already passed direct streaming verification and is not changed.

## 9. Acceptance Criteria

1. Incremental SSE progress events are rendered as they arrive.
2. The request still reaches its terminal result or error state normally.
3. Existing frontend tests and the production build pass.
4. No backend, SQL, diagnosis, data, or deployment file is changed.

## 10. Completion Boundary

After the FRONT-002 report, independent commit, and push, stop.
