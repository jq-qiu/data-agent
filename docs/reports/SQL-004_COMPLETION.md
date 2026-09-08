# SQL-004 Deterministic SchemaLinkingPlan - Completion Report

## Feature

在开放式 NL2SQL 的 SQL 生成前，用 Registry 驱动的 SchemaLinkingPlan 冻结本次查询的
指标、表、列、JOIN 路径和规范分组维度，让 SQL 生成不再由模型猜测 JOIN/维度。

## Changed Files

- `app/nl2sql/schema_linking.py`（新增）：Plan 数据模型、Builder、Validator、元数据库路径 Provider。
- `app/agent/nodes/build_schema_linking_plan.py`（新增）：Graph 节点。
- `app/agent/graph.py`：插入 `build_schema_linking_plan -> generate_sql`。
- `app/agent/state.py`：State 增加 `schema_linking_plan`。
- `app/agent/nodes/generate_sql.py`、`correct_sql.py`：Prompt 输入增加 Plan。
- `prompts/generate_sql.prompt`、`correct_sql.prompt`：增加 Plan 约束。
- `test/nl2sql/test_schema_linking_plan.py`（新增）：5 个单元测试。
- `test/nl2sql/test_runtime_adaptation.py`：增加 Plan 占位符契约断言。
- `specs/SQL-004_schema_linking_plan.md`（新增）：Feature Spec。
- `README.md`、`IMPLEMENTATION_STATUS.md`：状态与评测说明。

## Added Dependencies

无。

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
```

## Test Results

343 passed, 0 failed。

SQL-004 专项 5 passed：地区维度补全、DWS 品类优先、未知列拒绝、断连失败关闭、
地区过滤不误分组。

## Lint Results

Ruff 0 findings。

## Type Check Results

mypy `app`：Success, no issues found in 114 source files。

## Evaluation Results

未执行真实外部模型 NL2SQL 复测。SQL-002 历史 Execution Accuracy 16/30 保持不可变；
SQL-004 只验证 Plan Builder/Validator 的确定性契约。

## Acceptance Criteria

- [x] SchemaLinkingPlan 模型/Builder/Validator 已新增并有单元测试。
- [x] 地区查询可补 `dim_region` 与 `customer_to_region` 路径。
- [x] DWS 已含 category_id/region_id 时优先直接分组，不额外 JOIN 维度表。
- [x] Graph/Prompt 已消费 Plan，修复路径同样受 Plan 约束。
- [x] 全量 pytest/Ruff/mypy 通过，无新增依赖。

## Known Issues

- 本 Feature 未重跑 30 条真实模型基线，不能宣称 Execution Accuracy 已提升。
- Builder 的维度分组识别基于 Registry/受控词组启发式；高泛化 NL 解析仍需后续评测和迭代。
- `table_infos` 中未出现但由 Plan 引入的规范维度表，依赖 SQL Prompt 的 Plan 约束正确使用。

## Diff Review Summary

未修改 SQL Validator、SQL-002/003 评测、历史报告、数据、配置或诊断链路。
用户已批准提交与推送；真实模型复测仍未执行。
