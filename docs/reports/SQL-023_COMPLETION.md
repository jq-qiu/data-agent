# SQL-023 V4-flash Head-to-head Rerun - Completion Report

## Feature

用户回退模型到 `deepseek-ai/DeepSeek-V4-flash` 后，以与 SQL-022(V3.2) 完全相同的
代码版本完成 30 条真实 Live/Replay，得到可对标的 V4-flash 结果。

## Changed Files

- `data/reports/SQL-023_nl2sql_v4_post_sql021_evaluation.json`
- `eval_runs/sql-023-v4-post-sql021-v1/summary.json`
- `eval_runs/sql-023-v4-post-sql021-v1/nl2sql_results.csv`
- `eval_runs/sql-023-v4-post-sql021-v1/error_analysis.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-023_v4_post_sql021_real_model_rerun.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL-023 Live 命令（DeepSeek-V4-flash，未使用 `--skip-reference`）
- SQL-023 Replay 命令（临时报告与 Run 目录位于 `.tmp/`）
- PowerShell JSON 字段级 Live/Replay 对账
- SQL-022(V3.2)/SQL-023(V4) Head-to-head 差异分析
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

- Model：`deepseek-ai/DeepSeek-V4-flash`（本地 conf/app_config.yaml）。
- Compatible / Strict Execution：25/30（83.33%）。
- Metric Accuracy：29/30（96.67%）。
- Validator Acceptance / Validity / Executability：30/30。
- Trace Conformance：17/30（56.67%）；Grain Contract：5/15（33.33%）。
- Correction：1/3。
- Gate 3：true；Live/Replay 完全一致。
- Head-to-head：V4-flash 25/30（Metric 29/30）显著高于 V3.2 的 23/30（Metric 26/30），
  且无回退（J01、N04 从失败转通过）。

## Acceptance Criteria

1. Passed：与 SQL-022 相同的代码/Golden/Evaluator 上完成 V4 复测。
2. Passed：所有多标签失败均有主分类，Safety 12/12，Gate 3 passed。
3. Passed：Live/Replay 评测主体、Safety、Gate 和身份字段一致。
4. Passed：如实报告 25/30 与 V3.2 23/30 的逐项差异。
5. Passed：历史评测产物未修改。
6. Passed：全量 pytest、Ruff、mypy 与 whitespace Gate 全部通过。

## Known Issues

- V4-flash 是当前模型选择；模型非确定性仍可能使后续单次结果波动。
- T04/T05/J02/N02/C05 仍是 SQL-023 剩余失败。
- J02 NULL category_name_en 的 Golden/Plan 分组语义冲突待裁决。

## Diff Review Summary

- 本 Feature 未修改 Runtime、Evaluator、Prompt、Metadata、Policy 或 Golden。
- 本地模型配置保持 V4-flash（Git 忽略，不入库）。
- 运行产物写入独立 SQL-023 路径；历史评测产物保持不变。
