# SQL-016 Post-SQL-015 Real-model Rerun - Completion Report

## Feature

在 Evaluator v3 与 SQL-011~013 + SQL-015 修复链上重跑 30 条 NL2SQL Golden，验证真实
Live/Replay 结果，并记录仍存的确定性缺口。

## Changed Files

- `data/reports/SQL-016_nl2sql_post_sql015_evaluation.json`
- `eval_runs/sql-016-post-sql015-v1/summary.json`
- `eval_runs/sql-016-post-sql015-v1/nl2sql_results.csv`
- `eval_runs/sql-016-post-sql015-v1/error_analysis.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-016_post_sql015_real_model_rerun.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL-016 Live 命令（重跑参考 SQL，未使用 `--skip-reference`）
- SQL-016 Replay 命令（临时报告与 Run 目录位于 `.tmp/`）
- PowerShell JSON 字段级 Live/Replay 对账
- SQL-010/014/016 差异分析
- `.\\.venv\\Scripts\\python.exe -m pytest`
- `.\\.venv\\Scripts\\ruff.exe check .`
- `.\\.venv\\Scripts\\mypy.exe app`
- `git diff --check`

## Test Results

- 全量 pytest：392 passed in 14.53 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- Case：30/30；六个 Bucket 各 5 条；兼容与严格参考摘要 30/30。
- Compatible / Strict Execution Accuracy：24/30（80.00%），两种口径一致。
- Metric Accuracy：30/30（100%）。
- SQL Validity / Executability / Validator Acceptance：27/30（90%）。
- Trace Conformance：15/30（50%）；Grain Contract：4/15（26.67%）。
- Correction：3/7（42.86%），严格口径相同。
- Bucket Execution：Simple 5/5、Aggregate 4/5、Time 4/5、JOIN 4/5、TopN 3/5、
  Comparison 4/5。
- 结果失败：A02、T03、J02、N02、N04、C05。
- Safety：12/12 危险 SQL 被拒绝，危险放行 0。
- Gate 3：true；所有多标签失败都有主分类。
- 与 SQL-014 比较：无新增转通过；N02 新增失败，A02/T03/J02/N04/C05 保持失败。
- T03/A02 仍受整体 DWS Plan 强制 `region_id` 必需列影响；即使扁平化后物理列可回溯，
  不含 region_id 的整体 SUM 查询仍被 Plan 约束拒绝。这是 SQL-017 的单一口径假设。
- N02 本轮使用 MAX(category_name)+ROW_NUMBER 但投影名/结构不符合 Golden；模型漂移。
- Live/Replay：Evaluation、Safety、Gate、Dataset、Runtime、Prompt、Model、Database
  与 Cache 摘要字段全部一致。

## Acceptance Criteria

1. Passed：30 条 Case、六个 Bucket、兼容/严格参考摘要完整。
2. Passed：所有多标签失败均有主分类，Safety 12/12，Gate 3 passed。
3. Passed：Live/Replay 评测主体、Safety、Gate 和身份字段一致。
4. Passed：如实报告 24/30 与 T03/A02/J02/N02/N04/C05，不预设提升。
5. Passed：SQL-010/014 与历史产物未修改。
6. Passed：全量 pytest、Ruff、mypy 和 whitespace Gate 全部通过。

## Known Issues

- 整体 DWS 指标（如 order_count）的 SchemaLinkingPlan 强制包含 Region ID 必需列，
  与整体粒度参考 SQL 不一致；SQL-017 将按 Scope 裁剪该必需列。
- C05 仍生成条件聚合/按 status 分组，J02 仍结果不匹配，TopN 存在模型结构漂移。
- 三次真实运行（26/25/24）表明模型非确定性显著；单次 Case 变化不能归因于某修复。
- Token/Cost unavailable 与 Qdrant 版本警告仍是独立问题。

## Diff Review Summary

- 本 Feature 未修改 Runtime、Evaluator、Prompt、Metadata、Policy 或 Golden。
- 运行产物写入独立 SQL-016 路径；SQL-002/005/008/010/014 历史产物保持不变。
- Replay Cache 与临时 Replay 输出位于 Git 忽略的 `.tmp/`，不纳入提交。
- 报告保留 24/30、Metric Accuracy 30/30 与 Gate true 的真实组合，不夸大提升。
