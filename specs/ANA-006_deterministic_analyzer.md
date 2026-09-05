# ANA-006 Deterministic Analyzer

## 1. Feature

Implement the deterministic numeric analysis layer that consumes the frozen
`AnalysisPlan` and validated `AnalysisQueryResult` contracts from ANA-004 and
ANA-005. The layer calculates period changes, the two-factor GMV Shapley
decomposition, region/category GMV contributions, and requested candidate
factor changes without using an LLM.

## 2. Source of Truth

This Feature follows, in order:

1. the current user request;
2. this specification;
3. `IMPLEMENTATION_PLAN.md`;
4. `docs/02_data_and_metric_design.md`;
5. `docs/04_analysis_methodology.md`;
6. `docs/05_agent_workflow.md`;
7. `docs/06_evaluation.md`;
8. `AGENTS.md` and existing frozen upstream contracts.

## 3. In Scope

- Strict, serializable Analyzer input/output models.
- Deterministic validation of query-result roles, required fields, numeric
  domains, query lineage, and metric-version consistency.
- Period absolute change and change-rate calculation.
- `GMV = Order Count x AOV` two-factor Shapley decomposition.
- Region and category GMV contribution calculation with completeness and
  near-zero-total safeguards.
- Traffic, Promotion, and Inventory candidate metric changes requested by the
  analysis plan.
- Stable warning and reconciliation contracts.
- An Analyzer node adapter that writes only `analysis_results`.
- Unit tests and a fixed offline evaluation set/report.

## 4. Out of Scope

- Evidence strength, support/refutation labels, candidate ranking, business
  conclusions, causal language, or report generation.
- LLM calls, NL2SQL changes, LangGraph wiring, metadata changes, or query
  execution changes.
- Metric-registry formula changes, AOV/GMV definition changes, schema changes,
  database writes, DDL, or data regeneration.
- EVAL-001 and every downstream Feature.

## 5. Allowed Files

- `specs/ANA-006_deterministic_analyzer.md`
- `app/diagnosis/__init__.py`
- `app/diagnosis/analyzer.py`
- `app/scripts/evaluate_deterministic_analyzer_v1.py`
- `data/evaluation/deterministic_analyzer_golden_v1.json`
- `data/reports/ANA-006_deterministic_analyzer_evaluation.json`
- `test/diagnosis/test_deterministic_analyzer.py`
- `ANA-006_COMPLETION.md`
- `IMPLEMENTATION_STATUS.md`

Any additional file requires a documented blocking reason and must stay inside
ANA-006.

## 6. Numeric Rules

All input numerics must be finite `Decimal`, integer, or canonical numeric
string values. Boolean and binary floating-point values are rejected. Counts
and additive measures must be non-negative.

Derived arithmetic uses a local decimal context with precision 28 and
`ROUND_HALF_EVEN`. Derived rates and monetary contributions are serialized at
six decimal places. Numeric reconciliation uses an absolute tolerance of
`0.01`.

### 6.1 Period Comparison

For one baseline and one current row:

```text
absolute_delta = current - baseline
change_rate = absolute_delta / ABS(baseline)
```

`change_rate` is `null` when the baseline is zero. This produces the stable
warning `BASELINE_ZERO` and does not invent an infinite rate.

### 6.2 GMV Shapley Decomposition

Let `Q0`, `Q1` be baseline/current Order Count and `P0`, `P1` be the derived
baseline/current AOV:

```text
order_count_contribution = (Q1 - Q0) * (P1 + P0) / 2
aov_contribution = (P1 - P0) * (Q1 + Q0) / 2
```

The contribution sum must reconcile to current GMV minus baseline GMV within
`0.01`. A non-zero GMV with zero orders is invalid. If either period has zero
orders and zero GMV, AOV and contributions are `null`, and the result degrades
with `AOV_DENOMINATOR_ZERO`. Any other failed Shapley reconciliation raises
`NUMERIC_RECONCILIATION_FAILED`.

### 6.3 Dimension Contribution

Missing period values for an observed dimension member are treated as zero.
For each member:

```text
delta_i = current_i - baseline_i
contribution_i = delta_i / total_delta
```

The grouped delta sum is compared with the overall period GMV delta. When they
do not reconcile within `0.01`, only absolute member deltas are returned;
contribution ratios are `null`, reconciliation is `DEGRADED`, and the stable
warning is `DIMENSION_TOTAL_MISMATCH`. When `ABS(total_delta) <= 0.01`, ratios
are also `null` with `TOTAL_DELTA_NEAR_ZERO`. Negative and greater-than-100%
contributions are valid when opposing member movements exist. Region and
category are independent results. Category order counts are never used for
overall Order Count reconciliation.

### 6.4 Candidate Factors

Only factors requested by the `candidate_validation` task are analyzed:

- Traffic: Visitors, Conversion Rate, and Order Count.
- Promotion: Promotion Coverage, Conversion Rate, and Order Count.
- Inventory: Inventory Fill Rate, Conversion Rate, and Order Count.

Ratios are calculated after additive aggregation:

```text
conversion_rate = order_count / visitors
promotion_coverage = promoted_sku_count / active_sku_count
inventory_fill_rate = available_sku_count / required_sku_count
```

A zero or missing denominator yields `null` for that period and emits
`RATIO_DENOMINATOR_ZERO_OR_MISSING`; it does not infer a value. Candidate
results are numeric observations only and do not express Evidence support or
causality.

## 7. Output Contract

Each strict `AnalysisResult` contains:

- stable `analysis_result_id` in plan/result order (`A001`, `A002`, ...);
- a deterministic method discriminator;
- exact `input_query_ids`;
- metric lineage/version records copied from validated query results;
- a typed, discriminated `values` payload;
- optional numeric reconciliation details;
- stable warning codes.

The Analyzer emits no raw SQL, SQL parameters, credentials, connection strings,
query trace internals, or LLM content. At most five analysis results may be
produced for the V1 full-diagnosis plan.

## 8. Failure Contract

Structural, lineage, or numeric-domain violations raise a typed
`AnalysisError` with a stable code. Required codes include:

- `INVALID_ANALYSIS_INPUT`
- `MISSING_QUERY_RESULT`
- `DUPLICATE_QUERY_RESULT`
- `METRIC_VERSION_MISMATCH`
- `NUMERIC_RECONCILIATION_FAILED`

Dimension incompleteness and defined zero-denominator cases use the explicit
degraded result contract rather than fabricated values.

## 9. Acceptance Criteria

1. Period delta/rate behavior, including zero baseline, is deterministic.
2. Valid Shapley results reconcile within `0.01`; invalid inputs fail closed.
3. Dimension contributions handle new/disappearing members, opposing effects,
   near-zero totals, and incomplete group sets without overclaiming.
4. Requested candidate ratios are computed from additive numerators and
   denominators; zero/missing denominators produce `null` and warnings.
5. Every result preserves query IDs and metric-version lineage and is JSON
   serializable without raw SQL or secrets.
6. The fixed offline evaluation passes every frozen numeric scenario.
7. Full pytest is green, and Ruff/mypy do not regress their recorded baselines.
8. Diff review confirms changes are limited to the allowed ANA-006 files.

## 10. Validation Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_deterministic_analyzer.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_deterministic_analyzer_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
```
