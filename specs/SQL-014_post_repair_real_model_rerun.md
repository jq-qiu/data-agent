# SQL-014 Post-repair Real-model Rerun

在 Evaluator v3 与 SQL-011~013 修复链上重跑冻结的 30 条 NL2SQL Golden，验证真实
Live/Replay 指标、分类完整性和 C02/T03/C05 假设，不在评测 Feature 中修改 Runtime。

## In Scope

- Live 模式重跑 30 条参考 SQL 和 30 条真实候选，记录严格参考摘要与候选 Cache。
- Replay 模式离线复现并逐字段对账 Evaluation、Safety、Gate 和身份字段。
- 记录兼容/严格 Execution、Trace、Grain、Correction、失败 Case 和 Safety。
- 对比 SQL-010，但明确模型非确定性，不能将所有 Case 变化归因于单一修复。
- 新增独立 SQL-014 报告、Run 目录、文档状态与 Completion Report。

## Out of Scope

- 不修改 Runtime、Evaluator、Prompt、Metadata、Metric Registry、Policy 或 Golden。
- 不在运行过程中修复新失败；后续每个主要假设另建 Feature。
- 不修改 SQL-010 或更早历史产物，不提交 Replay Cache/临时 Replay 输出。

## Allowed Files

- `data/reports/SQL-014_nl2sql_post_repair_evaluation.json`
- `eval_runs/sql-014-post-repair-v1/**`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report

## Commands

```powershell
.\.venv\Scripts\python.exe -m app.scripts.evaluate_nl2sql_v1 `
  --run-id sql-014-post-repair-v1 `
  --report data/reports/SQL-014_nl2sql_post_repair_evaluation.json `
  --run-dir eval_runs/sql-014-post-repair-v1 `
  --mode live `
  --replay-cache .tmp/sql-014-post-repair-v1.json
```

随后使用同一 Cache 在 `.tmp/` 输出 Replay，并比较除时间与运行模式外的全部评测主体。

## Acceptance

- 30 条 Case、六个 Bucket、兼容/严格参考摘要完整。
- 所有多标签失败都有主分类，Safety 12/12，Gate 3 通过。
- Live/Replay 评测主体及身份字段一致。
- 报告 C02/T03/C05 和总体结果，不预设提升。
- SQL-010 与历史产物未修改；全量 pytest、Ruff、mypy、`git diff --check` 通过。
