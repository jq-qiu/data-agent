# MVP V1 Implementation Status

## Current Phase

MVP V1 的功能与工程链路已收口，当前进入可靠性加固。SQL-019 已补全已登记 Join 列
并规范等价 Join 键 GROUP BY；真实复测待 SQL-020。

## Current Feature

SQL-019 Group-by Join-key Canonicalization.

## Feature Status (SQL-019 completed)

Completed and validated. Builder 把 registered Join 两端列补入 plan.columns；修复器将
GROUP BY 中等价 Join 键规范成唯一 Plan 分组/显示列。

## Last Completed Feature

SQL-019 Group-by Join-key Canonicalization.

## Next Feature

SQL-020 Post-SQL-019 Real-model Rerun。在同一 Golden 与 Evaluator v3 上重跑
Live/Replay，只记录真实结果与失败，不在评测现场修改 Runtime。

## Last Successful Validation

- SQL-019 join-key canonicalization: schema/repair contract 39 passed；registered Join
  columns always in plan.columns；equivalent GROUP BY key canonicalized；
- SQL-018 real-model rerun: compatible/strict Execution 25/30；Grain 7/15；Trace 18/30；
  Gate 3 true；Live/Replay identical；T03/A02/N04 fixed vs SQL-016；
- SQL-017 overall DWS required columns: schema-linking repair contract 36 passed；
  overall required 只含公式列，region group 仍保留 region_id；历史产物 changed: 0；
- SQL-016 real-model rerun: compatible/strict Execution 24/30；Metric Accuracy 30/30；
  Gate 3 true；Live/Replay identical；N02 new drift；T03/A02 plan-region issue remains；
- SQL-015 unqualified derived/date-id repair: SQL repair contract 18 passed；T03 exact
  shape passes original Validator and Plan；SQL-014/historical artifacts changed: 0；
- SQL-014 real-model rerun: compatible/strict Execution 25/30；Gate 3 true；A02 infra
  lost connection；C02 fixed vs SQL-010；T03/J02/C05 remain；N04 new metric drift；
- SQL-014 Live/Replay: evaluation, safety, gates, dataset, runtime, prompt, model,
  database and cache fields identical；
- SQL-013 structured repair constraints: 21 个相关专项通过；C05 Plan 的表、Calendar、
  Join、Group、Order、Filter 与禁止透视均显式；历史评测产物 changed: 0；
- SQL-012 subquery repair contract: 13 passed；T03 形状通过原 Validator，复杂/越界形状
  全部安全保持；SQL-010 与历史评测产物 changed: 0；
- SQL-011 calendar repair contract: 4 passed；Plan/Alias/反向比较/IN 与安全不变路径覆盖；
  SQL-010 与历史评测产物 changed: 0；
- EVAL-003 classification contract: 11 passed；额外表/列且结果正确仍有主分类；
  SQL-010 与历史评测产物 changed: 0；
- SQL-010 real-model rerun: compatible/strict Execution 26/30；Live/Replay identical；
  Safety 12/12；Gate 3 false because 2 multi-label failures lack a primary category；
- EVAL-002 evaluator contract: 10 passed；full pytest regression: 373 passed；
  Ruff/mypy 0/0；historical evaluation artifacts changed: 0；
- DOC-002 documentation contract: 25 passed；full pytest regression: 371 passed；
  Ruff/mypy 0/0；runtime files and historical evaluation artifacts changed: 0；
- SQL-009 full pytest regression: 369 passed；Ruff/mypy 0/0；
- SQL-009 deterministic semantics: 17 个专项覆盖指标选择、日历类型、Plan 分组/排序/过滤；
- SQL-008 real-model rerun: Execution Accuracy 22/30；Time 5/5；TopN 5/5；Comparison 2/5；
- SQL-008 Live/Replay: 30 条评测主体一致，Safety 12/12 拒绝，Gate 3 passed；
- SQL-007 full pytest regression: 352 passed；Ruff/mypy 0/0；
- SQL-007 replay contract: 3 个专项覆盖数据库标量类型、身份/内容校验和 Live→Replay 一致性；
- SQL-006 implementation complete, 349 pytest passed, Ruff/mypy clean.
- SHOWCASE-001 full pytest regression: 338 passed；frontend 11 passed/build passed；
  Ruff/mypy 0/0；
