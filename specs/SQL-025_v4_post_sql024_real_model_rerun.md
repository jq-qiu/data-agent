# SQL-025 Post-SQL-024 Real-model Rerun (DeepSeek-V4-flash)

在 Evaluator v3、SQL-011~013/015/017/019/021/024 修复链上，以
`deepseek-ai/DeepSeek-V4-flash` 重跑冻结的 30 条 NL2SQL Golden，验证 SQL-024
Daily GMV DWS Source and Projection Contract 是否让 T05 转通过，并检查是否存在
其它 Case 回退；本 Feature 只评测。

## Precondition

- SQL-024 已提交且工作树干净后再执行，使 Replay Cache 身份绑定 SQL-024 提交；
  若因用户选择保留未提交改动，必须在报告中明确记录 Dirty 状态。
- 本地模型配置保持 `deepseek-ai/DeepSeek-V4-flash`（Git 忽略，不入库）。

## In Scope

- Live 模式重跑 30 条参考 SQL 与候选，写入严格参考摘要与 Git 忽略的 Replay Cache。
- Replay 模式离线复现并逐字段对账 Evaluation、Safety、Gate 与身份字段。
- 记录兼容/严格 Execution、Metric、Trace、Grain、Correction 与失败 Case。
- 逐项对比 SQL-023(V4-flash，SQL-021 代码) 与 SQL-025(V4-flash，SQL-024 代码)，
  明确 T05 是否转通过及整体是否回退；模型非确定性造成的波动必须如实报告。
- 新增独立 SQL-025 报告、Run 目录、文档状态与 Completion Report。

## Out of Scope

- 不修改 Runtime、Evaluator、Prompt、Metadata、Metric Registry、SQL Policy 或 Golden。
- 不现场修复 SQL-025 新发现的失败；后续 Feature 另行立项。
- 不修改 J02 Golden/Plan 语义冲突、T04/N02/C05 或模型非确定性。
- 不修改历史评测产物，不提交 Replay Cache/临时输出。

## Allowed Files

- `data/reports/SQL-025_nl2sql_v4_post_sql024_evaluation.json`
- `eval_runs/sql-025-v4-post-sql024-v1/**`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report

## Commands

```powershell
.\.venv\Scripts\python.exe -m app.scripts.evaluate_nl2sql_v1 `
  --run-id sql-025-v4-post-sql024-v1 `
  --report data/reports/SQL-025_nl2sql_v4_post_sql024_evaluation.json `
  --run-dir eval_runs/sql-025-v4-post-sql024-v1 `
  --mode live `
  --replay-cache .tmp/sql-025-v4-post-sql024-v1.json
```

随后用同一 Cache 在 `.tmp/` 输出 Replay 并比较全部评测主体与身份字段，再执行
SQL-023 与 SQL-025 的 T05/总体逐项差异分析。

## Acceptance

- 30 条 Case、六个 Bucket、兼容/严格参考摘要完整。
- Safety 12/12，Gate 3 通过；所有多标签失败都有主分类。
- Live/Replay 评测主体及身份字段一致。
- 报告 T05 是否转通过与总体 30 条结果，不预设提升；历史评测产物未修改。
- 全量 pytest、Ruff、mypy 与 `git diff --check` 通过。
