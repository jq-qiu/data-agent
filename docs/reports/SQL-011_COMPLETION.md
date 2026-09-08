# SQL-011 Calendar Literal Repair Normalization - Completion Report

## Feature

针对 SQL-010 C02 的最后一次修复失败，在 LLM 修复输出重新进入 Validator 前，对 Plan
允许的 `dim_date.year/quarter/date_id` 数字字符串执行确定性整数 Literal 规范化。

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
- `specs/SQL-011_calendar_literal_repair_normalization.md`
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

- SQL-011 专项：4 passed。
- 全量 pytest：378 passed in 16.66 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- 未评测；本 Feature 未调用真实模型、数据库或检索服务。
- SQL-010 仍为兼容/严格 Execution 26/30，C02 收益须由后续独立 Rerun 验证。

## Acceptance Criteria

1. Passed：Plan 内 dim_date 数字字段支持表 Alias、反向比较与 IN 确定性规范化。
2. Passed：Month/Date、其他表与非规范数字字符串保持不变。
3. Passed：无合格 Plan、非 dim_date Calendar 或解析失败时原样返回。
4. Passed：修复节点仍只调用一次 LLM，规范化后重入同一 Validator。
5. Passed：SQL-010 与更早历史评测产物未修改。
6. Passed：全量 pytest、Ruff、mypy 和 whitespace Gate 全部通过。

## Known Issues

- 本 Feature 只处理 C02 类型错配假设，不宣称真实准确率提升。
- T03 必需指标列、C05 GROUP BY、J02 结果差异仍未处理。
- Qdrant 版本警告和 Token/Cost unavailable 仍是独立问题。

## Diff Review Summary

- Validator 规则未放宽，最大修复次数仍为一次。
- 规范化严格受 Plan Calendar Table、目标字段和数字格式约束，不新增/删除 SQL 结构。
- Prompt、Metadata、Policy、Golden 与所有历史评测产物均未修改。
