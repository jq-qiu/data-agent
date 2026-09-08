# SQL-019 Group-by Join-key Canonicalization - Completion Report

## Feature

让 SchemaLinkingPlan 无条件包含 registered Join 左右列，并把 GROUP BY 中等价 Join 键
确定性规范成唯一 Plan 分组/显示列，解决 J02 的 `dim_product.category_id` vs
`dim_category.category_id` 偏差。

## Changed Files

- `app/nl2sql/schema_linking.py`
- `app/nl2sql/repair.py`
- `app/agent/nodes/correct_sql.py`
- `test/nl2sql/test_schema_linking_plan.py`
- `test/nl2sql/test_sql_repair.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-019_group_join_key_canonicalization.md`
- 本 Completion Report

## Added Dependencies

- 无；复用现有 SQLGlot。

## Commands Executed

- `.\\.venv\\Scripts\\python.exe -m pytest test/nl2sql/test_sql_repair.py test/nl2sql/test_schema_linking_plan.py -q`
- `.\\.venv\\Scripts\\python.exe -m pytest`
- `.\\.venv\\Scripts\\ruff.exe check .`
- `.\\.venv\\Scripts\\mypy.exe app`
- `git diff --check`
- SQL-018 与历史评测产物 Diff Review

## Test Results

- SQL repair/schema linking 专项：39 passed，其中 SQL-019 新增 3 个 Case。
- 全量 pytest：397 passed in 16.61 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- 未评测；本 Feature 未调用真实模型、数据库或检索服务。
- SQL-018 的 25/30 仍是最近真实结果，J02 收益须由 SQL-020 实测。

## Acceptance Criteria

1. Passed：registered Join 左右列无条件进入 plan.columns。
2. Passed：`GROUP BY dp.category_id` 可规范成 Plan 的 `dc.category_id`。
3. Passed：无对应 Join、目标不唯一或目标表不在 SQL 时不改写。
4. Passed：只作用于 GROUP BY，SELECT/JOIN/WHERE/ORDER BY 不变。
5. Passed：SQL-018 与历史评测产物未修改。
6. Passed：全量 pytest、Ruff、mypy 与 whitespace Gate 全部通过。

## Known Issues

- 本 Feature 只处理 J02 等价 Group 键，不宣称真实准确率提升。
- C05 Pivot、N03 缺失 Join/Filter、T05 日历过度 Join 与 TopN 漂移仍待处理。
- 真实模型收益必须由独立 SQL-020 Live/Replay 验证。

## Diff Review Summary

- 修复严格限定在 Plan 已登记等值 Join；未放宽 Validator 或新增 SQL 结构。
- Prompt、Policy、Golden、Evaluator 与所有历史评测产物均未修改。