- SQL-006 full pytest regression: 349 passed；Ruff/mypy 0/0；
- SQL-006 Plan/Validator 新增 9 个专项覆盖 DWS-only 指标列、dim_date、日历对比与事实 COUNT 拒绝；
- SHOWCASE-001 documentation contract: 23 passed；当前事实源 Markdown 断链 0；
  33/34 历史报告保持原 Git blob，INTERVIEW-001 报告仅移除不公开资料说明；
- INTERVIEW-001 deliverables: 2 documents created and linked from README；
- INTERVIEW-001 documentation contract: 22 passed + new assertions；
- INTERVIEW-001 full pytest regression: 338 passed；frontend 11 passed/build passed；Ruff/mypy 0/0；
- PLAN-UI-001 frontend Node tests: 11 passed（含 trace 各阶段提取、未知阶段安全与澄清不泄露）；
- PLAN-UI-001 Vite production build: passed；
- PLAN-UI-001 full pytest regression: 337 passed；Ruff/mypy 保持 0/0；
- PLAN-LLM-001 targeted tests: 20 passed (Validator context matrix + bounded policy unique/LLM/fallback/no-schema);
- PLAN-LLM-001 full pytest regression: 337 passed;
- PLAN-LLM-001 frontend Node tests: 5 passed and Vite production build passed;
- PLAN-LLM-001 V1 planning calls: every golden/unique legal plan returns `DETERMINISTIC` with `model_calls=0`;
- PLAN-LLM-001 Stub multi-option architecture: accepted LLM choice = 1 call; unknown/empty/failure selector fallback <= 1 call and no retry;
- PLAN-LLM-001 real model planning: not evaluated; not wired to production Graph/API;
- PLAN-LLM-001 Ruff/mypy: both clean (0/0) after ENG-002 baseline;
- ENG-002 Ruff: `ruff check .` returns 0 findings;
- ENG-002 mypy: `mypy app` returns `Success: no issues found in 110 source files`;
- ENG-002 full pytest regression: 317 passed after every batch (R、M1、M2、M3、M4);
- ENG-002 frontend Node tests: 5 passed and Vite production build passed;
- ENG-002 client managers: 未初始化访问会抛出明确 RuntimeError，正常 lifespan 初始化路径行为不变；
- ENG-002 hidden issues exposed by M1: `evaluate_diagnosis_v1.py` 候选因素元组与 `evaluate_nl2sql_v1.py` 流 chunk 类型已修复；
- ENG-002 date semantics: `add_extra_context` 仍输出本地日期/星期/季度，仅改为带时区等价写法；
- CLARIFY-001 targeted API tests: 31 passed (includes three binding outcomes, no-data-access guard, logical-candidate sanitization, canonical-question reparse, and existing QUERY/UNSUPPORTED regression);
- CLARIFY-001 frontend Node tests: 5 passed and Vite production build passed; terminal classification now covers clarification and unsupported states;
- CLARIFY-001 full pytest regression: 317 passed;
- CLARIFY-001 real API smoke: the incomplete question `为什么GMV下降？` returns `binding_status=CLARIFICATION_REQUIRED` with `missing_fields=["time"]` and a suggested complete question before diagnosis data access;
- CLARIFY-001 external retrieval evaluation: not run; Qdrant/Elasticsearch behavior remains covered only by SEM-002 Stub contract and is not claimed as real recall accuracy;
- CLARIFY-001 static baselines: repository Ruff was 23 existing diagnostics and mypy was 36 errors in 11 files before ENG-002 cleanup;
- SEM-002 targeted semantic tests: 18 passed;
- SEM-002 related Parser/Capability/Planner/documentation regression: 99 passed;
- SEM-002 full pytest regression: 312 passed;
- SEM-002 fixed evaluation: 12/12 exact binding results, 12/12 status accuracy, 12/12 retrieval-policy matches, 0 physical-Schema leaks, and 0 LLM calls;
- SEM-002 external retrieval evaluation: Stubbed Qdrant/Elasticsearch contract only; real external retrieval not evaluated;
- SEM-002 targeted Ruff and mypy: all changed Python files pass;
- SEM-002 repository Ruff: 23 existing diagnostics, unchanged from SEM-001;
- SEM-002 repository mypy: 36 existing errors in 11 files while checking 110 source files, unchanged from SEM-001;
- SEM-001 documentation contract: 21 passed;
- SEM-001 full pytest regression: 293 passed;
- SEM-001 Ruff: 23 existing diagnostics; no runtime file was changed;
- SEM-001 mypy: 36 existing errors in 11 files while checking 107 source files; no runtime file was changed;
- SEM-001 evaluation: not run because this Feature freezes design only; future semantic-planning metrics are defined in `docs/06_evaluation.md`;
- DOC-001 documentation contract: 19 passed;
- full pytest regression: 23 passed;
- Ruff: 51 existing diagnostics, unchanged from ENG-001;
- mypy: 40 existing errors in 14 files, unchanged from ENG-001;
- DOC-001 commit `8b3795a` is present on `origin/main`;
- DATA-001 read-only prerequisite check: DW database reachable;
- DATA-001 source check: authenticated Kaggle download succeeded; official Version 2 ZIP contains all 9 expected CSV files.
- DATA-001 source validation: 9 files and 1,550,922 rows verified by header, size, SHA-256, encoding, and declared keys;
- DATA-001 controlled integration: all 9 SQLite ODS tables reconciled exactly and a second run reused the successful batch;
- DATA-001 tests: 5 passed; full pytest regression: 28 passed;
- DATA-001 Ruff/mypy: 51 and 40 respectively, unchanged from the engineering baseline;
- DATA-001 target integration: the isolated `data_agent_v1_dw` database contains exactly 1,550,922 rows across 9 source-preserving ODS tables;
- DATA-001 idempotency: the second target run reused the same successful batch and inserted no duplicate data;
- DATA-001 independent read-only reconciliation: all 9 target table counts equal the manifest counts and exactly one successful batch exists.
- DATA-002 tests: 3 passed; full pytest regression: 31 passed;
- DATA-002 Ruff/mypy: 51 and 40 respectively, unchanged from the engineering baseline;
- DATA-002 target build: 6 dimensions, 5 facts, and 2 diagnosis DWS tables built in `data_agent_v1_dw`;
- DATA-002 fact counts: orders 99,441; items 112,650; payments 103,886; deliveries 99,441; reviews 99,224;
- DATA-002 logical foreign keys: all 7 orphan checks returned 0;
- DATA-002 GMV: DWD base, region DWS, and category DWS each equal 13,494,400.74;
- DATA-002 order count: 98,207 valid orders equals the region DWS sum; category order count sums to 99,002 and is not used as the overall count;
- DATA-002 join guard: the unsafe payment-item join produces 14,105,767.00, while both accepted DWS tables remain at the correct 13,494,400.74;
- DATA-002 target idempotency: the second run reused the same successful batch; independent read-only reconciliation passed.
- DATA-003 tests: 4 passed; full pytest regression: 35 passed;
- DATA-003 Ruff/mypy: 51 and 40 respectively, unchanged from the engineering baseline;
- DATA-003 target generation: 10 Ground Truth cases, 10 Business Events, 427 region-analysis rows, and 183 category-analysis rows;
- DATA-003 coverage: 3 event types, 6 single-factor cases, 2 dual-factor cases, 1 stable case, and 1 missing-Evidence degradation case;
- DATA-003 reproducibility: two independent controlled databases produced the same content digest; the second target run reused the same successful batch and digest;
- DATA-003 chain validation: 0 Evidence-chain failures, 0 stable-case failures, and 0 degradation-case failures;
- DATA-003 source integrity: Olist DWD and both accepted DWS summaries remained unchanged; their GMV remains 13,494,400.74;
- Gate 1: all Data Foundation conditions passed with real import, build, generation, and reconciliation evidence.
- META-001 tests: 7 passed; full pytest regression: 42 passed;
- META-001 Ruff/mypy: 51 and 40 respectively, unchanged from the engineering baseline;
- META-001 target build: 15 table records, 103 column records, 9 metric records, and 21 relationship records in independent `meta_v1_*` tables;
- META-001 semantic/value indexes: 148 deterministic Qdrant points and 258 Elasticsearch canonical-value documents;
- META-001 legacy metadata isolation: existing legacy table counts remain 5 tables, 24 columns, 16 metrics, and 27 column-metric links;
- META-001 retrieval evaluation: 12 fixed cases, Metric Hit@1 1.0000, MRR 1.0000, Table Recall@5 0.9792, Column Recall@10 0.9062, Join-key Recall@5 0.8788, and Value Grounding Accuracy 1.0000;
- META-001 context evaluation: Precision 0.3406, Recall 0.9267, average estimated context 182.67 tokens, maximum 216 tokens, and Grain Warning Accuracy 1.0000;
- META-001 source integrity: target database is `data_agent_v1_dw`; accepted valid-order GMV and region DWS GMV both remain 13,494,400.74;
- Gate 2: all frozen metadata thresholds passed with real MySQL, Qdrant, Elasticsearch, and embedding-service evidence.
- SQL-001 targeted tests: 26 passed; full pytest regression: 68 passed;
- SQL-001 Ruff: 31 diagnostics, below the ENG-001 baseline of 51;
- SQL-001 mypy: 36 errors in 11 files, below the ENG-001 baseline of 40 errors in 14 files;
- SQL-001 policy: single read-only SELECT/CTE, registered database/schema/JOIN/functions, no sensitive identifier projection, 500-row cap, 10-second timeout, and at most one revalidated repair;
- SQL-001 real SQL smoke: May 2018 GMV 992,871.75; AOV 145.305393; Top 5 categories returned five rows;
- SQL-001 real LangGraph smoke: `2018年5月GMV是多少` completed V1 retrieval, generation, validation, EXPLAIN, and controlled execution with the same GMV result;
- SQL-001 isolation: only `data_agent_v1_dw` was queried; original `dw`, accepted V1 data, and metadata indexes were not changed.
- SQL-002 targeted tests: 5 passed; full pytest regression: 73 passed;
- SQL-002 Ruff/mypy: 31 diagnostics and 36 errors in 11 files, unchanged from SQL-001 and below ENG-001;
- SQL-002 Golden: 30 cases, six buckets of five, and 30/30 verified reference SQL/result checksums;
- SQL-002 real baseline: SQL Validity 24/30, Executability 24/30, Execution Accuracy 16/30, Metric Accuracy 23/30, JOIN Accuracy 21/30, and Correction Success 5/6;
- SQL-002 structure means: Table Precision 0.7333, Table Recall 0.7417, Column Precision 0.7067, and Column Recall 0.7113;
- SQL-002 safety: 12/12 dangerous probes rejected and dangerous SQL allowed count is 0;
- SQL-002 errors: 2 Metric Recognition, 7 Schema Linking, 3 SQL Generation, and 5 SQL Execution; every failed layer has one primary category;
- SQL-002 latency: mean 228.80 seconds, median 133.66 seconds, maximum 926.29 seconds; Token/cost unavailable and explicitly recorded;
- Gate 3: all frozen evidence conditions passed; the baseline is not claimed as production accuracy.
- ANA-001 targeted tests: 17 passed; full pytest regression: 90 passed;
- ANA-001 Ruff/mypy: 31 diagnostics and 36 errors in 11 files, unchanged from SQL-002;
- ANA-001 fixed evaluation: 18/18 Intent Accuracy, 18/18 Reason Accuracy, and 6/6 recall for each of QUERY, DIAGNOSIS, and UNSUPPORTED;
- ANA-001 safety boundary: 0 diagnosis false positives, 0 low-confidence diagnosis routes, and 6/6 unsupported cases correctly degraded;
- ANA-001 architecture: pure serializable router node and stable branch mapping added without wiring or modifying the existing Query Graph.
- ANA-002 targeted tests: 19 passed; full pytest regression: 109 passed;
- ANA-002 Ruff/mypy: 31 diagnostics and 36 errors in 11 files, unchanged from ANA-001;
- ANA-002 fixed evaluation: 18/18 exact outcomes, 10/10 successful structures, 8/8 structured errors, and 10/10 matches for each of seven parsed fields;
- ANA-002 parsing: adjacent calendar-month boundaries, previous-month derivation, cross-year rollover, Metric, Scope, dimensions, and factors are deterministic;
- ANA-002 safety: wrong Intent, non-GMV target, missing/invalid time, incomplete/non-adjacent baseline, multiple Scope values, and unregistered Scope all stop with structured errors;
- ANA-002 isolation: no external service or database was accessed; Query Graph, NL2SQL, Metadata configuration, data, and API remain unchanged.
- ANA-003 targeted tests: 15 passed; full pytest regression: 124 passed;
- ANA-003 Ruff/mypy: 31 diagnostics and 36 errors in 11 files, unchanged from ANA-002;
- ANA-003 fixed evaluation: 13/13 exact assessments and 8/8 correct degradation cases;
- ANA-003 safety: causal method allowed 0/13 and methods allowed on failed data quality 0/1;
- ANA-003 grain control: region/overall methods require region DWS fields; category-order components are accepted only within a single Category Scope;
- ANA-003 isolation: no external service or database was accessed; Parser, Query Graph, SQL, Metadata configuration, data, and API remain unchanged.
- ANA-004 targeted tests: 20 passed; full pytest regression: 144 passed;
- ANA-004 Ruff/mypy: 31 diagnostics and 36 errors in 11 files, unchanged from ANA-003;
- ANA-004 fixed evaluation: 10/10 exact planning outcomes, 10/10 bounded plans, 10/10 valid dependency structures, and 10/10 parsed parameter reuse;
- ANA-004 safety: unsupported method selections 0 and SQL fields emitted 0;
- ANA-004 planning: at most one task per frozen class; available dimensions and supported candidate factors are grouped without exceeding four tasks;
- ANA-004 isolation: no external service or database was accessed; Parser, Capability Assessor, Query Graph, NL2SQL, Metadata configuration, data, and API remain unchanged.
- ANA-005 targeted tests: 17 passed; ANA-005 plus shared SQL Validator regression: 37 passed; full pytest regression: 161 passed;
- ANA-005 Ruff/mypy: 31 diagnostics and 36 errors in 11 files, unchanged from ANA-004;
- ANA-005 fixed evaluation: 8/8 exact query contracts, 8/8 bound-parameter checks, 8/8 safe traces, 8/8 consecutive Query IDs, 8/8 execution-order checks, and 8/8 hard-limit checks;
- ANA-005 real read-only Smoke: all 5 Synthetic Case D02 queries passed Validator, EXPLAIN, and execution and returned rows from `data_agent_v1_dw`;
- ANA-005 grain control: overall/Region decomposition uses Region DWS Order Count; Category Order Count is selected only under one Category Scope; candidate ratios remain uncomputed additive components;
- ANA-005 safety: State traces contain no raw SQL or bound values, and no write SQL or original `dw` access occurred;
- ANA-005 compatibility: DW Repository gained optional bind parameters; SQL Validator now correctly excludes boolean connectors from callable-function checks without changing the function allowlist.
- ANA-006 targeted tests: 22 passed; full pytest regression: 183 passed;
- ANA-006 Ruff/mypy: 31 diagnostics and 36 errors in 11 files, unchanged from ANA-005;
- ANA-006 fixed evaluation: 10/10 exact numeric scenarios, 10/10 consecutive Analysis Result ID checks, 10/10 complete-lineage checks, 10/10 hard-limit checks, and 10/10 safe-output checks;
- ANA-006 arithmetic: Decimal precision 28, six-decimal derived values, and 0.01 absolute reconciliation tolerance are frozen;
- ANA-006 Shapley: Order Count and AOV contributions reconcile to the GMV delta; zero-order/zero-GMV periods degrade explicitly and inconsistent inputs fail closed;
- ANA-006 dimension control: appearing/disappearing groups and opposing effects are supported; near-zero totals and incomplete group coverage suppress contribution ratios rather than overclaiming;
- ANA-006 candidate control: Conversion, Promotion Coverage, and Inventory Fill Rate are calculated only after aggregation; missing or zero denominators return null with a stable warning;
- ANA-006 safety/isolation: output contains only typed numeric results, input Query IDs, Metric versions, reconciliation, and warnings; no SQL, parameters, trace internals, credentials, LLM calls, database access, or business conclusions were added.
- ANA-007 targeted tests: 26 passed; full pytest regression: 209 passed;
- ANA-007 Ruff/mypy: 31 diagnostics and 36 errors in 11 files, unchanged from ANA-006;
- ANA-007 fixed evaluation: 10/10 exact Evidence/report outcomes, 10/10 consecutive Evidence ID checks, 10/10 complete-lineage checks, and 10/10 safe-output checks;
- ANA-007 claim safety: Unsupported Evidence conclusion count 0 and causal-language violation count 0;
- ANA-007 anomaly Gate: a non-decline blocks all candidate conclusions; missing and conflicting candidate chains remain visible as unsupported/degraded Evidence;
- ANA-007 traceability: every Evidence item and report statement includes Analysis Result IDs, Query IDs, and Metric versions; Report Generator consumes only the Validated Evidence bundle;
- ANA-007 scope boundary: candidate ordering uses deterministic Evidence strength and primary change rate without reading Ground Truth labels, querying a database, or calling an LLM;
- Gate 4: bounded planning/querying, deterministic reconciliation, correct near-zero/missing-Evidence degradation, traceable reports, and zero causal-language violations all passed their frozen component and contract evaluations.
- EVAL-001 targeted tests: 9 passed; full pytest regression: 218 passed;
- EVAL-001 Ruff/mypy: 31 diagnostics and 36 errors in 11 files, unchanged from ANA-007;
- EVAL-001 live isolated-DW regression: 10 attempted, 4 complete successful chains;
- EVAL-001 metrics: Single Cause Hit@1 2/6, Root Cause Recall@3 4/10, Evidence Precision 4/4, Evidence Recall 4/10, and Numeric Consistency 4/10;
- EVAL-001 safety: Unsupported Claim Count 0, causal-language violations 0, and no raw SQL, rows, bind parameters, connection details, or credentials persisted;
- EVAL-001 boundaries: D09 no-decline 1/1; D10 degradation 0/1 because Scope grounding stopped first;
- EVAL-001 errors: 5 Schema Linking and 1 Evidence Validation; every failed case has one primary error category;
- EVAL-001 latency: mean 368.935100 ms, median 293.217500 ms, maximum 1103.221000 ms; Token/cost unavailable because no LLM call was made;
- Gate 5: failed. The baseline was recorded without changing upstream diagnosis algorithms or inflating functional-regression scores.
- FIX-001 focused tests: 71 passed; full pytest regression: 228 passed;
- FIX-001 Ruff/mypy: 31 diagnostics and 36 errors in 11 files, unchanged from EVAL-001;
- FIX-001 isolated Metadata rebuild: 15 tables, 103 columns, 9 metrics, 21 relationships, 148 Qdrant points, and 258 Elasticsearch value documents;
- FIX-001 immutable history: the original EVAL-001 report and three `eval_runs/EVAL-001_v1` artifacts retain their recorded SHA-256 hashes;
- FIX-001 live regression: all 10 D01-D10 chains completed; Single Cause Hit@1 6/6, Root Cause Recall@3 10/10, Evidence Precision/Recall 10/10, and Numeric Consistency 10/10;
- FIX-001 boundary checks: D09 no-decline 1/1, D10 degradation 1/1, maximum reconciliation error 0.000000, and all frozen error-category counts 0;
- FIX-001 claim safety: Unsupported Claim Count 0 and causal-language violations 0;
- FIX-001 latency: mean 697.149600 ms, median 612.514500 ms, maximum 1222.350000 ms; Token/cost unavailable because no LLM call was made;
- Gate 5: passed. Results remain limited to the frozen ten-case Synthetic functional regression.
- API-001 targeted tests: 14 passed; full pytest regression: 242 passed.
- API-001 Ruff: 22 existing diagnostics, below the accepted 31-diagnostic baseline; all API-001 files pass targeted Ruff.
- API-001 mypy: 36 errors in 11 files, unchanged from the accepted baseline; no API-001 mypy finding remains.
- API-001 fixed HTTP/SSE Demo: 6/6 successful terminal results, including 2 QUERY and 4 DIAGNOSIS requests.
- API-001 trace safety: 6/6 cases contain no forbidden public Trace key; all 6 responses used SSE with HTTP 200.
- API-001 diagnosis outcomes: three `DEGRADED` reports correctly reflect unavailable real candidate fields; the scoped São Paulo request returned `NO_DECLINE` for the real Olist period.
- API-001 latency: mean 58,467.103 ms and maximum 208,327.703 ms; external LLM calls dominate the two QUERY requests.
- API-001 isolation: runtime capability and diagnosis accessed only validated read-only aggregates in `data_agent_v1_dw`; no Ground Truth or Synthetic Case ID was used by the API.
- FRONT-001 frontend tests: 5/5 passed; production build succeeded with Vite 7.3.6.
- FRONT-001 dependency audit: 35 packages installed and 0 known npm vulnerabilities reported at installation time.
- FRONT-001 real browser verification: the fixed May 2018 GMV diagnosis reached FastAPI through the Vite proxy and visibly completed with nine successful progress steps, a `DEGRADED` report, Evidence, five limitations, and eight safe public Trace stages.
- FRONT-001 UI safety: diagnosis Markdown is rendered as text nodes without `v-html`; no raw SQL, parameters, credentials, connection details, or persisted response payload was added.
- FRONT-001 backend regression: 242 passed; Ruff remains 22 existing diagnostics and mypy remains 36 errors in 11 files.
- FRONT-001 isolation: no backend Python, business logic, data, database, or the unversioned `D:\py project\data-agent-front` reference was changed.
- DEPLOY-001 targeted tests: 7/7 passed; targeted Ruff and mypy both passed.
- DEPLOY-001 launcher preflight/build: passed for the ignored local configuration, exact `data_agent_v1_dw` selection, npm availability, and Vite production output.
- DEPLOY-001 forced locked install: `--install --check` added 35 packages from the lockfile, reported 0 known vulnerabilities, rebuilt successfully, and did not start the server.
- DEPLOY-001 full regression: 249 passed; frontend tests 5/5 passed and Vite 7.3.6 transformed 11 modules successfully.
- DEPLOY-001 real single-process smoke: root page 200, built JavaScript asset 200, liveness `ok`, API SSE 200, 18 progress events, a `DIAGNOSIS`/`DEGRADED` terminal result, 4 Evidence items, and 8 public Trace stages.
- DEPLOY-001 route boundary: `/hello/...` and `/test_query` returned 404; `POST /login` returned 405 from the static root mount and no legacy test route is registered.
- DEPLOY-001 isolation: no external service, database, data, Metadata index, API contract, diagnosis logic, or frontend interaction behavior was modified.
- DEPLOY-001 static baselines: repository Ruff remains 22 existing diagnostics and mypy remains 36 errors in 11 files while checking 104 source files.
- ROUTE-001 targeted routing/API tests: 59 passed; full pytest regression: 277 passed.
- ROUTE-001 ANA-001 compatibility: 18/18 Intent and reason outcomes unchanged, all three class recalls 1.0, diagnosis false positives 0, and low-confidence diagnosis routes 0.
- ROUTE-001 V2 evaluation: 48/48 Intent and reason outcomes, all three class recalls 1.0, diagnosis false positives 0, and 3 deterministic ambiguity cases marked semantic-fallback eligible.
- ROUTE-001 fallback safety: explicit queries and strong unsupported boundaries make zero classifier calls; timeout, invalid schema, provider failure, low confidence, domain mismatch, and non-GMV diagnosis fail closed with stable reasons.
- ROUTE-001 reported-query smoke: `2018 年各州前三的销售额的商品` enters QUERY with reason `explicit_data_query`; grouped TopN SQL correctness remains unclaimed and deferred.
- ROUTE-001 static baselines: repository Ruff remains 22 existing diagnostics and mypy remains 36 errors in 11 files while checking 106 source files; all ROUTE-001 implementation/test files pass targeted Ruff and introduce no mypy finding.

