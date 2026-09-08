# SQL-009 NL2SQL Query Semantics Remediation

Remediate the deterministic query-semantics gaps evidenced by SQL-008 without changing
the warehouse model, Golden Dataset, or historical evaluation artifacts.

## In Scope

- Keep physical detail-row counts out of the registered `item_count` metric path.
- Keep status-sliced order counts on `fact_order`; DWS `order_count` has no status grain.
- Add query-level `有效订单` exclusions when the selected plan contains `fact_order`.
- Add canonical calendar grouping/order for month comparisons.
- Add deterministic ordering for canonical-value lists and display-name grouping.
- Reject non-canonical `dim_date` month/year/quarter/date_id literals before execution.
- Align metric-filter, SQL-generation, and repair prompts with these deterministic rules.
- Unit tests and current documentation.

## Out of Scope

- No data model, Metric Registry formula, Golden Dataset, or historical SQL-002/005/008
  artifact modification.
- No claim that all SQL-008 failures are fixed without a separate real-model rerun.
- No new metric or status-aware DWS aggregation.

## Allowed Files

- `app/agent/nodes/filter_metric.py`
- `app/nl2sql/schema_linking.py`
- `app/nl2sql/validator.py`
- `prompts/filter_metric_info.prompt`
- `prompts/generate_sql.prompt`
- `prompts/correct_sql.prompt`
- NL2SQL unit tests
- `README.md`, `IMPLEMENTATION_STATUS.md`, `docs/reports/README.md`
- This Spec and its Completion Report

## Acceptance

- Detail-row count wording deselects `item_count` deterministically.
- Grounded order-status slicing deselects DWS `order_count` deterministically.
- `有效订单` adds the registered canceled/unavailable exclusion to a fact-order plan.
- Month comparisons group and order by `dim_date.month` only.
- Canonical-value list queries receive stable order; display-name grouping orders by display.
- `dim_date.month IN (4, 5)` and string year/quarter/date_id literals are rejected.
- Full pytest, Ruff, and mypy pass.
