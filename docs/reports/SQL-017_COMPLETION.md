# SQL-017 Overall DWS Required Columns - Completion Report

## Feature

把 DWS-only 指标的 `required_metric_columns` 从“表口径列全集”收窄为“指标公式必需列”，
避免整体 SUM(order_count) 被强制引用 date_id/region_id，同时保留 Region 口径约束。

## Changed Files

- `app/nl2sql/schema_linking.py`
- `test/nl2sql/test_schema_linking_plan.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-017_overall_dws_required_columns.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- `.\\.venv\\Scripts\\python.exe -m pytest test/nl2sql/test_schema_linking_plan.py test/nl2sql/test_sql_repair.py -q`
- `.\\.venv\\Scripts\\python.exe -m pytest`
- `.\\.venv\\Scripts\\ruff.exe check .`
- `.\\.venv\\Scripts\\mypy.exe app`
- `git diff --check`
- SQL-016 与历史评测产物 Diff Review

## Test Results

- Schema linking/repair 专项：36 passed，其中 SQL-017 新增 2 个 Case。
- 全量 pytest：394 passed in 17.58 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- 未评测；本 Feature 未调用真实模型、数据库或检索服务。
- SQL-016 的 24/30 仍是最近真实结果，SQL-017 收益须由 SQL-018 实测。

## Acceptance Criteria

1. Passed：整体 order_count Plan 的 required 只含 `dws_sales_region_daily.order_count`。
2. Passed：DWS 表 date_id/region_id 仍留在 plan.columns，供查询生成与过滤使用。
3. Passed：Region 分组查询的 region_id 仍在 group_by_columns 中被保留。
4. Passed：SQL-016 与更早历史评测产物未修改。
5. Passed：全量 pytest、Ruff、mypy 和 whitespace Gate 全部通过。

## Known Issues

- 本 Feature 只消除整体 DWS 必需列误伤，不宣称真实准确率提升。
- C05 条件聚合、J02 结果差异与 TopN 模型结构漂移仍待处理。
- 真实模型收益必须由独立 SQL-018 Live/Replay 验证。

## Diff Review Summary

- Metric Registry 公式与 Validator 指标口径未变；仅 Builder 输出的 required 列集收窄。
- DWS-only 来源表仍按公式列还原，口径列继续通过 columns/group/filters 暴露。
- Prompt、Policy、Golden、Evaluator 与所有历史评测产物均未修改。
