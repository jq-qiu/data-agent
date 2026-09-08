# SQL-006 Metric Formula and Calendar Enforcement

Enforce registered metric source columns and canonical dim_date calendar usage
for NL2SQL plan, prompt, and SQL Validator.

## In Scope

- Add required_metric_columns and calendar_table to SchemaLinkingPlan.
- Builder restores DWS-only metric formula tables and columns.
- Builder adds dim_date for month/quarter/comparison queries.
- Prompt and repair rules prohibit date_id string/arithmetic conversion.
- Validator rejects alternative metric tables for order_count/item_count.
- Unit tests and docs.

## Out of Scope

- No SQL-002/005 artifact modification.
- No new real-model full rerun in this Feature.
- No Live/Replay cache implementation.

## Acceptance

- COUNT(fact_order.order_id) with metric order_count is rejected.
- Plan can expose DWS formula columns to generate_sql.
- Calendar queries set calendar_table to dim_date.
- Full pytest/Ruff/mypy pass.
