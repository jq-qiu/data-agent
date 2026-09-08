# SQL-005 NL2SQL 30-Case Rerun after SchemaLinkingPlan

Use the SQL-004 current graph to rerun the same SQL-002 30-case Golden into an
independent SQL-005 report while keeping SQL-002 artifacts immutable.

## In Scope

- Add optional run_id to evaluate_nl2sql_v1, default remains SQL-002.
- Run 30 real cases and write SQL-005 report/run artifacts.
- Update README/status/report index/completion report.

## Out of Scope

- No prompt, Validator, Policy, Graph, SchemaLinkingPlan, data or config change.
- No rewrite of SQL-002 Golden or historical artifacts.

## Allowed Files

- This spec
- app/scripts/evaluate_nl2sql_v1.py
- data/reports/SQL-005_nl2sql_schema_linking_evaluation.json
- eval_runs/sql-005-schema-linking-v1/**
- README.md, IMPLEMENTATION_STATUS.md, docs/reports/README.md
- docs/reports/SQL-005_COMPLETION.md

## Verification

Default behavior without run_id stays SQL-002; SQL-005 writes only its own paths.
