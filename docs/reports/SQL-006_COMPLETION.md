# SQL-006 Metric Formula and Calendar Enforcement - Completion Report

## Feature

为 NL2SQL 增加指标公式来源与日历约束：SchemaLinkingPlan 暴露 DWS-only
注册指标列，Validator 拒绝事实表 COUNT 替代口径，日历/对比类查询补 dim_date。

## Changed Files

- app/nl2sql/schema_linking.py
- app/nl2sql/validator.py
- prompts/generate_sql.prompt
- prompts/correct_sql.prompt
- test/nl2sql/test_schema_linking_plan.py
- test/nl2sql/test_sql_validator.py
- specs/SQL-006_metric_calendar_enforcement.md
- README.md, IMPLEMENTATION_STATUS.md, docs/reports/README.md
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\ruff.exe check .`
- `.\.venv\Scripts\mypy.exe app`
- `git diff --check`

## Test Results

- pytest: 349 passed
- SQL-002/003 reference SQL regression passed

## Lint Results

- Ruff: 0 findings
- `git diff --check`: no whitespace errors

## Type Check Results

- mypy: no issues in 114 source files

## Evaluation Results

- 未评测；本 Feature 未执行真实模型全量复测。

## Acceptance Criteria

- COUNT(fact_order.order_id) with order_count metric rejected
- Plan restores DWS-only source tables and exposes required_metric_columns
- Comparison/month queries set calendar_table to dim_date
- Full tests/Ruff/mypy pass

## Known Issues

- SQL-006 尚未做真实模型全量复测
- Live/Replay 评测属于 SQL-007

## Diff Review Summary

- Registry 来源表、方案列、Prompt 约束与 Validator 口径一致。
- 未修改 SQL-002/SQL-005 历史评测产物，未加入外部服务依赖。
