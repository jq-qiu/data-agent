# DOC-002 Status and Capability Truth Sync

## 1. Feature

Synchronize the repository's current status, semantic-grounding boundary, planner boundary,
and resume instructions after SQL-009 without changing runtime behavior or historical evidence.

## 2. Source of Truth

1. Current user authorization to execute the recommended reliability-hardening roadmap.
2. This specification.
3. `IMPLEMENTATION_PLAN.md`.
4. `docs/01_product_scope.md` through `docs/06_evaluation.md`.
5. `AGENTS.md` and the current implementation/report evidence.
6. `README.md`.

## 3. Prerequisite Findings

- Local `HEAD`, `origin/main`, and remote `main` all resolve to SQL-009 commit `5b29094` before
  DOC-002 changes.
- SQL-009 is complete, but its real-model benefit remains unevaluated; SQL-008 `22/30` is still
  the latest real NL2SQL execution result.
- `IMPLEMENTATION_STATUS.md` names SQL-009 at the top but still resumes from SHOWCASE-001 and
  reports an obsolete push/network state at the bottom.
- `docs/03_metadata_and_nl2sql.md` still says controlled semantic retrieval and the LLM planner
  are unimplemented. The semantic-grounding path is connected to the production single-turn API
  through CLARIFY-001; `BoundedPlannerPolicy` and `AnalysisPlanValidator` exist as independent
  components but are not connected to the production diagnosis planning path.

## 4. In Scope

- Record DOC-002 as the current/last completed Feature and EVAL-002 as the next proposed Feature.
- Replace stale SHOWCASE-001 commit/push/resume instructions with the SQL-009/DOC-002 state.
- Align semantic-grounding and planner wording across the implementation plan and Metadata/NL2SQL
  design.
- Add the reliability-hardening sequence without claiming any future Feature is implemented.
- Add deterministic documentation-contract tests for the corrected boundaries.
- Add DOC-002 to the completion-report index and create its completion report.

## 5. Out of Scope

- No Python runtime, frontend, Prompt, configuration, data model, Metric Registry, Golden Dataset,
  or historical evaluation artifact change.
- No NL2SQL evaluator change and no SQL-009 real-model rerun.
- No production LLM planner integration, external semantic-retrieval evaluation, multi-turn work,
  deployment hardening, GitHub visibility change, or remote push.

## 6. Allowed Files

- `specs/DOC-002_status_capability_truth_sync.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/03_metadata_and_nl2sql.md`
- `docs/reports/README.md`
- `docs/reports/DOC-002_COMPLETION.md`
- `test/test_documentation_contract.py`

## 7. Local Plan

1. Freeze current Git, evaluation, grounding, and planner facts in this Spec.
2. Correct the authoritative plan/design/status documents.
3. Add tests that reject the stale capability and resume statements.
4. Run documentation tests, full regression, Ruff, mypy, link checks, and diff review.
5. Write the completion report, create one local commit, and stop without pushing.

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test\test_documentation_contract.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

## 9. Acceptance Criteria

1. Current/last/next Feature statements are mutually consistent.
2. No resume instruction asks to commit or push the already completed SHOWCASE-001 Feature.
3. Push status reflects the verified SQL-009 synchronization and the local-only DOC-002 boundary.
4. Semantic grounding is documented as production API-integrated through CLARIFY-001 while its
   real external retrieval accuracy remains unevaluated.
5. The bounded LLM planner is documented as implemented independently but not production-wired.
6. Future reliability Features are clearly marked proposed/not started.
7. Documentation and full repository validation pass without runtime changes.

## 10. Completion Boundary

After the completion report, local commit, and final status verification, stop. EVAL-002 requires
its own Spec and implementation turn.
