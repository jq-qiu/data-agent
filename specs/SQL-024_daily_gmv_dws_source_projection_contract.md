# SQL-024 Daily GMV DWS Source and Projection Contract

解决 SQL-023 T05：模型绕过 DWS，从 `fact_order + fact_order_item` 明细路径计算
“每日 GMV”。SQL-021 只把“若已选 DWS”时的分组改为 date_id，没有解决 Plan 本身
没有锁死 DWS 源表与最终投影的问题。

## 根因

- `schema_linking._DWS_ONLY_METRIC_COLUMNS` 不含 `gmv`，因此 gmv 的
  `required_metric_columns` 为空，`_restore_dws_metric_tables` 不会恢复
  `dws_sales_region_daily`。
- `plan_tables` 保留 LLM 召回到的 DWD 明细表，后续 Daily 分组逻辑取到的是
  `fact_order.date_id`，而不是 DWS 的 `date_id`。
- Validator 对 gmv 允许 DWD 路径，见 `validator._validate_grain_rules`；当 DWS gmv
  列未出现且 DWD 列与状态过滤齐全时放行。

事实源关系：Metric Registry 的 `gmv.formula = SUM(fact_order_item.price)` 与 DWS
`gmv` 列并不矛盾——DWS gmv 是同一 DWD 口径在日期/州粒度的可加总预聚合，数据基座
要求两表 GMV 对账。整体/地区 GMV 趋势应读取 `dws_sales_region_daily.gmv`，因此本
Feature 把源表选择固化到 Plan 查询策略层，不改 Registry 公式。

## In Scope

- 命中“每日/按日期 + GMV、无品类/卖家/状态切片”时，从 Catalog 确定性恢复
  `dws_sales_region_daily` 为唯一源表，不依赖召回结果。
- 去掉无关 DWD 表与 `dim_date`，Plan 不引入 calendar JOIN。
- 锁定 `GROUP BY / ORDER BY dws_sales_region_daily.date_id`。
- 在 `SchemaLinkingPlan` 增加可选精确契约：
  - `source_table`：非空时 SQL FROM 只能是该单表，且不允许 JOIN；
  - `result_projections`：非空时根 SELECT 的投影数量、顺序与聚合类型必须一致，
    T05 锁为 `date_id, SUM(gmv)`。
- Validator 按 AST 校验源表与根 SELECT 投影，Prompt/repair 只作展示与辅助。
- 单元测试、设计文档、状态与独立 Completion Report。

## Out of Scope

- 不修改 T04、J02、N02、C05 的语义或 Golden/Plan 冲突；先记录诊断，不改评测口径。
- 不实现通用 SQL Composer。
- 不修改 Metric Registry、Golden、Evaluator、SQL Policy 或历史评测产物。
- 不删除 Validator 对 DWD gmv 的通用放行；只有 Plan 冻结 source_table 时收紧。
- 不运行真实模型复测；收益由后续 SQL-025 Rerun Feature 验证。

## Allowed Files

- `app/nl2sql/schema_linking.py`
- `app/nl2sql/validator.py`
- `prompts/generate_sql.prompt`
- `prompts/correct_sql.prompt`
- `app/agent/nodes/correct_sql.py`
- `test/nl2sql/test_schema_linking_plan.py`
- `test/nl2sql/test_sql_validator.py`
- `test/nl2sql/test_sql_repair.py`
- `test/nl2sql/test_correct_sql_node.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report

## Acceptance

- T05 查询在候选只有 `fact_order + fact_order_item` 时，Plan 仍恢复
  `dws_sales_region_daily` 且不含 `dim_date`。
- 候选同时含 DWD/DWS/`dim_date` 时，最终 Plan 只保留 DWS 单表。
- T05 的 Plan source_table 为 `dws_sales_region_daily`，result_projections 为
  `date_id, SUM(gmv)`，group/order 为 DWS date_id。
- Validator 接受带不同表别名/中文输出别名的语义等价 SQL。
- Validator 拒绝 DWD GMV、`dim_date.date` 替代 date_id、缺 date_id、额外投影列、
  `dim_date` JOIN 与 source_table 多表 SQL。
- `correct_sql` 使用 Stub LLM 完成“错误 DWD SQL → 修复 → 同一 Validator 接受规范
  SQL”的节点级闭环；修复后仍错误时 Validator 拒绝且修复次数不超过 1。
- Month/Comparison 查询仍按既有 dim_date 语义工作，历史测试不回退。
- 全量 pytest、Ruff、mypy 与 `git diff --check` 通过。
