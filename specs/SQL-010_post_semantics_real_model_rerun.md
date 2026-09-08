# SQL-010 Post-SQL-009 Real-model Rerun

在 EVAL-002 可信评测器上，对 SQL-009 后的冻结 30 条 NL2SQL Golden Dataset 执行
真实模型 Live/Replay 复测，并以新产物记录兼容与严格结果、Trace、Grain 和 Correction。

## In Scope

- Live 模式连接当前配置的 LLM、Embedding、Qdrant、Elasticsearch 与隔离 V1 DW。
- 重跑全部 30 条参考 SQL，以生成严格参考结果摘要；不得使用 `--skip-reference`。
- 将候选运行与严格参考摘要写入 Git 忽略的 Replay Cache。
- Replay 模式不初始化外部服务，复现同一评测主体并进行字段级对账。
- 新增独立 SQL-010 JSON、CSV、Summary 和 Error Analysis 产物。
- 报告兼容/严格 Execution、Validator、Trace、Grain、Correction、Safety 与失败标签。
- 更新 README、实施状态、计划索引和独立 Completion Report。

## Out of Scope

- 不修改 NL2SQL 运行时、Evaluator、Prompt、Metadata、Metric Registry、Policy 或 Golden。
- 不根据本次失败继续实现 Runtime Remediation；后续每个主要失败假设另建 Feature。
- 不修改 SQL-002、SQL-005、SQL-008 等历史评测产物。
- 不提交 Replay Cache、凭据、连接配置或额外临时产物。

## Allowed Files

- `data/reports/SQL-010_nl2sql_post_semantics_evaluation.json`
- `eval_runs/sql-010-post-semantics-v1/**`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report

## Commands

```powershell
.\.venv\Scripts\python.exe -m app.scripts.evaluate_nl2sql_v1 `
  --run-id sql-010-post-semantics-v1 `
  --report data/reports/SQL-010_nl2sql_post_semantics_evaluation.json `
  --run-dir eval_runs/sql-010-post-semantics-v1 `
  --mode live `
  --replay-cache .tmp/sql-010-post-semantics-v1.json
```

随后以 `--mode replay` 写入 `.tmp/` 下的临时报告/目录，并比较除生成时间和运行模式外的
评测主体、Safety、Gate、版本、模型、数据库、运行时摘要与 Cache 摘要。

## Acceptance

- 30 条 Case、六个五条 Bucket、兼容参考摘要和严格参考摘要完整记录。
- 兼容与严格 Execution、Trace、Grain、Correction 均按 EVAL-002 契约报告。
- 12 条危险 SQL 全部拒绝，所有失败 Case 都有主分类及多标签证据。
- Live 与 Replay 的评测主体、Safety、Gate 和身份字段一致。
- 历史 SQL-002/005/008 产物未修改，Replay Cache 未进入 Git。
- 全量 pytest、Ruff、mypy 和 `git diff --check` 通过。
