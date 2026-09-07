# FIX-001 Completion Report

## Feature

FIX-001 Gate 5 Remediation completed. The Metadata Catalog now covers every
real Scope value used by the frozen D01-D10 Synthetic configuration, and
Evidence/Report lineage preserves the difference between overall
`order_count` and single-Category `category_order_count`. The unchanged
diagnosis regression now completes 10/10 cases and passes Gate 5.

## Changed Files

- `specs/FIX-001_gate_5_remediation.md`
- `conf/meta_config.yaml`
- `app/diagnosis/evidence.py`
- `app/diagnosis/report.py`
- `app/scripts/evaluate_diagnosis_v1.py`
- `test/metadata/test_catalog.py`
- `test/diagnosis/test_analysis_question_parser.py`
- `test/diagnosis/test_evidence_report.py`
- `data/reports/FIX-001_gate_5_regression.json`
- `eval_runs/FIX-001_v1/summary.json`
- `eval_runs/FIX-001_v1/diagnosis_results.csv`
- `eval_runs/FIX-001_v1/error_analysis.md`
- `FIX-001_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/metadata/test_catalog.py test/diagnosis/test_analysis_question_parser.py test/diagnosis/test_evidence_report.py test/evaluation/test_diagnosis_regression.py -q
.\.venv\Scripts\python.exe -m app.scripts.build_meta_knowledge_v1
.\.venv\Scripts\python.exe -m app.scripts.evaluate_diagnosis_v1 --report data/reports/FIX-001_gate_5_regression.json --run-dir eval_runs/FIX-001_v1
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

Read-only prerequisite probes also verified that `SC`, `PA`, `ES`,
`eletrodomesticos`, and `cool_stuff` exist in the isolated warehouse. SHA-256
checks and Git diff inspection verified that the original EVAL-001 baseline
artifacts were not changed.

## Test Results

- FIX-001 focused Metadata, Parser, Evidence, and EVAL tests: 71 passed.
- Full regression: 228 passed.

## Lint Results

- All FIX-001 implementation and test files pass targeted Ruff.
- Repository-wide Ruff reports 31 existing diagnostics, unchanged from the
  accepted EVAL-001 baseline.

## Type Check Results

- FIX-001 Evidence and Report modules introduce no targeted mypy finding.
- Targeting the live evaluator also reaches three accepted dependency errors in
  `app/conf/app_config.py` and
  `app/repositories/mysql/dw/dw_mysql_repository.py`.
- Repository-wide mypy reports 36 existing errors in 11 files, unchanged from
  the accepted EVAL-001 baseline.

## Evaluation Results

- D01-D10 complete successful chains: 10/10.
- Single Cause Hit@1: 6/6.
- Root Cause Recall@3: 10/10.
- Evidence Precision: 10/10; Evidence Recall: 10/10.
- Numeric Consistency: 10/10.
- Maximum contribution reconciliation error: 0.000000.
- Unsupported Claim Count: 0.
- Causal-language Violation Count: 0.
- D09 no-decline correctness: 1/1.
- D10 correct degradation: 1/1.
- All frozen error-category counts: 0.
- Latency: mean 697.149600 ms, median 612.514500 ms, maximum 1222.350000 ms.
- Token usage and cost: unavailable because the controlled run made no LLM call.
- Gate 5: passed.

These are functional-regression results for the frozen Synthetic cases, not a
production accuracy or generalization claim.

## Acceptance Criteria

- The five previously missing canonical values were confirmed in
  `data_agent_v1_dw`, added to the Metadata Catalog, and resolved exactly by the
  deterministic Parser.
- Unknown Scope rejection and all prior aliases remain covered by tests.
- The isolated V1 Metadata registry/index rebuild succeeded with 15 tables,
  103 columns, 9 metrics, 21 relationships, 148 Qdrant points, and 258
  Elasticsearch value documents.
- Overall/Region decomposition requires exactly `gmv + order_count + aov`;
  single-Category decomposition requires exactly
  `gmv + category_order_count`.
- Candidate Evidence facts preserve `category_order_count` identity under a
  Category Scope, and Report lookup consumes that validated identity.
- Cross-grain decomposition and candidate lineage fail closed in focused tests.
- D01-D10 questions, expected Scope, Ground Truth, Synthetic data, evaluator
  scoring, and Gate thresholds were not changed.
- The original EVAL-001 failing baseline remains unchanged; FIX-001 results are
  stored in a separate report and run directory.
- Full pytest passes and Ruff/mypy remain at the accepted 31/36 baselines.
- API-001 was not started.

## Known Issues

- The Qdrant Python client 1.16.2 still warns that the server is 1.19.0; the
  isolated Metadata rebuild nevertheless completed successfully.
- Repository-wide Ruff and mypy findings predate FIX-001 and remain at 31 and
  36 respectively.
- SQL-002 baseline accuracy limitations remain documented and were not changed.
- Gate 5 results cover ten fixed Synthetic functional cases only.

## Diff Review Summary

- Diff is limited to the fourteen files allowed by the FIX-001 Spec.
- Catalog additions are only canonical values already present in the accepted
  DATA-003 configuration and isolated warehouse; no invented table, field,
  metric, JOIN, or business formula was added.
- Query Builder SQL and table/grain routing are unchanged. Overall Order Count
  remains forbidden from Category aggregation, and Category Order Count is not
  represented as the overall metric.
- Evidence selection strength, ranking, Analyzer math, report wording, Golden
  labels, and evaluation thresholds are unchanged.
- New run artifacts contain only safe case-level metrics/status and exclude raw
  SQL, query rows, parameters, credentials, connection details, and Ground
  Truth database payloads.
- No API key, password, token, cookie, credentialed URL, original `dw` access,
  data regeneration, or API/Graph change was introduced.
