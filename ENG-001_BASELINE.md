# ENG-001 Engineering Baseline

## Date and Environment

- Baseline date: 2026-09-04 23:50:30 +08:00
- Time zone: China Standard Time
- Operating system: Microsoft Windows 11 Pro 10.0.26200 (build 26200), AMD64
- Repository root: `D:/py project/data-agent`
- Python: 3.12.3
- Git: 2.48.1.windows.1
- pytest: 9.1.1
- Ruff: 0.16.6
- mypy: 2.3.1 (compiled)

## Repository State

- The repository is an independent Git repository on branch `main`.
- At the start of ENG-001, `main` tracked `origin/main` and the worktree was clean.
- The repository already contained commit `a155659` (`Initial commit`) before ENG-001 execution. This differs from the Feature Spec's older Current State statement that no first commit existed.
- ENG-001 preserves that history and establishes a separate engineering-baseline commit containing this report.
- `conf/app_config.yaml` is ignored and is not tracked.
- `.env`, `.env.*`, `.venv/`, `.tmp/`, Python/tool caches, IDE state, coverage output, and `logs/*.log` are ignored by `.gitignore`.
- No business source file was modified by ENG-001.

## Tool Versions

| Tool | Version |
|---|---|
| Python | 3.12.3 |
| Git | 2.48.1.windows.1 |
| pytest | 9.1.1 |
| Ruff | 0.16.6 |
| mypy | 2.3.1 (compiled) |

## Commands Executed

Required validation commands:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git status --short
git diff --cached --stat
git diff --cached --check
```

Supporting read-only checks covered:

- repository root, branch, history, remote, and worktree state;
- `.gitignore` and `pyproject.toml` contents;
- ignored and tracked status of local configuration, environments, caches, and logs;
- Python, Git, pytest, Ruff, mypy, operating-system, architecture, and time-zone versions;
- Ruff and mypy diagnostic category counts;
- staged-file scope and sensitive-pattern paths without printing matched values.

One initial read-only diagnostic-category aggregation attempt failed because of invalid PowerShell `Sort-Object` syntax. The corrected aggregation command completed successfully. This helper failure did not affect the three required baseline commands or their recorded results.

## Pytest Result

- Command: `.\.venv\Scripts\python.exe -m pytest`
- Exit code: 0
- Result: 4 passed, 0 failed.
- Collected tests: 4.
- Recorded duration: 1.30 seconds.
- Test file: `test/test_value_es_repository.py`.

## Ruff Result

- Command: `.\.venv\Scripts\ruff.exe check .`
- Exit code: 1
- Result: 51 existing diagnostics; 38 reported as automatically fixable.
- No Ruff fixes were applied because ENG-001 records the baseline and must not change business code.

Diagnostic categories:

| Code | Count |
|---|---:|
| I001 | 16 |
| F401 | 11 |
| B008 | 8 |
| UP045 | 7 |
| F541 | 3 |
| BLE001 | 1 |
| DTZ002 | 1 |
| PLC0206 | 1 |
| SIM118 | 1 |
| TRY004 | 1 |
| UP007 | 1 |

## Mypy Result

- Command: `.\.venv\Scripts\mypy.exe app`
- Exit code: 1
- Result: 40 existing errors in 14 files; 58 source files checked.
- No type fixes were applied because ENG-001 records the baseline and must not change business code.

Diagnostic categories:

| Error code | Count |
|---|---:|
| arg-type | 28 |
| union-attr | 3 |
| assignment | 2 |
| misc | 2 |
| dict-item | 1 |
| no-redef | 1 |
| return-value | 1 |
| typeddict-item | 1 |
| valid-type | 1 |

## Known Issues

- Ruff is not green: 51 diagnostics remain in existing source files.
- mypy is not green: 40 errors remain in 14 existing source files.
- The Feature Spec's Current State section is stale regarding the absence of an initial commit; the repository already had `a155659` before this Feature began.
- These issues are intentionally not fixed in ENG-001. Fixing them requires separately scoped work.

## Acceptance Criteria

- [x] Git repository root confirmed.
- [x] Local credentials, logs, caches, and virtual environment are not tracked.
- [x] pytest executed and the real result was recorded.
- [x] Ruff executed and the real result was recorded.
- [x] mypy executed and the real result was recorded.
- [x] Existing failures are visible and categorized.
- [x] No business logic was modified.
- [x] `ENG-001_BASELINE.md` was created.
- [x] Staged content received scope, sensitive-pattern, and diff checks.
- [x] A dedicated local ENG-001 baseline commit was established.
- [x] Completion results are reported without exposing credentials.
- [x] DOC-001 was not started.

## Gate -1 Conclusion

Gate -1 is satisfied: the Git root and ignore boundaries are explicit; pytest, Ruff, and mypy execute reproducibly; existing failures are measured rather than hidden; local sensitive configuration remains excluded; and ENG-001 makes no business-logic change.
