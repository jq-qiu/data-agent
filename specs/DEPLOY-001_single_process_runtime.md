# DEPLOY-001 Single-process Runtime

## 1. Feature

Package the completed Vue frontend and FastAPI API into one same-origin local
runtime, with a deterministic preflight/build command suitable for a single
host whose required data and model services are already provisioned.

## 2. Source of Truth

1. Current user authorization to continue with the recommended DEPLOY-001.
2. This specification.
3. `specs/API-001_minimal_demo.md` and `API-001_COMPLETION.md`.
4. `specs/FRONT-001_mvp_frontend.md` and `FRONT-001_COMPLETION.md`.
5. `docs/01_product_scope.md` and `docs/05_agent_workflow.md`.
6. `IMPLEMENTATION_PLAN.md`, `AGENTS.md`, `README.md`, and
   `IMPLEMENTATION_STATUS.md`.
7. Current FastAPI, Vite, and local configuration behavior.

## 3. Prerequisite Findings

- FRONT-001 is complete at commit `c040ea8`; local `main` and `origin/main`
  match and the worktree is clean.
- The Vite frontend uses same-origin `/api/query`, so a built frontend can be
  served by FastAPI without changing the API contract.
- The current root route belongs to an old test router that also exposes a
  mock login response containing submitted password text. These test routes
  are not part of API-001 or the V1 product and must not be exposed by the
  deployable application.
- `conf/app_config.yaml` is required at import/runtime, is intentionally
  ignored, and currently selects the isolated `data_agent_v1_dw` database.
  Preflight may inspect only structural readiness and must never print secret
  values or complete connection details.
- Python 3.12, Node, and npm are available. Docker is not installed. MySQL,
  Qdrant, Elasticsearch, embedding, and LLM services are external runtime
  prerequisites with accepted data/configuration already in place.
- Containerizing or provisioning those external services would introduce
  database migration, index lifecycle, secret distribution, and persistence
  decisions that are not defined by current facts sources.

## 4. In Scope

- Serve a completed `frontend/dist` from FastAPI at `/`, after registering all
  `/api` routes, so frontend and SSE API share one origin and one port.
- Keep API-only startup valid when the frontend has not been built; the
  runtime launcher must build it before importing/starting the application.
- Expose a dependency-free liveness endpoint at `/api/health/live` that reports
  process availability only and makes no database/model readiness claim.
- Remove the legacy test router from the deployable FastAPI application so its
  mock root, login, hello, item, user, and stream routes are not public.
- Add a cross-platform Python launcher that:
  - verifies the local ignored configuration exists;
  - verifies only that `db_dw.database` equals `data_agent_v1_dw`;
  - locates npm, installs locked frontend dependencies when missing or forced,
    and runs the production frontend build;
  - verifies the built `index.html` exists before importing `main`;
  - starts one Uvicorn worker with configurable host/port;
  - supports a non-serving `--check` preflight mode and a `--skip-build` mode
    for already-built artifacts.
- Add deterministic tests for configuration isolation, secret-safe failures,
  build planning, static mounting, liveness, API route precedence, and removal
  of legacy test routes.
- Run a real local single-process smoke against the built frontend, liveness,
  and one deterministic DIAGNOSIS request.
- Update README, implementation status, and a completion report.

## 5. Out of Scope

- No Docker/Compose, Kubernetes, cloud account, TLS certificate, domain, reverse
  proxy, system service, CI/CD, monitoring, autoscaling, or multi-worker setup.
- No provisioning, migration, write, DDL, rebuild, or lifecycle management for
  MySQL, Qdrant, Elasticsearch, Olist data, or Metadata indexes.
- No access to or modification of the original `dw`; only the existing
  `data_agent_v1_dw` configuration is accepted.
- No committed `conf/app_config.yaml`, API key, password, token, cookie,
  credentialed URL, environment value, or complete connection string.
- No change to API request/SSE contracts, NL2SQL, LangGraph, Metric Registry,
  Analyzer, Evidence, report, AOV, or other business behavior.
- No login, tenant, permission, multi-turn conversation, attachment, external
  business action, or frontend redesign.
