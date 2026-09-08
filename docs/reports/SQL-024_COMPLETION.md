# SQL-024 Daily GMV DWS Source and Projection Contract - Completion Report

## Feature

在 SQL-023 后修复 T05：整体每日 GMV 查询不再允许模型走 DWD 明细路径或引入
`dim_date.date`。Plan 直接从 Catalog 恢复 `dws_sales_region_daily` 单表，并把
`date_id, SUM(gmv)` 作为有序投影契约；Validator 按 AST 强制根 SELECT 与方案一致。

## Changed Files

- `app/nl2sql/schema_linking.py`
- `app/nl2sql/validator.py`
- `app/nl2sql/repair.py`
- `prompts/generate_sql.prompt`
- `prompts/correct_sql.prompt`
- `test/nl2sql/test_schema_linking_plan.py`
- `test/nl2sql/test_sql_validator.py`
- `test/nl2sql/test_correct_sql_node.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-024_daily_gmv_dws_source_projection_contract.md`
- 本 Completion Report

## Added Dependencies

- 无。使用现有 Pydantic、SQLGlot 与 LangChain FakeListChatModel 测试依赖。

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test\nl2sql\test_schema_linking_plan.py test\nl2sql\test_sql_validator.py test\nl2sql\test_sql_repair.py test\nl2sql\test_correct_sql_node.py -q
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
```

## Test Results

- 目标专项：88 passed。
- 全量 pytest：410 passed（相对 SQL-023 基线新增 12 个用例）。
- 覆盖：DWD 候选恢复地区 DWS；DWD/DWS/dim_date 并存时只保留 DWS；品类每日查询不
  错误触发地区 DWS；别名等价 SQL 通过；DWD、dim_date JOIN、缺 date_id、额外投影、
  投影乱序均被拒绝；`correct_sql` Stub LLM 闭环修复与仍错误拒绝。

## Lint Results

- Ruff：全仓库 All checks passed。

## Type Check Results

- mypy：Success，no issues found in 115 source files。

## Evaluation Results

- 未评测。本 Feature 未执行真实模型 Live/Replay；T05 收益由 SQL-025 Rerun Feature
  验证。

## Acceptance Criteria

- T05 查询候选只有 DWD 时 Plan 恢复 `dws_sales_region_daily` 单表且不含 dim_date：通过。
- 候选同时含 DWD/DWS/dim_date 时只保留 DWS：通过。
- source_table/result_projections/group/order 与规格一致：通过。
- Validator 接受别名等价 SQL，拒绝 DWD、dim_date.date、缺 date_id、额外投影与多表：通过。
- correct_sql Stub LLM 节点级闭环：通过；仍错误时 Validator 拒绝。
- Month/Comparison 既有 dim_date 语义与历史测试不回退：通过。
- 全量 pytest、Ruff、mypy 与 `git diff --check`：通过。

## Known Issues

- 真实模型复测未执行；SQL-024 只证明 Plan/Validator/修复闭环，不证明模型在 Live 上
  一定输出规范 SQL。
- T04/J02/N02/C05 仍为剩余失败，其中 J02 为 Golden/Plan 语义冲突，需另行裁决。
- 若未来整体月/季 GMV 也要强制 DWS，应在后续 Feature 扩展相同的源表选择规则；本
  Feature 刻意只覆盖“每日/按日期 + GMV、无品类/卖家/状态切片”。

## Diff Review Summary

- `SchemaLinkingPlan` 新增可选 `source_table` 与 `result_projections`，默认 None/空，
  既有 Plan 与 Replay 身份不受影响。
- Builder 只在整体每日 GMV 命中时恢复单源表并裁剪列；其他指标/维度路径逻辑不变。
- Validator 用 AST 校验根 SELECT；Prompt/repair 只增加展示约束，仍由 Validator 裁决。
- `test_sql_repair.py` 未增加用例但随约束渲染回归；历史评测产物、Golden 与
  Metric Registry 均未修改。
