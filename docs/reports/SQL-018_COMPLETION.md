# SQL-018 Post-SQL-017 Real-model Rerun - Completion Report

## Feature

在 Evaluator v3 与 SQL-011~013/015/017 修复链上重跑 30 条 NL2SQL Golden，验证整体
DWS required 修复并记录真实 Live/Replay 结果。

## Changed Files

- `data/reports/SQL-018_nl2sql_post_sql017_evaluation.json`
- `eval_runs/sql-018-post-sql017-v1/summary.json`
- `eval_runs/sql-018-post-sql017-v1/nl2sql_results.csv`
- `eval_runs/sql-018-post-sql017-v1/error_analysis.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-018_post_sql017_real_model_rerun.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL-018 Live 命令（重跑参考 SQL，未使用 `--skip-reference`）
- SQL-018 Replay 命令（临时报告与 Run 目录位于 `.tmp/`）
- PowerShell JSON 字段级 Live/Replay 对账
- SQL-016/018 差异分析
- `.\\.venv\\Scripts\\python.exe -m pytest`
- `.\\.venv\\Scripts\\ruff.exe check .`
- `.\\.venv\\Scripts\\mypy.exe app`
- `git diff --check`

## Test Results

- 全量 pytest：394 passed in 17.58 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- Case：30/30；六个 Bucket 各 5 条；兼容与严格参考摘要 30/30。
- Compatible / Strict Execution Accuracy：25/30（83.33%），两种口径一致。
- Metric Accuracy：29/30（96.67%）。
- SQL Validity / Executability / Validator Acceptance：27/30（90%）。
- Trace Conformance：18/30（60%）；Grain Contract：7/15（46.67%）。
- Correction：0/4；本轮 4 次修复均未实现“修复后结果正确”。
- 结果失败：T05、J02、N02、N03、C05。
- Safety：12/12 危险 SQL 被拒绝，危险放行 0。
- Gate 3：true；所有多标签失败都有主分类。
- 相对 SQL-016：A02/T03/N04 转通过，T05/N03 新增失败；J02/N02/C05 保持失败。
- SQL-017 的整体 DWS required 修复被本轮证实有效：T03/A02 不再因必需列误伤被拒绝，
  Grain/Trace 较 SQL-016 提升。模型非确定性仍使 TopN/Time 出现轮间漂移。
- Live/Replay：Evaluation、Safety、Gate、Dataset、Runtime、Prompt、Model、Database
  与 Cache 摘要字段全部一致。

## Acceptance Criteria

1. Passed：30 条 Case、六个 Bucket、兼容/严格参考摘要完整。
2. Passed：所有多标签失败均有主分类，Safety 12/12，Gate 3 passed。
3. Passed：Live/Replay 评测主体、Safety、Gate 和身份字段一致。
4. Passed：如实报告 25/30、T03/A02 转通过与 T05/N03/J02/C05 失败。
5. Passed：SQL-010/014/016 与历史产物未修改。
6. Passed：全量 pytest、Ruff、mypy 和 whitespace Gate 全部通过。

## Known Issues

- J02 仍把等价 Join 键 `dim_product.category_id` 放入 Group，Validator 要求 Plan 分组列
  `dim_category.category_id`；SQL-019 将做等价键规范。
- C05 仍生成按 status 条件聚合/无 Calendar Join 的形状；结构化约束不足以阻止。
- T05/N03 为本轮新增 Time/TopN 漂移；真实模型非确定性需要更多轮次或稳定策略。
- SQL-010/014/016 的历史分数均为单次真实运行，不能作为当前 25/30 的替代。

## Diff Review Summary

- 本 Feature 未修改 Runtime、Evaluator、Prompt、Metadata、Policy 或 Golden。
- 运行产物写入独立 SQL-018 路径；SQL-002/005/008/010/014/016 历史产物保持不变。
- Replay Cache 与临时 Replay 输出位于 Git 忽略的 `.tmp/`，不纳入提交。
- 报告保留 Grain/Trace 真实变化，不把单轮 25/30 解释为稳定提升。
