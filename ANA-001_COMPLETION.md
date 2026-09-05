# ANA-001 Completion Report

## Feature

ANA-001 Intent Router. The repository now has a strict, serializable `QUERY | DIAGNOSIS | UNSUPPORTED` decision Schema, deterministic V1 routing policy, LangGraph-compatible node, stable branch mapping, and fixed evaluation evidence. The existing NL2SQL Graph and every later diagnosis stage remain unchanged.

## Changed Files

- `specs/ANA-001_intent_router.md`: frozen scope, priority policy, allowed files, plan, and acceptance criteria;
- `app/diagnosis/__init__.py`: diagnosis package boundary;
- `app/diagnosis/intent.py`: validated Intent Schema, deterministic router, compatible node, and branch mapping;
- `data/evaluation/intent_router_golden_v1.json`: 18 fixed QUERY, DIAGNOSIS, and UNSUPPORTED cases;
- `app/scripts/evaluate_intent_router_v1.py`: deterministic evaluation and report entry point;
- `data/reports/ANA-001_intent_router_evaluation.json`: real per-case routing evidence;
- `test/diagnosis/test_intent_router.py`: Schema, rewrites, boundaries, degradation, serialization, branch, and evaluation tests;
- `IMPLEMENTATION_STATUS.md`, `ANA-001_COMPLETION.md`: completion and next-Feature status.

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_intent_router.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_intent_router_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## Test Results

- ANA-001 targeted tests: 17 passed;
- full pytest regression: 90 passed;
- all Schema, deterministic rewrite, unsupported-boundary, serialization, and branch-mapping tests passed;
- no external model, database, vector store, or search service was used.

## Lint Results

Ruff executed against the full repository and reported 31 existing diagnostics, unchanged from SQL-001/SQL-002 and below the ENG-001 baseline of 51. All ANA-001 Python and test files pass Ruff.

## Type Check Results

mypy executed against `app` and reported 36 existing errors in 11 files, unchanged from SQL-001/SQL-002 and below the ENG-001 baseline of 40 errors in 14 files. A targeted mypy run for all ANA-001 modules passed with no issues.

## Evaluation Results

Dataset `intent-router-golden-v1` contains 18 cases: 6 QUERY, 6 DIAGNOSIS, and 6 UNSUPPORTED.

| Metric | Result |
|---|---:|
| Intent Accuracy | 18/18 (1.0000) |
| Reason Accuracy | 18/18 (1.0000) |
| QUERY Recall | 6/6 (1.0000) |
| DIAGNOSIS Recall | 6/6 (1.0000) |
| UNSUPPORTED Recall | 6/6 (1.0000) |
| Correct Degradation | 6/6 |
| Diagnosis False Positives | 0/12 |
| Low-confidence Diagnosis | 0 |
| Failed Cases | 0 |

This is a fixed functional routing set, not a production-language generalization claim.

## Acceptance Criteria

- PASS: Schema accepts only QUERY, DIAGNOSIS, and UNSUPPORTED; confidence is constrained to 0–1;
- PASS: non-UNSUPPORTED decisions below 0.70 are rejected by Schema validation;
- PASS: equivalent fixed rewrites route consistently;
- PASS: explicit numerical comparison such as “GMV相比4月变化了多少” remains QUERY;
- PASS: explicit GMV reason, decomposition, contribution, and candidate-factor requests route to DIAGNOSIS;
- PASS: future/action, strict-causal, multi-turn anaphora, non-GMV diagnosis, blank, and ambiguous requests degrade to UNSUPPORTED;
- PASS: route output and node update are JSON serializable and contain no external dependency object;
- PASS: stable branch names are available for Existing NL2SQL, future Analysis Question Parser, and unsupported handling;
- PASS: all 18 fixed cases passed with zero diagnosis false positives;
- PASS: full pytest passes and Ruff/mypy remain at the accepted baseline;
- PASS: existing Query graph, SQL behavior, databases, Metadata, and API are unchanged.

## Known Issues

- The router is deliberately high-precision and deterministic; novel phrasings without explicit cues degrade to UNSUPPORTED rather than invoking an LLM. This matches the V1 low-confidence boundary but is not a broad natural-language benchmark.
- The DIAGNOSIS branch is not wired into the production Graph because ANA-002 and later nodes do not yet exist. ANA-001 only freezes the Schema, node, and branch contract.
- Diagnosis is limited to GMV and the frozen Traffic/Promotion/Inventory factor bundle. Non-GMV “why” questions correctly degrade under V1 scope.
- The repository retains 31 Ruff diagnostics and 36 mypy errors in 11 files from the documented engineering baseline.

## Diff Review Summary

- scope review: only ANA-001 Schema/router, fixed evaluation, tests, Spec, report, and status files changed;
- architecture review: the router is pure and stateless; its node emits only serializable request state and holds no Client, Repository, LLM, or Registry;
- boundary review: QUERY behavior is not intercepted, and the future diagnosis branch is named but not executed;
- safety review: prediction/external action, strict causal, multi-turn, unsupported metric diagnosis, and ambiguity paths all stop at UNSUPPORTED;
- security review: the diff contains no API Key, database password, Token, Cookie, or full connection string;
- downstream review: parsing, capability, planning, execution, analysis, Evidence, report, and API features were not implemented;
- whitespace review: `git diff --check` passed.
