# SQL-012 Required Metric Subquery Flattening - Completion Report

## Feature

针对 SQL-010 T03 的修复形状，在最后一次 LLM 修复后识别并扁平化严格安全的单表裸列
派生查询，使必需指标物理列和日期过滤重新可由原 Validator 追踪。

## Changed Files

- `app/nl2sql/repair.py`
- `app/agent/nodes/correct_sql.py`
- `test/nl2sql/test_sql_repair.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-012_required_metric_subquery_flattening.md`
- 本 Completion Report

## Added Dependencies

- 无；复用现有 SQLGlot。

## Commands Executed

- `.\.venv\Scripts\python.exe -m pytest test/nl2sql/test_sql_repair.py -q`
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\ruff.exe check .`
- `.\.venv\Scripts\mypy.exe app`
- `git diff --check`
- SQL-010 与历史评测产物 Diff Review

## Test Results

- SQL repair 专项：13 passed，其中 SQL-012 新增 9 个 Case。
- 全量 pytest：387 passed in 15.42 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- 未评测；本 Feature 未调用真实模型、数据库或检索服务。
- SQL-010 仍为兼容/严格 Execution 26/30，T03 收益须由后续独立 Rerun 验证。

## Acceptance Criteria

1. Passed：T03 形状被扁平为同一物理表聚合，日期过滤和输出 Alias 保留。
2. Passed：未使用 `region_id` 投影删除，Alias 投影映射回真实物理列。
3. Passed：扁平结果在原 Validator 与原 Plan 下成功，并回溯 order_count/date_id。
4. Passed：聚合/分组/Distinct/Limit/外层过滤/Plan 外列/无必需指标契约均保持原 SQL。
5. Passed：修复轮数、安全规则、Prompt 与 Validator 均未改变。
6. Passed：SQL-010 与更早历史评测产物未修改。
7. Passed：全量 pytest、Ruff、mypy 和 whitespace Gate 全部通过。

## Known Issues

- 本 Feature 只处理 T03 冗余派生表假设，不宣称真实准确率提升。
- C05 GROUP BY/Calendar Join 和 J02 结果差异仍未处理。
- 复杂派生表不会自动改写，将继续由 Validator 安全拒绝。

## Diff Review Summary

- 扁平化前置条件刻意严格；任何不确定结构原样交回 Validator。
- 只移动内层既有过滤并映射外层实际引用，不创建公式、字段、Join 或过滤。
- Prompt、Metadata、Policy、Golden 与所有历史评测产物均未修改。
