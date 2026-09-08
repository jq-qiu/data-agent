# SQL-009 NL2SQL Query Semantics Remediation - Completion Report

## Feature

针对 SQL-008 暴露的结果不匹配，增加确定性指标粒度收紧、日历分组/类型、稳定排序、
有效订单过滤，并让 Validator 按 SchemaLinkingPlan 再次核对生成和执行 SQL。

## Changed Files

- `app/agent/nodes/filter_metric.py`
- `app/agent/nodes/validate_sql.py`
- `app/agent/nodes/execute_sql.py`
- `app/nl2sql/schema_linking.py`
- `app/nl2sql/validator.py`
- `prompts/filter_metric_info.prompt`
- `prompts/generate_sql.prompt`
- `prompts/correct_sql.prompt`
- `test/nl2sql/test_metric_selection_policy.py`
- `test/nl2sql/test_schema_linking_plan.py`
- `test/nl2sql/test_sql_validator.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`, `IMPLEMENTATION_STATUS.md`, `docs/reports/README.md`
- `specs/SQL-009_query_semantics_remediation.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL-009 NL2SQL 专项 pytest
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\ruff.exe check .`
- `.\.venv\Scripts\mypy.exe app`
- `git diff --check`

## Test Results

- pytest: 369 passed
- SQL-009 新增专项：17 passed

## Lint Results

- Ruff: 0 findings
- `git diff --check`: no whitespace errors

## Type Check Results

- mypy: no issues in 114 source files

## Evaluation Results

- 未评测；SQL-009 未执行新的真实模型 30 条复测。
- 最近一次真实结果仍为 SQL-008 Execution Accuracy 22/30。

## Acceptance Criteria

- 明细物理行数不选择 `item_count`
- 已 Grounding 的订单状态拆分不选择无状态粒度的 DWS `order_count`
- `有效订单` Fact Plan 固定排除 canceled/unavailable
- 月份比较固定按 `dim_date.month` 分组和排序
- 枚举列表与显示名称使用稳定规范排序
- 日历字段非规范字面量在执行前被拒绝
- Validator 在生成与执行前均核对 Plan 表、列、JOIN、分组、排序、过滤
- 全量 pytest、Ruff、mypy 通过

## Known Issues

- SQL-009 的真实模型收益尚未实测，不能据单元测试更新 22/30 指标。
- C05 继续使用 Fact 订单状态粒度；本 Feature 没有新增状态感知 DWS。
- Qdrant client/server 版本警告仍是独立环境问题。

## Diff Review Summary

- 未修改数据模型、Metric Registry 公式、Golden Dataset 或 SQL-002/005/008 历史产物。
- Plan 约束是可选 Validator 输入，不影响诊断 Controlled Query Builder 的既有调用。
- 修复失败仍最多重试一次，修复 SQL 与执行 SQL 都不能绕过同一 Plan。