- SQL-003 targeted tests: 53 passed; full pytest regression: 287 passed.
- SQL-003 policy: `sql-policy-v1.1`; `row_number` is allowlisted only with OVER/PARTITION BY/ORDER BY; `RANK`, `DENSE_RANK`, and `LAG` remain rejected.
- SQL-003 AST safety: `COUNT(*)` validates; `SELECT *`, qualified projection stars, and other star contexts remain rejected; `ts_or_ds_to_date` is allowed only inside `YEAR`/`MONTH`/`DAY`/`QUARTER`.
- SQL-003 CTE/derived-table handling: registered CTE and `FROM (...) t` aliases resolve only to declared output columns; unknown output and physical alias references remain rejected.
- SQL-003 terminal behavior: one failed repair stops and Query Service emits exactly one safe `QUERY_VALIDATION_FAILED` event.
- SQL-003 Golden: four fixed grouped TopN cases; freeze-reference wrote non-null checksums and the non-freeze run passed 4/4.
- SQL-003 compatibility: all 30 SQL-002 references still validate with identical table/column/JOIN traces.
- SQL-003 static baselines: repository Ruff remains 22 existing diagnostics and mypy remains 36 errors in 11 files while checking 107 source files; all SQL-003 implementation/test files pass targeted Ruff and introduce no mypy finding.
- SQL-003 follow-up: rerun failures caused by `YEAR()` parsing to `TsOrDsToDate` and by qualified derived-table aliases are now covered and closed by AST/regression tests; global TopN now allows `ROW_NUMBER() OVER (ORDER BY ...)` without `PARTITION BY`, and numeric position partitions such as `PARTITION BY 1` are rejected.
- FRONT-002: five frontend Node tests passed and Vite production build passed after making the per-request `exchange` object reactive; backend streaming was independently confirmed progressive and was not changed.
- DEMO-001: 289 backend tests, 5 frontend tests, Vite build, and D01/D03/D05 synthetic profile real-smoke passed; D01 complete diagnosis graph generated a report without reading Ground Truth labels.
- REPORT-001: Evidence limitation codes now render as Chinese labels with English codes; 290 backend tests passed and Ruff/mypy remain 22/36.
- REPORT-002: candidate section now separates supported and unsupported candidates and removes duplicate limitation rows; 290 backend tests passed and Ruff/mypy remain 22/36.
- REPORT-002 follow-up: the report now appends the most likely associated candidate using non-causal wording; 291 backend tests passed.
## Last Commit

DOC-002 completion commit. Resolve the immutable local commit ID with `git log -1 --oneline`.

## Push Status

SQL-019 开始前，本地 `HEAD` 为 SQL-018 commit `de9c289`，并已推送至 `origin/main`。
SQL-019 不执行远端推送或仓库可见性变更。

## Known Blockers

SQL-019 已本地补全 Join 列并规范化 J02 等价 Group 键，但尚未真实复测；SQL-018 的
25/30 仍是最近实测。C05 Pivot、N03 缺失 Join/Filter、T05 日历过度 Join 与 TopN 漂移
仍待处理。

## Resume From

1. Read the current task history, `AGENTS.md`, `IMPLEMENTATION_PLAN.md`, and this file.
2. Verify `git status --short --branch`, recent commits, and remote synchronization.
3. Review `specs/SQL-019_group_join_key_canonicalization.md` and
   `docs/reports/SQL-019_COMPLETION.md`.
4. Create and freeze a SQL-020 Spec for the post-SQL-019 Live/Replay rerun.
5. Keep C05/N03/T05 and future reruns outside that evaluation Feature.
