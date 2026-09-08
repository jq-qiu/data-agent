# SQL-022 Post-SQL-021 Real-model Rerun (DeepSeek-V3.2)

在 Evaluator v3、SQL-011~013/015/017/019/021 修复链上，以
`deepseek-ai/DeepSeek-V3.2` 重跑冻结的 30 条 NL2SQL Golden，验证 Daily DWS date_id
分组与模型切换后的真实结果；本 Feature 只评测。

## In Scope

- Live 模式重跑 30 条参考 SQL 与候选，写入严格参考摘要与 Git 忽略的 Replay Cache。
- Replay 模式离线复现并逐字段对账 Evaluation、Safety、Gate 与身份字段。
- 记录兼容/严格 Execution、Trace、Grain、Correction 与失败 Case。
- 对比 SQL-018/020，明确模型非确定性，不能把 Case 变化全部归因于修复。
- 新增独立 SQL-022 报告、Run 目录、文档状态与 Completion Report。

## Out of Scope

- 不修改 Runtime、Evaluator、Prompt、Metadata、Metric Registry、Policy 或 Golden。
- 不处理 J02 Golden/Plan 语义冲突、C05/N02 或模型非确定性。
- 不修改历史评测产物，不提交 Replay Cache/临时输出。

## Allowed Files

- `data/reports/SQL-022_nl2sql_v32_post_sql021_evaluation.json`
- `eval_runs/sql-022-v32-post-sql021-v1/**`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report

## Commands

```powershell
.\.venv\Scripts\python.exe -m app.scripts.evaluate_nl2sql_v1 `
  --run-id sql-022-v32-post-sql021-v1 `
  --report data/reports/SQL-022_nl2sql_v32_post_sql021_evaluation.json `
  --run-dir eval_runs/sql-022-v32-post-sql021-v1 `
  --mode live `
  --replay-cache .tmp/sql-022-v32-post-sql021-v1.json
```

随后用同一 Cache 在 `.tmp/` 输出 Replay 并比较全部评测主体与身份字段。

## Acceptance

- 30 条 Case、六个 Bucket、兼容/严格参考摘要完整。
- 所有多标签失败都有主分类，Safety 12/12，Gate 3 通过。
- Live/Replay 评测主体及身份字段一致。
- 报告 T05 与总体结果，不预设提升；历史评测产物未修改。
- 全量 pytest、Ruff、mypy、`git diff --check` 通过。
