# SQL-013 Structured Plan Repair Constraints - Completion Report

## Feature

针对 SQL-010 C05，把冻结 SchemaLinkingPlan 提炼为短、错误导向、确定性格式的 LLM
修复约束，突出 Calendar Join、精确分组/排序/过滤并禁止把分组透视为条件聚合列。

## Changed Files

- `app/nl2sql/repair.py`
- `app/agent/nodes/correct_sql.py`
- `prompts/correct_sql.prompt`
- `test/nl2sql/test_sql_repair.py`
- `test/nl2sql/test_runtime_adaptation.py`
- `test/test_documentation_contract.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `specs/SQL-013_structured_plan_repair_constraints.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL repair/runtime prompt 相关专项 pytest
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\ruff.exe check .`
- `.\.venv\Scripts\mypy.exe app`
- `git diff --check`
- SQL-010 与历史评测产物 Diff Review

## Test Results

- 相关专项：21 passed，其中 SQL-013 新增 2 个约束 Case。
- 全量 pytest：389 passed in 14.07 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- 未评测；本 Feature 未调用真实模型、数据库或检索服务。
- SQL-010 仍为兼容/严格 Execution 26/30，C05 收益须由 SQL-014 实测。

## Acceptance Criteria

1. Passed：C05 Plan 的 fact_order/dim_date、Calendar、Join、Group 和 Order 均显式输出。
2. Passed：Group 错误明确要求每组一行并禁止条件聚合透视。
3. Passed：Include Filter 的方向和值完整输出；无 Plan 不虚构约束。
4. Passed：Prompt 包含独立约束变量，仍只执行一次 LLM 修复并重入原 Validator。
5. Passed：SQL-010 与更早历史评测产物未修改。
6. Passed：全量 pytest、Ruff、mypy 和 whitespace Gate 全部通过。

## Known Issues

- 结构化约束改善的是修复上下文，不保证非确定性模型一定生成正确 SQL。
- C02/T03 的确定性修复与 C05 约束均尚未真实复测；J02 结果差异未处理。
- Token/Cost unavailable 和 Qdrant 版本警告仍是独立问题。

## Diff Review Summary

- 不用 AST 或本地规则生成 C05 的业务聚合公式、Join 或过滤。
- Validator、最大修复次数、Metadata、Policy、Golden 均未改变。
- Prompt 只新增冻结 Plan 的确定性摘要，所有输出仍由 Validator 裁决。
