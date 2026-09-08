# SQL-005 NL2SQL SchemaLinkingPlan Rerun - Completion Report

SQL-004 接入后重跑同一 30 条 NL2SQL Golden，结果写入独立 SQL-005 报告。
Execution Accuracy 从 SQL-002 的 16/30 提升到 19/30；JOIN bucket 从 0/5 提升到 3/5。
历史 SQL-002 报告与 eval_runs 保持不可变。

## Changed Files

- app/nl2sql/evaluation.py
- app/scripts/evaluate_nl2sql_v1.py
- app/nl2sql/schema_linking.py
- app/agent/nodes/build_schema_linking_plan.py
- test/nl2sql/test_schema_linking_plan.py
- data/reports/SQL-005_nl2sql_schema_linking_evaluation.json
- eval_runs/sql-005-schema-linking-v1/**
- specs/SQL-005_nl2sql_schema_linking_rerun.md
- README.md, IMPLEMENTATION_STATUS.md, docs/reports/README.md
- 本 Completion Report

## Verification

- pytest: 344 passed
- Ruff: 0 findings
- mypy: no issues
- SQL-005 gate_3_passed: true
- SQL-005 safety dangerous SQL allowed: 0

## Key Results

- Execution Accuracy: 19/30
- SQL Validity/Executability: 29/30
- JOIN bucket: 3/5
- Simple 3/5, Aggregate 4/5, Time 3/5, TopN 4/5, Comparison 2/5

## Known Issues

source_commit 需在 Feature 提交后校正为最终 HEAD；真实运行无连接中断。
结果不代表生产泛化能力。
