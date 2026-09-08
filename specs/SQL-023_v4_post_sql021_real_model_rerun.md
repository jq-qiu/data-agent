# SQL-023 V4-flash Post-SQL-021 Head-to-head Rerun

在用户确认回退到 DeepSeek-V4-flash 后，以与 SQL-022(V3.2) 完全相同的代码、Golden 与
Evaluator 版本重跑 30 条 Live/Replay，得到可对标的 V4-flash 结果。

## In Scope

- 以 `deepseek-ai/DeepSeek-V4-flash` 执行 SQL-021 后代码上的完整 Live/Replay。
- 记录兼容/严格 Execution、Metric、Trace、Grain、Correction 与 Safety。
- 与 SQL-022(V3.2) 同版本逐项对比。
- 新增独立 SQL-023 报告/Run 目录与 Completion Report。

## Out of Scope

- 不修改 Runtime、Evaluator、Prompt、Metadata、Policy、Golden 或历史产物。
- 不现场修复失败；后续 Feature 另行立项。

## Allowed Files

- `data/reports/SQL-023_nl2sql_v4_post_sql021_evaluation.json`
- `eval_runs/sql-023-v4-post-sql021-v1/**`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report
