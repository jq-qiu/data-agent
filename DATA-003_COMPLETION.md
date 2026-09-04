# DATA-003 Completion Report

## Feature

DATA-003 Synthetic Evidence and Ground Truth.

`synthetic-v1` now provides deterministic D01-D10 regression scenarios without modifying Olist ODS, DWD, or accepted DWS values. DATA-003 completes Gate 1 only; Metadata, NL2SQL, LangGraph, diagnosis analysis, reporting, and API behavior remain unimplemented in this Feature.

## Changed Files

- `specs/DATA-003_synthetic_evidence.md`: freezes the generator, table grains, D01-D10 buckets, safety rules, and acceptance checks.
- `data/config/synthetic_v1.json`: versions the Seed, periods, evidence baselines, elasticities, cases, scopes, strengths, ranks, and missing-Evidence rule.
- `app/synthetic/__init__.py`: declares the Synthetic package.
- `app/synthetic/generator.py`: validates configuration, generates daily Evidence/result chains, persists Ground Truth, hashes content, and reconciles Gate 1.
- `app/scripts/generate_synthetic_evidence.py`: provides the controlled generator command and sanitized report.
- `test/data/test_synthetic_evidence.py`: tests the frozen buckets, independent reproducibility, evidence chains, stable/degradation behavior, idempotency, and tamper rejection.
- `data/reports/DATA-003_synthetic_evidence.json`: records the successful target generation and reconciliation.
- `IMPLEMENTATION_STATUS.md`: records DATA-003 and Gate 1 completion plus the META-001 resume point.
- `DATA-003_COMPLETION.md`: records this completion evidence.

## Added Dependencies

None.

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test/data/test_synthetic_evidence.py
.\.venv\Scripts\python.exe -m app.scripts.generate_synthetic_evidence
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check app/synthetic app/scripts/generate_synthetic_evidence.py test/data/test_synthetic_evidence.py
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

The controlled test suite generated the same content in two independent SQLite databases. The real generator ran twice against `data_agent_v1_dw`; the second run regenerated the expected payload, validated its digest, and reused the first successful batch. Independent read-only SQL checked representative D05, D07, D09, and D10 period totals, all table counts, event-type coverage, and unchanged original DWS GMV.

The first generated test payload was rejected because expected and persisted Business Event rows used different deterministic sort orders. Canonical sorting was added before hashing; no acceptance condition was weakened. A tamper test initially raised a stricter zero-denominator rejection than its message assertion expected, so the test was corrected to assert the rejection type rather than one specific safe failure message.

## Test Results

- DATA-003专项测试：4 passed in 1.10 seconds.
- Full pytest regression: 35 passed in 2.58 seconds.
- Independent deterministic generation: two databases produced the same content digest.
- Real MySQL first generation: success, not reused.
- Real MySQL second generation: success, reused the same batch and digest.

## Lint Results

- New DATA-003 Python files: all targeted Ruff checks passed.
- Full repository Ruff result: 51 existing diagnostics.
- ENG-001 Ruff baseline: 51 diagnostics.
- Baseline delta: 0.

## Type Check Results

- Full mypy result: 40 existing errors in 14 files; 67 source files checked.
- ENG-001 mypy baseline: 40 errors in 14 files.
- Baseline delta: 0.
- Targeted mypy reaches one pre-existing configuration-module error through the command wrapper; the Synthetic module adds no diagnostic.

## Evaluation Results

未进行模型或诊断 Agent 评测。Deterministic Gate 1 evaluation passed:

- Raw/ODS, DWD, and both original DWS remain reconciled;
- unsafe one-to-many Join inflation remains detected and excluded;
- overall Order Count remains sourced from region grain, not category sums;
- ratio values are recomputed from additive components and zero denominators return `None`;
- three event types with fixed Seed are reproducible;
- Ground Truth, direct Evidence, analysis orders, and analysis GMV are consistent for all 10 cases.

## Acceptance Criteria

- [x] Generator Version is `synthetic-v1`; Random Seed is 20260905; 10 cases are versioned.
- [x] D01-D10 match the frozen Traffic, Promotion, Stockout, dual-factor, stable, and missing-Evidence buckets.
- [x] `fact_business_event` contains 10 ranked events across all 3 allowed event types.
- [x] Six single-factor, two dual-factor, one no-clear-evidence, and one degradation case are present.
- [x] `analysis_sales_region_daily` contains 427 unique case-date-region rows.
- [x] `analysis_sales_category_daily` contains 183 unique case-date-region-category rows.
- [x] Two independent controlled databases produced the same content digest.
- [x] The real second run reused the same successful batch and digest.
- [x] Evidence-chain failures: 0.
- [x] Stable-case failures: 0.
- [x] Missing-Evidence degradation failures: 0.
- [x] D05 Stockout lowers inventory fill, orders, and GMV in the SP Synthetic scenario.
- [x] D07 lowers both Visitors and Promotion Coverage before orders and GMV.
- [x] D09 baseline/current orders and GMV are equal and has no Business Event.
- [x] D10 baseline/current Visitors are missing, results decline, and no cause is asserted.
- [x] Runtime ratios handle zero denominators as `None`.
- [x] Original region and category DWS GMV remain 13,494,400.74.
- [x] All Gate 1 conditions pass.
- [x] DATA-003专项 and full pytest pass.
- [x] Ruff and mypy do not exceed the ENG-001 baselines.
- [x] No META-001 or downstream behavior was implemented.
- [x] DATA-003 is isolated to one commit and push.

## Known Issues

- Synthetic Evidence is explicitly generated regression data and cannot support causal language or production generalization claims.
- Synthetic results live in separate `analysis_*` tables; later Metadata/Diagnosis Features must select them explicitly and must not present them as Olist facts.
- The accepted generator refuses automatic overwrite. A corrupted accepted version requires explicit operator remediation.
- The repository retains the documented Ruff baseline of 51 diagnostics and mypy baseline of 40 errors in 14 files.

## Diff Review Summary

The final diff is limited to one versioned non-secret generator configuration, independent Synthetic/Ground Truth schemas and generation code, one command wrapper, deterministic tests, a sanitized report, the DATA-003 Spec, persistent status, and this report. It does not update Olist ODS, DWD, or DWS values and does not modify Metadata, NL2SQL, LangGraph, Analyzer, report generation, or API behavior. No real user data, credentials, connection strings, tokens, raw Olist files, or local databases are included.
