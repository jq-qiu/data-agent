# SQL-022 DeepSeek-V3.2 Real-model Rerun - Completion Report

## Feature

在 Evaluator v3、SQL-011~013/015/017/019/021 修复链上，以 DeepSeek-V3.2 重跑冻结的
30 条 NL2SQL Golden，验证 Daily DWS 修复与模型切换后的真实结果。

## Changed Files

- `data/reports/SQL-022_nl2sql_v32_post_sql021_evaluation.json`
- `eval_runs/sql-022-v32-post-sql021-v1/summary.json`
- `eval_runs/sql-022-v32-post-sql021-v1/nl2sql_results.csv`
- `eval_runs/sql-022-v32-post-sql021-v1/error_analysis.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-022_v32_post_sql021_real_model_rerun.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL-022 Live 命令（DeepSeek-V3.2，未使用 `--skip-reference`）
- SQL-022 Replay 命令（临时报告与 Run 目录位于 `.tmp/`）
- PowerShell JSON 字段级 Live/Replay 对账
- SQL-020(V4-flash)/SQL-022(V3.2) 差异分析
- `.\\.venv\\Scripts\\python.exe -m pytest`
- `.\\.venv\\Scripts\\ruff.exe check .`
- `.\\.venv\\Scripts\\mypy.exe app`
- `git diff --check`

## Test Results

- 全量 pytest：398 passed（SQL-021 收口后基线；本 Feature 未改代码）。
- Documentation contract：25 passed。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 115 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- Model：`deepseek-ai/DeepSeek-V3.2`（本地 conf/app_config.yaml）。
- Case：30/30；六个 Bucket 各 5 条；兼容与严格参考摘要 30/30。
- Compatible / Strict Execution Accuracy：23/30（76.67%）。
- Metric Accuracy：26/30（86.67%）。
- SQL Validity / Executability / Validator Acceptance：28/30（93.33%）。
- Trace Conformance：14/30（46.67%）；Grain Contract：5/15（33.33%）。
- Correction：4/10（40%），是历次运行中修复尝试与成功数最高的一轮。
- Safety：12/12 危险 SQL 被拒绝，危险放行 0。
- Gate 3：true；Live/Replay 完全一致。
- 与 SQL-020（V4-flash 26/30，Metric 30/30）相比，V3.2 Execution 低 3 条、Metric 低
  4 条，需要更多修复次数；模型 SQL 生成能力明显更弱但修复闭环可承接部分偏差。

## Acceptance Criteria

1. Passed：30 条 Case、六个 Bucket、兼容/严格参考摘要完整。
2. Passed：所有多标签失败均有主分类，Safety 12/12，Gate 3 passed。
3. Passed：Live/Replay 评测主体、Safety、Gate 和身份字段一致。
4. Passed：如实报告 V3.2 的 23/30 与 V4-flash SQL-020 的 26/30 差异。
5. Passed：历史评测产物未修改。
6. Passed：全量 pytest、Ruff、mypy 与 whitespace Gate 全部通过。

## Known Issues

- V3.2 与 V4-flash 存在明显能力/成本取舍；当前配置保持 V3.2，但模型选择未定。
- J02 NULL category_name_en 的 Golden/Plan 语义冲突、C05/N02/T05 仍待处理。
- 模型非确定性仍需更多轮次或稳定策略，不能由单次 23/30 判定长期水平。

## Diff Review Summary

- 本 Feature 未修改 Runtime、Evaluator、Prompt、Metadata、Policy 或 Golden。
- 本地 `conf/app_config.yaml` 已被切换为 V3.2，但该文件属 Git 忽略，不入库。
- 运行产物写入独立 SQL-022 路径；历史评测产物保持不变。
