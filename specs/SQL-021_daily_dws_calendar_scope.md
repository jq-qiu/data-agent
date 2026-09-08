# SQL-021 Daily DWS Calendar Scope

解决 SQL-020 T05：每日/按日期查询在 DWS 已含 date_id 时，Plan 应直接把
dws_sales_region_daily.date_id 设为规范分组/排序列，不让模型自由引入 dim_date 并按
dim_date.date 分组。

## In Scope

- 命中“每日/按日/按日期”时，若候选表含 date_id，优先把 DWS/aggregate 的 date_id 加入
  group_by_columns，并通过 `_infer_order` 生成稳定 ORDER BY。
- 保持 dim_date 只在月/季/对比语义明确时作为 calendar_table 加入。
- 单元测试、设计文档、状态与独立 Completion Report。

## Out of Scope

- 不修改 J02 Golden/Plan 语义冲突；先记录诊断，不改评测口径。
- 不处理 C05 Pivot、N02 显示列、J02 NULL 分组语义或模型非确定性。
- 不修改 Prompt、Evaluator、Policy、Golden 或历史评测产物。
- 不运行真实模型复测；收益由 SQL-022 验证。

## Allowed Files

- `app/nl2sql/schema_linking.py`
- `test/nl2sql/test_schema_linking_plan.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report

## Acceptance

- “列出2018年5月每日GMV，按日期排序”的 Plan group/order 为 DWS date_id。
- Month/Comparison 查询仍使用 dim_date.month 等既有语义。
- 无 date_id 候选表时不触发该直接分组。
- 全量 pytest、Ruff、mypy 与 `git diff --check` 通过。
