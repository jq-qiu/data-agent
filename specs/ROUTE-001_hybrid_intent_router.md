# ROUTE-001 Hybrid Intent Router

## 1. Feature

Expand V1 data-query language coverage and add a bounded semantic fallback
without weakening the accepted QUERY, DIAGNOSIS, and UNSUPPORTED safety
boundaries. Replace the misleading generic unsupported answer with stable,
reason-specific guidance.

## 2. Source of Truth

1. Current user authorization and the reviewed `意图识别.txt` design reference.
2. This specification.
3. `docs/01_product_scope.md` and `docs/05_agent_workflow.md`.
4. `specs/ANA-001_intent_router.md` and `ANA-001_COMPLETION.md`.
5. `specs/API-001_minimal_demo.md` and `API-001_COMPLETION.md`.
6. `IMPLEMENTATION_PLAN.md`, `AGENTS.md`, `README.md`, and
   `IMPLEMENTATION_STATUS.md`.
7. Current Intent Router, API dependency, Query Service, Metadata catalog, and
   fixed evaluation behavior.

The desktop text file is an advisory reference, not a repository fact source.
Its two-intent model, fixed rule/LLM weights, China-region example, and broad
classification of trend/decline as analysis are not accepted into V1.

## 3. Prerequisite Findings

- DEPLOY-001 is complete at commit `ce1d9d4`; local `main` and `origin/main`
  match and the worktree is clean.
- The reported question `2018 年各州前三的销售额的商品` is a V1 TopN QUERY,
  but the existing router returns `UNSUPPORTED/ambiguous_or_incomplete_question`
  because `前三` is absent from its fixed query-term list.
- Deterministic probes found the same false-negative class for `前3`, `Top 3`,
  bottom-N, maximum/minimum, aggregate, year-over-year, month-over-month,
  ratio, distribution, and threshold phrasing.
- Query Service routes before entering the NL2SQL graph. An UNSUPPORTED decision
  therefore means the SQL-generation prompt is never called.
- The accepted catalog and JOIN registry can represent State, Product ID,
  Category, Order, Customer, and item-price GMV. Correct SQL for grouped TopN
  is a separate downstream concern and is not proven by routing alone.
- ANA-001 deliberately had no LLM dependency. ROUTE-001 supersedes only that
  constraint for unresolved ambiguity while retaining the original strong
  rules and synchronous deterministic interface.

## 4. In Scope

- Preserve the three frozen intents and `IntentDecision` validation.
- Extract deterministic domain/query/diagnosis signals after NFKC/casefold
  normalization.
- Expand high-confidence QUERY coverage for:
  - Top/Bottom N, Chinese or Arabic ordinals, ranking, and extrema;
  - aggregates, totals, distribution, median, and breakdown/grouping;
  - comparison, year-over-year, month-over-month, rate/change expressions;
  - share/composition expressions;
  - threshold and range filters;
  - customer, seller, product, category, order, payment, delivery, and review
    entities already inside the V1 open-query scope;
  - common English query operations when paired with a registered domain term.
- Build metric aliases from the accepted Metadata catalog when the router is
  created for the API; retain a frozen safe default vocabulary for standalone
  tests, graph nodes, and deterministic evaluation.
- Preserve strong-rule precedence for empty input, multi-turn anaphora,
  prediction/external action, and strict causal requests.
- Require a GMV diagnosis operator, or the accepted multi-factor bundle, before
  entering DIAGNOSIS. Decline/trend/change alone remain QUERY or ambiguous.
- Add an async semantic fallback only after deterministic routing returns the
  stable ambiguity reason.
- Constrain the semantic classifier to a Pydantic result with the three intents
  and confidence. Apply a hard timeout, fail closed on errors/invalid output,
  require a registered domain signal for QUERY, require GMV for DIAGNOSIS, and
  retain the existing low-confidence degradation rule.
- Keep the LLM client inside the API dependency container through a dedicated
  classifier adapter; do not place it in Agent State or a Repository.
- Map UNSUPPORTED reason codes to concise Chinese guidance without returning
  model output, exception text, prompts, credentials, or runtime objects.
- Add a new immutable V2 routing Golden/evaluator/report. Do not rewrite
  ANA-001 V1 evidence.
- Add deterministic, stubbed-fallback, API-message, safety, and evaluation
  tests, then update README/status/completion records.

## 5. Out of Scope

- No modification to the SQL-generation prompt, NL2SQL graph, retrieval,
  Metadata content/indexes, SQL Validator, SQL repair, or query execution.
- No implementation or accuracy claim for grouped TopN SQL, window functions,
  tie-breaking,同比/环比 formulas, or other SQL-003 behavior.
