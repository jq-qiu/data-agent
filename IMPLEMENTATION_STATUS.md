# MVP V1 Implementation Status

## Current Phase

Diagnosis Agent implementation in progress; Gate 3 complete.

## Current Feature

ANA-004 Analysis Planner.

## Feature Status

Completed. A strict, deterministic planner now converts accepted Parsed Questions and Capability Assessments into at most four ordered tasks behind a Period Comparison gate. Ten fixed cases passed with 10/10 exact plans, 10/10 bounded task counts, 10/10 valid dependency structures, zero unsupported method selections, and zero SQL fields. The diagnosis Graph remains unwired until later stages exist. The status is valid when the ANA-004 completion commit containing this file is present on `origin/main`.

## Last Completed Feature

ANA-004 Analysis Planner.

## Next Feature

ANA-005 Controlled Query Builder.

## Last Successful Validation

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

## Last Commit

The ANA-004 completion commit containing this file. Resolve the immutable commit ID with `git log -1 --oneline` when resuming.

## Push Status

Pushed to `origin/main`. If Git metadata disagrees, Git is authoritative and this field must be corrected before starting another Feature.

## Known Blockers

None blocking ANA-005. ANA-003 still consumes an injected request-scoped Data Profile; runtime construction is deferred. ANA-004 produces intent-only tasks and intentionally contains no query specification or SQL. SQL-002 baseline limitations and the Qdrant compatibility warning remain documented. The repository reports 31 Ruff diagnostics and 36 mypy errors in 11 files.

## Resume From

1. Read the current task history, `AGENTS.md`, `IMPLEMENTATION_PLAN.md`, and this file.
2. Verify `git status --short --branch`, recent commits, and remote synchronization.
3. Query the current Codex usage limit and update the Heartbeat to two minutes after the latest `resetsAt`.
4. Create and fully read `specs/ANA-005_controlled_query_builder.md` and its direct sources before implementation.
5. Inspect the accepted AnalysisTask contract, Metadata Catalog, Metric Registry, grain invariants, and SQL safety boundary without implementing task execution or analysis mathematics.
6. Implement ANA-005 only, run its Registry, grain, read-only, and no-hallucination tests, produce a completion report, create an independent commit, and push.
