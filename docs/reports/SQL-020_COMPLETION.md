# SQL-020 Post-SQL-019 Real-model Rerun - Completion Report

## Feature

在 Evaluator v3、SQL-011~013/015/017/019 修复链上重跑 30 条 NL2SQL Golden，验证
Join-key 规范化并记录真实 Live/Replay 结果。

## Changed Files

- `data/reports/SQL-020_nl2sql_post_sql019_evaluation.json`
- `eval_runs/sql-020-post-sql019-v1/summary.json`
- `eval_runs/sql-020-post-sql019-v1/nl2sql_results.csv`
- `eval_runs/sql-020-post-sql019-v1/error_analysis.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-020_post_sql019_real_model_rerun.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL-020 Live 命令（重跑参考 SQL，未使用 `--skip-reference`）
- SQL-020 Replay 命令（临时报告与 Run 目录位于 `.tmp/`）
- PowerShell JSON 字段级 Live/Replay 对账
- SQL-018/020 差异分析
- `.\\.venv\\Scripts\\python.exe -m pytest`
- `.\\.venv\\Scripts\\ruff.exe check .`
- `.\\.venv\\Scripts\\mypy.exe app`
- `git diff --check`

## Test Results

- 全量 pytest：397 passed（SQL-019 收口后代码基线，本 Feature 未改运行时代码）。
- Documentation contract：25 passed。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- Case：30/30；六个 Bucket 各 5 条；兼容与严格参考摘要 30/30。
- Compatible / Strict Execution Accuracy：26/30（86.67%），两种口径一致。
- Metric Accuracy：30/30；Validator Acceptance：30/30；SQL Validity/Executability：30/30。
- Trace Conformance：20/30（66.67%）；Grain Contract：9/15（60%）。
- Correction：0/2；本轮两次修复后仍未达到结果正确。
- 结果失败：T05、J02、N02、C05。
- Safety：12/12 危险 SQL 被拒绝，危险放行 0。
- Gate 3：true。
- 相对 SQL-018：N03 转通过，无任何回退，整体 26/30 为当前最优真实结果。
- J02 已通过 Validator 且 Trace 全对，但结果值仍与参考不同，需单独数值诊断。
- Live/Replay：Evaluation、Safety、Gate、Dataset、Runtime、Prompt、Model、Database
  与 Cache 摘要字段全部一致。

## Acceptance Criteria

1. Passed：30 条 Case、六个 Bucket、兼容/严格参考摘要完整。
2. Passed：所有多标签失败均有主分类，Safety 12/12，Gate 3 passed。
3. Passed：Live/Replay 评测主体、Safety、Gate 和身份字段一致。
4. Passed：如实报告 26/30、N03 转通过与 T05/J02/N02/C05 失败。
5. Passed：历史评测产物未修改。
6. Passed：全量 pytest、Ruff、mypy 与 whitespace Gate 全部通过（397 passed）。

## Known Issues

- J02 已不再被 SchemaLinkingPlan 拒绝，但兼容/严格结果不匹配；下阶段先做参考/候选
  行级数值诊断再立项。
- C05 仍生成 Pivot Shape；T05 仍为每日查询过度引入 Calendar Join；N02 仍保留多余
  显示列结构。三者的修复方向和风险已在 SQL-020 报告中记录。
- 模型非确定性仍可能让单次 26/30 在不同轮次波动。

## Diff Review Summary

- 本 Feature 未修改 Runtime、Evaluator、Prompt、Metadata、Policy 或 Golden。
- 运行产物写入独立 SQL-020 路径；历史评测产物保持不变。
- Replay Cache 与临时 Replay 输出位于 Git 忽略的 `.tmp/`，不纳入提交。
