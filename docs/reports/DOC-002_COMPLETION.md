# DOC-002 Status and Capability Truth Sync - Completion Report

## Feature

DOC-002 Status and Capability Truth Sync. Synchronize the SQL-009 post-completion status,
Semantic Grounding and planner production boundaries, reliability-hardening roadmap, and resume
instructions without changing runtime behavior or historical evaluation evidence.

## Changed Files

- `specs/DOC-002_status_capability_truth_sync.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/03_metadata_and_nl2sql.md`
- `docs/reports/README.md`
- `docs/reports/DOC-002_COMPLETION.md`
- `test/test_documentation_contract.py`

## Added Dependencies

- 无。

## Commands Executed

- Git worktree/history and remote synchronization inspection
- Authoritative documentation and current implementation-boundary inspection
- Documentation-contract pytest
- Full pytest regression
- Repository Ruff and mypy
- `git diff --check`
- Changed-file and historical-artifact diff review

## Test Results

- Documentation contract: 25 passed.
- Final full pytest regression: 371 passed in 15.18 seconds.
- Two new contract tests verify Current/Last/Next/Resume consistency and the production grounding/
  planner boundary.

## Lint Results

- Repository Ruff: 0 findings.
- `git diff --check`: no whitespace errors.

## Type Check Results

- mypy: Success, no issues found in 114 source files.
- Existing informational notes about unchecked untyped client-manager method bodies remain notes,
  not mypy errors, and this Feature does not modify those runtime files.

## Evaluation Results

- 未评测；本 Feature 不运行外部模型、检索服务或数据库评测。
- SQL-008 `22/30` 仍是最近一次真实 NL2SQL Execution Accuracy。
- SQL-009 的真实模型收益仍未评测。

## Acceptance Criteria

1. Passed: Current Feature and Last Completed Feature both identify DOC-002; Next Feature identifies
   EVAL-002 as planned/not started.
2. Passed: no resume instruction asks to commit or push SHOWCASE-001.
3. Passed: status records the verified SQL-009 synchronization and local-only DOC-002 boundary.
4. Passed: production single-turn Semantic Grounding and its unevaluated real external recall are
   documented separately.
5. Passed: `BoundedPlannerPolicy`/`AnalysisPlanValidator` are documented as implemented but not
   production-wired or real-model evaluated.
6. Passed: EVAL-002 and SQL-010 are explicitly proposed/not started; no future accuracy is claimed.
7. Passed: documentation/full pytest/Ruff/mypy validation completed without runtime changes.

## Known Issues

- EVAL-002 尚未开始；当前 NL2SQL 结果列语义、Grain、Correction 和 Replay 身份评测
  可信度问题未在本 Feature 修复。
- SQL-010 尚未开始；不得宣称 SQL-009 提升了 `22/30`。
- 诊断 Semantic Grounder 的真实外部召回和真实 LLM Planner 仍未评测。

## Diff Review Summary

- The diff is limited to the seven DOC-002 allowed files.
- No file under `app/`, `frontend/`, `prompts/`, `conf/`, `data/`, or `eval_runs/` changed.
- No historical completion report or evaluation artifact changed.
- The only executable change is two documentation-contract tests; production behavior is unchanged.
- Final review found no broken authoritative-document link or whitespace error.
