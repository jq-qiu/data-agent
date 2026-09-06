# DEPLOY-001 Completion Report

## Feature

DEPLOY-001 Single-process Runtime. The built Vue frontend and unchanged FastAPI query API now run on one origin and one Uvicorn process, with a safe build/preflight launcher for an already provisioned single host.

## Changed Files

- `specs/DEPLOY-001_single_process_runtime.md`
- `app/deployment.py`
- `app/scripts/serve.py`
- `main.py`
- `test/deployment/test_runtime.py`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `DEPLOY-001_COMPLETION.md`

## Added Dependencies

None. The launcher uses the Python standard library plus the existing PyYAML and Uvicorn dependencies. Frontend installation continues to use the committed npm lockfile.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test\deployment\test_runtime.py
.\.venv\Scripts\ruff.exe check app\deployment.py app\scripts\serve.py main.py test\deployment\test_runtime.py
.\.venv\Scripts\mypy.exe app\deployment.py app\scripts\serve.py
.\.venv\Scripts\python.exe -m app.scripts.serve --check
.\.venv\Scripts\python.exe -m app.scripts.serve --install --check
.\.venv\Scripts\python.exe -m app.scripts.serve --skip-build
npm test --prefix frontend
npm run build --prefix frontend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

The live smoke used local HTTP requests against the single launcher process and retained only aggregate verification facts, not response bodies.

## Test Results

- DEPLOY-001 targeted tests: 7 passed, 0 failed.
- Full backend regression: 249 passed, 0 failed in 12.94 seconds.
- Frontend Node tests: 5 passed, 0 failed.
- Tests cover isolated-DW configuration, secret-safe failures, locked installation planning, build validation, static serving, route precedence, process liveness, API-only import behavior, and legacy-router removal.

## Lint Results

- All DEPLOY-001 Python implementation and test files pass targeted Ruff.
- Repository Ruff reports 22 existing diagnostics, unchanged from FRONT-001.

## Type Check Results

- `app/deployment.py` and `app/scripts/serve.py` pass targeted mypy.
- Repository mypy reports 36 existing errors in 11 files while checking 104 source files, unchanged from FRONT-001.

## Evaluation Results

- Launcher preflight and Vite production build: passed; Vite 7.3.6 transformed 11 modules.
- Forced locked-install path: passed; `npm ci` added 35 packages and reported 0 known vulnerabilities before a successful build.
- Real single-process frontend: `/` returned 200 with the product title and the built JavaScript asset returned 200.
- Liveness: `/api/health/live` returned `{"status":"ok"}` without querying external services.
- Legacy routes: `/hello/...` and `/test_query` returned 404; `POST /login` returned 405 from the static mount. The legacy router is not registered.
- Real diagnosis SSE: HTTP 200 with `text/event-stream`, 18 progress events, one `DIAGNOSIS`/`DEGRADED` terminal result, 4 Evidence items, and 8 public Trace stages.
- Public-internet security, TLS, reverse proxy, load, high availability, recovery, monitoring, Docker, cloud, and production SLA: not evaluated; they are outside DEPLOY-001.

## Acceptance Criteria

1. Passed: one command performs preflight/build and starts frontend plus API on one origin.
2. Passed: preflight requires exactly `data_agent_v1_dw` and errors do not echo other configuration values.
3. Passed: npm installation uses `npm ci` only when modules are missing or `--install` is explicit.
4. Passed: the launcher refuses a missing build while the FastAPI integration supports API-only imports without one.
5. Passed: the built frontend and asset are served at root while `/api/query` retains route priority and SSE behavior.
6. Passed: process-only liveness makes no external readiness claim.
7. Passed: the deployable application does not register the legacy test/password-echo router.
8. Passed: loopback is the default host and network binding requires `--host`.
9. Passed: targeted/full tests and frontend build pass; Ruff/mypy retain their accepted baselines.
10. Passed: the real single-process smoke verified frontend, liveness, legacy-route absence, and diagnosis completion.
11. Passed: the diff contains exactly the eight allowed files and no detected secret, connection string, or persisted response payload.
12. Passed: no external service, database, index, data, business logic, or later Feature was modified.

## Known Issues

- The runtime still requires operator-provided ignored configuration and already available MySQL, Qdrant, Elasticsearch, embedding, and LLM services.
- Docker was unavailable on the validated host; container and public hosting decisions are intentionally deferred.
- The existing Qdrant compatibility warning, 22 Ruff diagnostics, and 36 mypy errors in 11 files remain unchanged.
- The legacy router source file remains in the repository for historical compatibility but is not registered by the deployable application.
- A static root mount returns method-not-allowed rather than not-found for some non-GET legacy paths; no legacy handler receives the request.

## Diff Review Summary

The deployment layer performs orchestration only: it validates the isolated database selection, builds a locked frontend, verifies the artifact, starts one worker, exposes process liveness, and mounts static content after the product API. It does not log credential values, provision external services, change API/SSE data, recompute business metrics, access another database, or add public-infrastructure assumptions. Final review found exactly the eight allowed files, no credential or connection-string pattern, no tracked local configuration/dependency/build directory, and no whitespace error. Commit and push synchronization are verified separately after this report is committed.