- No change to GMV, AOV, Order Count, dimension contribution, Analyzer,
  Evidence, report wording, capability assessment, or diagnosis planning.
- No new diagnosis target beyond GMV and the accepted factor bundle.
- No database, data, DDL, index, external-service, frontend, deployment, login,
  multi-turn, prediction, execution action, or strict causal capability.
- No fixed numeric fusion between rule and LLM scores. Strong rules always win;
  semantic classification is fallback-only.
- No real LLM call in ordinary unit tests or the deterministic routing report.
- No storage of user questions, classifier prompts/responses, credentials, or
  external model payloads in the Golden/report.

## 6. Routing Contract

Priority:

```text
Strong UNSUPPORTED boundary
  → explicit GMV/factor DIAGNOSIS
  → registered-domain + explicit QUERY operation
  → bounded semantic fallback
  → validated decision or safe UNSUPPORTED
```

`IntentRouter.route(question)` remains deterministic and synchronous.
`IntentRouter.aroute(question)` calls a configured classifier only when the
synchronous result is `UNSUPPORTED/ambiguous_or_incomplete_question`.

Semantic fallback rules:

- timeout: at most 8 seconds;
- accepted confidence: at least 0.80;
- QUERY requires a recognized metric/entity/dimension signal;
- DIAGNOSIS requires a GMV signal;
- classifier error, timeout, invalid output, low confidence, or domain mismatch
  returns a stable UNSUPPORTED reason without exception details.

## 7. Unsupported Guidance Contract

The public result keeps `intent`, Trace, and reason in `limitations`, but
selects the answer from a frozen reason-to-guidance mapping. At minimum it
distinguishes empty, anaphora, future/external action, strict causal request,
non-GMV diagnosis, low-confidence semantic result, unavailable classifier,
domain mismatch, and ambiguous/incomplete wording.

## 8. Allowed Files

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

Any additional file requires a documented direct blocker and must remain
inside ROUTE-001.

## 9. Local Plan

1. Freeze new query paraphrases, diagnosis/query conflicts, strong boundaries,
   and semantic-fallback validation with tests and a V2 Golden.
2. Refactor the router into safe signal extraction plus deterministic priority
   rules while preserving the accepted synchronous API.
3. Add the structured LLM classifier adapter and fallback-only async path.
4. Inject the hybrid router into Query Service through API dependencies and
   add reason-specific unsupported guidance.
5. Run V1 compatibility plus V2 evaluation, targeted/API/full tests, Ruff,
   mypy, and documentation checks.
6. Perform a real API routing smoke that proves the reported question enters
   QUERY without persisting or requiring successful SQL-003 output.
7. Complete secret-safe Diff Review, completion/status records, one commit,
   push, and stop before SQL-003.

## 10. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test\diagnosis\test_intent_router.py test\api\test_query_api.py
.\.venv\Scripts\python.exe -c "from app.scripts.evaluate_intent_router_v1 import evaluate; print(evaluate()['failure_count'])"
.\.venv\Scripts\python.exe -m app.scripts.evaluate_intent_router_v2
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

## 11. Acceptance Criteria

1. The reported question and frozen TopN/aggregate/comparison/share/filter/entity
   paraphrases route to QUERY without calling the semantic classifier.
2. Existing ANA-001 V1 cases retain exact Intent and reason behavior.
3. Explicit GMV/factor diagnosis remains DIAGNOSIS; change, decline, trend, and
   ranking phrasing do not become false diagnosis by themselves.
4. Strong unsupported rules always win and never invoke the classifier.
5. Only deterministic ambiguity may call the classifier, at most once and
   within the hard timeout.
6. Fallback output is Schema validated; low confidence, failure, non-domain
   QUERY, and non-GMV DIAGNOSIS fail closed with stable reasons.
7. API production wiring obtains the classifier from the dependency container;
   unit tests use stubs and no Agent State/Repository stores an LLM.
8. Public unsupported answers are reason-specific and contain no exception,
   prompt, model response, credential, SQL, or connection detail.
9. V2 evaluation reports real Intent/reason accuracy, per-class recall,
   diagnosis false positives, classifier-call eligibility, and failures.
10. Targeted/full pytest pass and Ruff/mypy do not regress the accepted 22/36
    baselines.
11. Diff is limited to allowed ROUTE-001 files and contains no secret, raw
    external response, user payload, or rewritten historical V1 report.
12. SQL generation, business logic, data, databases, indexes, frontend,
    deployment, and SQL-003 remain unchanged.

## 12. Completion Boundary

After completion report, status update, independent commit, and push, stop.
Grouped TopN SQL correctness and any SQL prompt change require SQL-003.
