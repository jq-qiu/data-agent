# SQL-017 Overall DWS Required Columns

修复 SQL-016 T03/A02 的整体订单数假设：SchemaLinkingPlan 把 DWS-only 指标的
date_id/region_id/category_id 等口径列一并放入 required_metric_columns，导致不带这些
口径的整体 SUM 查询被 Validator 拒绝，模型只能以 HAVING/无谓投影 hack 绕行。

## In Scope

- `_DWS_ONLY_METRIC_COLUMNS` 只保留该指标在 DWS 上的公式必需列，不包含日期、地区、
  品类等口径列。
- DWS-only 指标来源表仍按公式列还原；口径列继续由 plan.columns、group_by、filters
  与 Validator 的 Metric Registry 规则约束。
- 整体 SUM(order_count) 不带 region_id/date_id 时可以按冻结 Plan 通过。
- Region 过滤/分组时仍通过 planned filter 或 group_by 约束 Region ID。
- 单元测试、设计文档、状态与独立 Completion Report。

## Out of Scope

- 不修改 Metric Registry、Golden、Data Model、Prompt、Evaluator 或历史评测产物。
- 不处理 C05/J02/TopN 漂移或真实模型非确定性。
- 不运行真实模型复测；收益由后续独立 Rerun 验证。
- 不放大 DWS 指标可跨口径聚合的语义；category_order_count 仍需品类 Scope。

## Allowed Files

- `app/nl2sql/schema_linking.py`
- `test/nl2sql/test_schema_linking_plan.py`
- `test/nl2sql/test_sql_repair.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report

## Acceptance

- 整体 order_count Plan 的 required_metric_columns 只含
  `dws_sales_region_daily.order_count`，但 columns 仍包含口径列。
- 无 region_id 的 T03 扁平 SQL 能通过原 Validator 与原 Plan。
- Region 查询的 region_id 仍通过 planned filter 约束。
- 全量 pytest、Ruff、mypy 和 `git diff --check` 通过。