- No claim of production SLA, high availability, public-internet hardening, or
  managed-service readiness.

## 6. Runtime Contract

Canonical command from the repository root:

```powershell
.\.venv\Scripts\python.exe -m app.scripts.serve
```

The command installs frontend dependencies only when `frontend/node_modules`
is missing, always creates a fresh Vite production build, verifies it, and then
starts `main:app` on `127.0.0.1:8000` by default. `--install` forces `npm ci`;
`--skip-build` requires an existing valid build; `--check` performs preflight
and optional build but does not start Uvicorn.

Runtime routes:

- `/` and frontend assets: built Vue application;
- `/api/query`: unchanged API-001 SSE endpoint;
- `/api/health/live`: process liveness only;
- legacy demonstration routes: not registered.

## 7. Safety and Failure Contract

- Preflight error messages identify only a missing path, missing field, wrong
  database name category, unavailable tool, or failed command stage.
- No configuration value other than the allowed database name may be logged.
- Wrong or missing DW selection stops before frontend build or server import.
- A missing/failed frontend build stops before Uvicorn starts.
- External service availability is tested only by the real smoke after startup;
  the liveness route never claims those dependencies are ready.
- The host defaults to loopback. Binding to a network interface must be an
  explicit operator choice through `--host`.

## 8. Allowed Files

- `specs/DEPLOY-001_single_process_runtime.md`
- `app/deployment.py`
- `app/scripts/serve.py`
- `main.py`
- `test/deployment/test_runtime.py`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `DEPLOY-001_COMPLETION.md`

Any additional file requires a documented direct blocker and must remain
inside DEPLOY-001.

## 9. Local Plan

1. Freeze preflight, mounting, route precedence, and route-removal behavior in
   deployment-focused tests.
2. Implement the dependency-free liveness/static integration and remove only
   the legacy test-router registration from the deployable app.
3. Implement the standard-library/PyYAML launcher without importing app runtime
   modules before preflight and build succeed.
4. Run deployment tests, frontend tests/build, backend regression, Ruff, mypy,
   and documentation contract.
5. Start the launcher in single-process mode and verify frontend HTML,
   liveness semantics, hidden legacy routes, and one real diagnosis SSE flow.
6. Complete secret-safe Diff Review, completion/status records, one commit,
   push, and stop.

## 10. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test\deployment\test_runtime.py
.\.venv\Scripts\python.exe -m app.scripts.serve --check
npm test --prefix frontend
npm run build --prefix frontend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

The real smoke starts the launcher on loopback, reads only public HTTP/SSE
output, stores no response body, and shuts the process down afterward.

## 11. Acceptance Criteria

1. One documented command validates/builds the frontend and starts one FastAPI
   process that serves both frontend and API on the same origin.
2. Preflight stops on missing config or any DW database other than
   `data_agent_v1_dw`, without exposing other configuration values.
3. Dependency installation uses the committed lockfile and occurs only when
   missing or explicitly forced.
4. Missing or invalid frontend build stops startup; API-only imports remain
   valid for testing/development when no build exists.
5. `/` returns the built Vue application and its assets; `/api/query` retains
   priority and the accepted SSE contract.
6. `/api/health/live` reports process liveness without querying or claiming
   readiness of external services.
7. Legacy demo/test routes, including the password-echo route, are absent from
   the deployable app.
8. The host defaults to `127.0.0.1`; non-loopback binding is explicit.
9. Deployment tests, frontend tests/build, and full pytest pass; Ruff/mypy do
   not regress the accepted 22/36 baselines.
10. A real local single-process smoke verifies frontend, liveness, hidden test
    routes, and a deterministic diagnosis terminal event.
11. Diff is limited to allowed DEPLOY-001 files and contains no secret,
    connection string, or persisted response payload.
12. No external service, database, data, index, business logic, or later
    Feature is modified.

## 12. Completion Boundary

After completion report, status update, independent commit, and push, stop.
Public deployment infrastructure, production hardening, monitoring, CI/CD, or
V1.1 capabilities require a new Feature and explicit target decisions.
