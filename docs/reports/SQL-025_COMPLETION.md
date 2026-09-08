# SQL-025 Post-SQL-024 Real-model Rerun - Completion Report

## Feature

在 SQL-024 Daily GMV DWS Source and Projection Contract 后，以
`deepseek-ai/DeepSeek-V4-flash` 在相同代码/Golden/Evaluator 上完成 30 条真实
Live/Replay，验证 T05 是否转通过并检查整体回退。本 Feature 只评测，不修改
Runtime/Evaluator/Prompt/Metadata/Policy/Golden。

## Changed Files

- `data/reports/SQL-025_nl2sql_v4_post_sql024_evaluation.json`
- `eval_runs/sql-025-v4-post-sql024-v1/summary.json`
- `eval_runs/sql-025-v4-post-sql024-v1/nl2sql_results.csv`
- `eval_runs/sql-025-v4-post-sql024-v1/error_analysis.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-025_v4_post_sql024_real_model_rerun.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL-025 Live：`python -m app.scripts.evaluate_nl2sql_v1 --run-id
  sql-025-v4-post-sql024-v1 --mode live`
- SQL-025 Replay：同 Cache、`--mode replay`，报告与 Run 目录位于 Git 忽略的 `.tmp/`
- Live/Replay JSON 字段级逐项对账
- SQL-023 与 SQL-025 逐 Case 差异分析
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\ruff.exe check .`
- `.\.venv\Scripts\mypy.exe app`
- `git diff --check`

## Test Results

- 全量 pytest：410 passed（SQL-024 基线；本 Feature 未改代码，只更新文档契约预期）。
- Documentation contract：通过。

## Lint Results

- Ruff：All checks passed。
- `git diff --check`：无 whitespace errors。

## Type Check Results

- mypy：Success，no issues found in 115 source files。

## Evaluation Results

- Model：`deepseek-ai/DeepSeek-V4-flash`（temperature 0）。
- Compatible / Strict Execution：27/30（90%）。
- Metric Accuracy：30/30（100%）。
- Validator Acceptance / Validity / Executability：29/30。
- Trace Conformance：20/30（66.7%）；Grain Contract：9/15（60%）。
- Correction：0/2 succeeded。
- Safety：12/12 rejected；Dangerous SQL Allowed：0。
- Gate 3：true；Live/Replay 评测主体、Safety、Gate、身份字段完全一致。
- Head-to-head vs SQL-023（同模型、SQL-021 代码）：
  - T04、T05、N02 由 0 转 1；
  - N01 由 1 转 0（生成冗余双层窗口派生表，Validator 以 JOIN 未登记拒绝；
    结论为模型非确定性/形状漂移，SQL-024 未触及该路径）；
  - J02（Golden/Plan NULL 分组语义冲突）与 C05（Pivot）仍失败；
  - 净提升 +2，无 SQL-024 相关回退。

## Acceptance Criteria

1. Passed：SQL-024 代码、干净工作树、V4-flash 上完成 30 条 Live。
2. Passed：Replay 身份校验通过，Live/Replay 逐 Case、Safety、Gate 与身份字段一致。
3. Passed：T05 从 SQL-023 的 0 转为 1，生成的规范 SQL 直接通过，无修复。
4. Passed：总体 27/30 并逐项对比 SQL-023，明确 N01 为模型非确定性回退。
5. Passed：Safety 12/12，Gate 3 true，历史评测产物未修改。
6. Passed：全量 pytest、Ruff、mypy、`git diff --check` 通过。

## Known Issues

- N01 是本轮唯一 Execution 回退，需后续 Feature 用 Plan 最终投影/无冗余包装约束处理
  或接受模型非确定性波动。
- J02 仍是 Golden/Plan 语义冲突（NULL category_name_en），待产品裁决。
- C05 仍输出 Calendar × Status Pivot，待 Plan-driven Composer/禁止 Pivot 约束处理。
- 大量 Trace Deviation（10/30）不进入 Execution 失败；若作为验收口径需单独 Feature。

## Diff Review Summary

- 本 Feature 未修改 Runtime、Evaluator、Prompt、Metadata、SQL Policy 或 Golden。
- Live 产物与 SQL-023/SQL-022 保持相同目录结构，历史评测产物不变。
- Replay Cache 位于 Git 忽略的 `.tmp/`，仅报告与 Run 摘要入库。
