# SQL-002 Completion Report

## Feature

SQL-002 NL2SQL Evaluation. A frozen 30-case Olist V1 Golden Dataset, deterministic evaluator, safety probes, versioned run artifacts, and the first real LangGraph baseline now provide Gate 3 evidence. No SQL-001 runtime behavior or downstream diagnosis/API logic was changed.

## Changed Files

- `specs/SQL-002_nl2sql_evaluation.md`: frozen Feature scope, Gate definition, plan, and acceptance criteria;
- `data/evaluation/nl2sql_golden_v1.json`: 30 fixed cases, five each for simple, aggregate, time, JOIN, TopN, and comparison queries, with frozen reference checksums;
- `app/nl2sql/evaluation.py`: Golden contract, result normalization/checksums, layered metrics, safety probes, failure classification, and artifact generation;
- `app/scripts/evaluate_nl2sql_v1.py`: real isolated-DW reference and LangGraph evaluation entry point;
- `data/reports/SQL-002_nl2sql_evaluation.json`: complete machine-readable baseline;
- `eval_runs/sql-002-baseline-v1/summary.json`: versioned run summary;
- `eval_runs/sql-002-baseline-v1/nl2sql_results.csv`: 30 per-case records;
- `eval_runs/sql-002-baseline-v1/error_analysis.md`: fixed-category failure analysis;
- `test/nl2sql/test_evaluation.py`: dataset, trace, checksum, ordering, safety, and metric tests;
- `IMPLEMENTATION_STATUS.md`, `SQL-002_COMPLETION.md`: Gate 3 status and completion evidence.

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/nl2sql/test_evaluation.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_nl2sql_v1 --freeze-reference
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

The live evaluation validated, explained, and executed reference and candidate SQL only against `data_agent_v1_dw`. No credential or connection string was printed or saved.

## Test Results

- SQL-002 targeted tests: 5 passed;
- full pytest regression: 73 passed;
- dataset contract: exactly 30 unique cases with six buckets of five;
- reference contract: 30/30 reference SQL statements matched their declared table, column, and JOIN traces;
- reference execution: 30/30 passed Validator, EXPLAIN, execution, and frozen result-checksum verification;
- safety regression: 12/12 dangerous probes rejected, 0 allowed.

## Lint Results

Ruff executed against the full repository and reported 31 existing diagnostics, unchanged from the SQL-001 baseline and below the ENG-001 baseline of 51. All SQL-002 Python and test files pass Ruff.

## Type Check Results

mypy executed against `app` and reported 36 existing errors in 11 files, unchanged from SQL-001 and below the ENG-001 baseline of 40 errors in 14 files. The SQL-002 evaluator and entry point add no mypy errors.

## Evaluation Results

Run `sql-002-baseline-v1` used source commit `76ff3c1`, dataset `nl2sql-golden-v1`, metadata `metadata-v1`, policy `sql-policy-v1`, the frozen prompt bundle, and model `deepseek-ai/DeepSeek-V4-Pro` at temperature 0.

| Metric | Result | Count |
|---|---:|---:|
| SQL Validity Rate | 0.8000 | 24/30 |
| SQL Executability | 0.8000 | 24/30 |
| Execution Accuracy | 0.5333 | 16/30 |
| Metric Accuracy | 0.7667 | 23/30 |
| Table Precision | 0.7333 | mean |
| Table Recall | 0.7417 | mean |
| Column Precision | 0.7067 | mean |
| Column Recall | 0.7113 | mean |
| JOIN Accuracy | 0.7000 | 21/30 exact |
| Grain Safety Rate | 0.8000 | 24/30 |
| Correction Success Rate | 0.8333 | 5/6 |
| Dangerous SQL Allowed | 0 | 0/12 |

Bucket Execution Accuracy: simple 0.8000, aggregate 1.0000, time 0.4000, JOIN 0.0000, TopN 0.6000, and comparison 0.4000. Mean latency was 228.80 seconds, median 133.66 seconds, and maximum 926.29 seconds. The current graph does not expose token usage, so Token and cost are explicitly recorded as unavailable rather than estimated.

Primary error classification across the 30 cases: Metadata Retrieval 0, Metric Recognition 2, Schema Linking 7, SQL Generation 3, and SQL Execution 5. Every case with a failed layer has exactly one recorded primary category. Several structurally different candidates returned the correct result but remain flagged by strict table/column/JOIN expectations; Execution Accuracy remains result-set based.

Gate 3 passed its frozen evidence conditions: all 30 cases were run and recorded, all required metrics were reported, references were verified 30/30, dangerous SQL allowed was 0, and every failure was classified. No post-hoc accuracy threshold was invented for this first baseline.

## Acceptance Criteria

- PASS: Golden contains exactly 30 unique cases and six balanced buckets;
- PASS: every case contains expected metric/table/column/JOIN facts, reference SQL, frozen result checksum, risk tags, and ordering semantics;
- PASS: 30/30 reference SQL and checksums passed on the isolated DW;
- PASS: comparison ignores SQL text, column order, aliases, Decimal representation, and non-semantic row order while preserving configured TopN/order semantics;
- PASS: all 30 live LangGraph attempts have a final per-case record;
- PASS: all required execution, structure, safety, and correction metrics are real and versioned;
- PASS: 12/12 dangerous SQL probes were rejected;
- PASS: every failed layer has a fixed error category and reviewable detail;
- PASS: reproducibility metadata includes source commit, dataset/metadata/policy/prompt versions, model parameters, latency, and explicit Token/cost unavailability;
- PASS: pytest passes and Ruff/mypy do not exceed SQL-001 baselines;
- PASS: no SQL-001 runtime, diagnosis, AOV decomposition, or API behavior changed.

## Known Issues

- Five candidate runs ended with transient lost-MySQL-connection errors during an unusually long external-model run and are honestly counted as SQL Execution errors. SQL-002 records the baseline and does not modify SQL-001 lifecycle behavior.
- Initial quality is intentionally not presented as a release-level production score: Execution Accuracy is 16/30, with the weakest buckets being JOIN and time/comparison.
- Strict structure scoring flags valid alternate plans such as DWD versus DWS even when normalized results match; per-case execution and structure metrics remain separate in the report.
- One simple result was counted order-sensitive because its frozen reference includes `ORDER BY`; this is retained as part of the immutable first baseline and should be reconsidered only in a future versioned dataset.
- Token usage and cost are unavailable because the current graph does not expose model usage metadata.
- Qdrant client 1.16.2 continues to warn about server 1.19.0 compatibility; retrieval completed during the run.
- The repository retains 31 Ruff diagnostics and 36 mypy errors in 11 files from the documented engineering baseline.

## Diff Review Summary

- scope review: only SQL-002 dataset, evaluator, run artifacts, tests, Spec, report, and status files changed;
- runtime review: SQL-001 retrieval, prompts, Validator, repair routing, execution, Agent graph, and API were not modified;
- evaluation review: reference checksums are frozen from validated read-only SQL; candidate accuracy uses normalized results rather than SQL string equality;
- failure review: no failed case was removed, retried away, or relabeled outside the fixed taxonomy;
- data safety review: all live access targeted only `data_agent_v1_dw`; original `dw`, V1 data, and metadata indexes were not written;
- security review: artifacts and diff contain no API Key, database password, Token, Cookie, or full connection string;
- downstream review: ANA-001 and all later diagnosis/API features remain unimplemented;
- whitespace review: `git diff --check` passed.
