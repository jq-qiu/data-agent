# SQL-021 Daily DWS Calendar Scope - Completion Report

## Feature

Daily/按日期查询在 DWS 已含 date_id 时，Plan 直接按物理 date_id 分组并稳定排序，
避免模型自由引入 dim_date 并按 dim_date.date 分组，目标 SQL-020 T05。

## Changed Files

- `app/nl2sql/schema_linking.py`
- `test/nl2sql/test_schema_linking_plan.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-021_daily_dws_calendar_scope.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- `.\\.venv\\Scripts\\python.exe -m pytest test/nl2sql/test_schema_linking_plan.py -q`
- `.\\.venv\\Scripts\\python.exe -m pytest`
- `.\\.venv\\Scripts\\ruff.exe check .`
- `.\\.venv\\Scripts\\mypy.exe app`
- `git diff --check`
- SQL-020 与历史评测产物 Diff Review

## Test Results

- Schema linking 专项：20 passed，其中 SQL-021 新增 1 个 Case。
- 全量 pytest：398 passed in 15.74 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- 未评测；本 Feature 未调用真实模型、数据库或检索服务。
- SQL-020 的 26/30 仍是最近真实结果，T05 收益须由 SQL-022 实测。

## Acceptance Criteria

1. Passed：Daily DWS Plan group/order 为物理 date_id。
2. Passed：无既有 region/category group 时才做 direct date_id 分组。
3. Passed：Month/Comparison 语义继续使用既有 calendar 规则。
4. Passed：SQL-020 与历史评测产物未修改。
5. Passed：全量 pytest、Ruff、mypy 与 whitespace Gate 全部通过。

## Known Issues

- 本 Feature 只处理 T05 的 Daily Calendar Scope，不宣称真实准确率提升。
- J02 差异已定位为 NULL category_name_en 的 name-only 与 id+name 分组语义冲突，
  需要 Golden/Plan 语义裁决后才能立项修复。
- C05 Pivot、N02 显示列、模型非确定性仍待处理。
- 真实模型收益必须由独立 SQL-022 Live/Replay 验证。

## Diff Review Summary

- 只新增一条 Plan 分组规则，Validator/Prompt/Policy 未放宽。
- dim_date 仍在 Month/Quarter/Comparison 语义中按原逻辑加入。
- Golden、Evaluator 与所有历史评测产物均未修改。
