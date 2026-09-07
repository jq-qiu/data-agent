# ROUTE-001 Completion Report

## Feature

ROUTE-001 Hybrid Intent Router. The V1 router now recognizes common analytical-query wording deterministically and uses a bounded structured semantic classifier only for unresolved ambiguity, while preserving strong safety boundaries and the three accepted intents.

## Changed Files

- `specs/ROUTE-001_hybrid_intent_router.md`
- `app/diagnosis/intent.py`
- `app/diagnosis/intent_classifier.py`
- `prompts/classify_intent.prompt`
- `app/api/dependencies.py`
- `app/services/query_service.py`
- `test/diagnosis/test_intent_router.py`
- `test/api/test_query_api.py`
- `data/evaluation/intent_router_golden_v2.json`
- `app/scripts/evaluate_intent_router_v2.py`
- `data/reports/ROUTE-001_intent_router_evaluation.json`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `ROUTE-001_COMPLETION.md`

## Added Dependencies

None. The implementation uses the existing Pydantic, LangChain, and configured chat-model dependencies.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test\diagnosis\test_intent_router.py test\api\test_query_api.py -q
.\.venv\Scripts\python.exe -c "import json; from app.scripts.evaluate_intent_router_v1 import evaluate; r=evaluate(); print(json.dumps({'case_count':r['case_count'],'metrics':r['metrics'],'failure_count':r['failure_count']}, ensure_ascii=False))"
.\.venv\Scripts\python.exe -m app.scripts.evaluate_intent_router_v2
.\.venv\Scripts\ruff.exe check app\diagnosis\intent.py app\diagnosis\intent_classifier.py app\api\dependencies.py app\services\query_service.py test\diagnosis\test_intent_router.py test\api\test_query_api.py app\scripts\evaluate_intent_router_v2.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

The V1 evaluator was invoked through its read-only `evaluate()` function so the historical ANA-001 report was not regenerated.

## Test Results

- ROUTE-001 focused diagnosis/API suite: 59 passed, 0 failed in 10.71 seconds.
- Full backend regression: 277 passed, 0 failed in 13.54 seconds.
- Tests cover expanded query expressions, the reported grouped-TopN wording, V1/V2 deterministic evaluations, zero-call strong paths, one-call semantic fallback, schema validation, confidence/domain/GMV gates, timeout/provider failure, query handoff, and public guidance.

## Lint Results

- All ROUTE-001 implementation, evaluator, and test files pass targeted Ruff.
- Repository Ruff reports 22 existing diagnostics, unchanged from DEPLOY-001.

## Type Check Results

- No mypy finding points to a ROUTE-001 implementation file.
- Repository mypy reports 36 existing errors in 11 files while checking 106 source files, unchanged in count and affected-file count from DEPLOY-001. The source-file count increased by the two new Python modules.

## Evaluation Results

- ANA-001 V1 compatibility: 18 cases; Intent Accuracy 1.0; Reason Accuracy 1.0; QUERY/DIAGNOSIS/UNSUPPORTED recall each 1.0; diagnosis false positives 0; low-confidence diagnosis count 0; failures 0.
- ROUTE-001 V2 deterministic evaluation: 48 cases (24 QUERY, 12 DIAGNOSIS, 12 UNSUPPORTED); Intent Accuracy 1.0; Reason Accuracy 1.0; all class recalls 1.0; diagnosis false positives 0; failures 0.
- Three deliberately ambiguous V2 cases remain eligible for semantic fallback. The deterministic report makes no external LLM accuracy or availability claim.
- The reported wording enters the QUERY branch with `explicit_data_query` and does not call the semantic classifier. Grouped TopN SQL generation and execution accuracy were not evaluated and remain outside this Feature.

## Acceptance Criteria

1. Passed: the reported wording plus frozen Top/Bottom N, aggregate, comparison, share, filter, and entity paraphrases route QUERY without classifier calls.
2. Passed: all 18 ANA-001 V1 Intent/reason results remain exact.
3. Passed: explicit GMV/factor diagnosis remains DIAGNOSIS; query change/trend/ranking language does not become diagnosis by itself.
4. Passed: empty, anaphora, future/action, and strict-causal boundaries win deterministically and skip the classifier.
5. Passed: only deterministic ambiguity invokes the classifier, at most once, with a configurable hard timeout capped at eight seconds.
6. Passed: structured-output validation, 0.80 confidence, registered-domain QUERY, and GMV DIAGNOSIS gates fail closed with stable reasons.
7. Passed: the API dependency container builds the catalog-backed classifier/router; Agent State and repositories remain free of LLM runtime objects.
8. Passed: unsupported results use reason-specific frozen guidance and do not expose prompt, response, exception, credential, SQL, or connection details.
9. Passed: the immutable V2 evaluation records real Intent/reason accuracy, recall, diagnosis false positives, eligibility, and failures.
10. Passed: focused/full pytest pass and Ruff/mypy retain the accepted 22/36 baselines.
11. Passed: the final diff is limited to the 14 allowed ROUTE-001 files and does not rewrite historical V1 evidence.
12. Passed: SQL generation, NL2SQL graph, AOV/GMV business logic, diagnosis calculations, data, database, indexes, frontend, and deployment remain unchanged.

## Known Issues

- Semantic fallback depends on the configured external chat model at runtime; it safely degrades when unavailable, and no real-model classification accuracy was evaluated in this Feature.
- A QUERY route proves only routing. Complex grouped TopN, tie-breaking,同比/环比 formula, and other SQL generation correctness require a separately authorized SQL-003 Feature.
- The repository retains 22 Ruff diagnostics and 36 mypy errors in 11 legacy files.

## Diff Review Summary

The implementation keeps strong rules first, derives production domain vocabulary from accepted Metadata, preserves the synchronous deterministic router for existing graph use, and adds an async fallback only at the API service boundary. Model output is schema-validated and cannot override unsupported boundaries or bypass domain/GMV gates. The V2 report stores fixed case IDs and outcomes rather than prompts or external payloads. Final review found no SQL prompt, NL2SQL graph, metric formula, Analyzer, Evidence, database, data, frontend, deployment, or historical V1-report modification. Commit and push synchronization are verified separately after this report is committed.
