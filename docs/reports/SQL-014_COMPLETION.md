# SQL-014 Post-repair Real-model Rerun - Completion Report

## Feature

在 Evaluator v3 与 SQL-011~013 修复链上重跑冻结的 30 条 NL2SQL Golden，执行真实
Live/Replay 并记录可信的分类完整结果。

## Changed Files

- `data/reports/SQL-014_nl2sql_post_repair_evaluation.json`
- `eval_runs/sql-014-post-repair-v1/summary.json`
- `eval_runs/sql-014-post-repair-v1/nl2sql_results.csv`
- `eval_runs/sql-014-post-repair-v1/error_analysis.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-014_post_repair_real_model_rerun.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL-014 Live 命令（重跑参考 SQL，未使用 `--skip-reference`）
- SQL-014 Replay 命令（临时报告与 Run 目录位于 `.tmp/`）
- PowerShell JSON 字段级 Live/Replay 对账
- SQL-010/SQL-014 Case 与 Bucket 差异分析
- `.\\.venv\\Scripts\\python.exe -m pytest`
- `.\\.venv\\Scripts\\ruff.exe check .`
- `.\\.venv\\Scripts\\mypy.exe app`
- `git diff --check`

## Test Results

- 全量 pytest：389 passed in 16.75 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- Case：30/30；六个 Bucket 各 5 条；兼容与严格参考摘要 30/30。
- Compatible / Strict Execution Accuracy：25/30（83.33%），两种口径一致。
- SQL Validity / Executability / Validator Acceptance：27/30（90%）。
- Metric Accuracy：28/30（93.33%）；Trace Conformance：17/30（56.67%）。
- Grain Contract：5/15（33.33%）；Correction：1/4（25%），严格口径相同。
- Bucket Execution：Simple 5/5、Aggregate 4/5、Time 4/5、JOIN 4/5、TopN 4/5、
  Comparison 4/5。
- 结果失败：A02、T03、J02、N04、C05。
- Safety：12/12 危险 SQL 被拒绝，危险放行 0。
- Gate 3：true。所有 13 个多标签失败都有主分类，其中 A02 为
  MySQL Lost connection 环境失败；T03/J02/C05 仍失败，N04 为本轮模型指标/结果漂移。
- 与 SQL-010 比较：C02 由失败转通过；T03、J02、C05 仍失败；A02、N04 新增。
  模型运行非确定，A02 属基础设施连接丢失，不能把 Case 变化全部归因于修复。
- Live/Replay：Evaluation、Safety、Gate、Dataset、Prompt、Runtime、Model、Database
  和 Cache 摘要字段全部一致。

## Acceptance Criteria

1. Passed：30 条 Case、六个 Bucket、兼容/严格参考摘要完整。
2. Passed：所有多标签失败均有主分类，Safety 12/12，Gate 3 passed。
3. Passed：Live/Replay 评测主体、Safety、Gate 和身份字段一致。
4. Passed：如实报告 C02/T03/J02/C05/A02/N04 与总体 25/30，不预设提升。
5. Passed：SQL-010 与历史产物未修改。
6. Passed：全量 pytest、Ruff、mypy 和 whitespace Gate 全部通过。

## Known Issues

- SQL-012 扁平化只接受 `t.order_count`；T03 修复输出使用无表名前缀的 `order_count`，
  导致必需指标列仍无法回溯（SQL-015 将只修此缺口）。
- C05 结构化约束仍不能阻止模型生成条件聚合/直接 `purchase_date` 透视；J02 修复后又把
  `dim_product.category_id` 加入 Group，仍偏离 Plan。
- A02 在候选图执行中遇到 MySQL Lost connection；不是确定性模型失败，正式复测须单列。
- N04 本轮误选 `item_count` 并保留排名列/结果形状不符。
- 历史 SQL-010 26/30 不能替代 SQL-014 的 25/30；模型非确定性由两次运行证明。

## Diff Review Summary

- 本 Feature 未修改 Runtime、Evaluator、Prompt、Metadata、Policy 或 Golden。
- 运行产物写入独立 SQL-014 路径；SQL-002/005/008/010 历史产物保持不变。
- Replay Cache 与临时 Replay 输出位于 Git 忽略的 `.tmp/`，不纳入提交。
- 报告保留 A02 环境失败与 N04 新漂移，不把 Gate 通过误写为准确率提升。
