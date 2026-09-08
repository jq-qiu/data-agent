# SQL-015 Unqualified Derived-column and Date ID Repair - Completion Report

## Feature

补齐 SQL-012/011 在 T03 实际修复输出上的两个缺口：无表名前缀的派生列引用无法被
扁平化，以及 Plan 内物理 `date_id` 的 ISO 日期字符串未被归一。

## Changed Files

- `app/nl2sql/repair.py`
- `test/nl2sql/test_sql_repair.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-015_unqualified_derived_dateid_repair.md`
- 本 Completion Report

## Added Dependencies

- 无；复用现有 SQLGlot。

## Commands Executed

- `.\\.venv\\Scripts\\python.exe -m pytest test/nl2sql/test_sql_repair.py -q`
- `.\\.venv\\Scripts\\python.exe -m pytest`
- `.\\.venv\\Scripts\\ruff.exe check .`
- `.\\.venv\\Scripts\\mypy.exe app`
- `git diff --check`
- SQL-014 与历史评测产物 Diff Review

## Test Results

- SQL repair 专项：18 passed，其中 SQL-015 新增 3 个 Case。
- 全量 pytest：392 passed in 14.53 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- 未评测；本 Feature 未调用真实模型、数据库或检索服务。
- SQL-014 的 25/30 仍是最近真实结果，T03 收益须由 SQL-016 实测。

## Acceptance Criteria

1. Passed：无前缀 `order_count` 与外层 `t.order_count` 均映射回物理列并丢弃未用投影。
2. Passed：Plan 内物理 `date_id` 的 ISO 日期字符串可转成 `YYYYMMDD` 整数。
3. Passed：Month/Date、其他表字符串与非规范字符串保持不变。
4. Passed：T03 实际形状经归一与扁平后通过原 Validator 与 Plan。
5. Passed：复杂/越界形状继续安全保持原 SQL。
6. Passed：SQL-014 与更早历史评测产物未修改。
7. Passed：全量 pytest、Ruff、mypy 和 whitespace Gate 全部通过。

## Known Issues

- 本 Feature 只处理 T03 的两个确定性缺口，不宣称真实准确率提升。
- C05 条件聚合、J02 Group 偏差、N04 指标漂移与 A02 数据库连接问题仍待处理。
- 真实模型收益必须由独立 SQL-016 Live/Replay 验证。

## Diff Review Summary

- 修复仍在最后一次 LLM 输出重回原 Validator 前执行，轮数、安全规则与 Validator 不变。
- ISO date_id 归一只作用于 Plan 已列出的物理 date_id 列，不新增字段/JOIN/过滤。
- Prompt、Metadata、Metric Registry、Policy、Golden 与所有历史评测产物均未修改。
