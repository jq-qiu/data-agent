# SQL-010 Post-SQL-009 Real-model Rerun - Completion Report

## Feature

在 EVAL-002 评测器上完成 SQL-009 后的 30 条真实模型 Live/Replay 复测，同时首次记录
严格结果、独立 Trace/Grain 和严格 Correction 指标。

## Changed Files

- `data/reports/SQL-010_nl2sql_post_semantics_evaluation.json`
- `eval_runs/sql-010-post-semantics-v1/summary.json`
- `eval_runs/sql-010-post-semantics-v1/nl2sql_results.csv`
- `eval_runs/sql-010-post-semantics-v1/error_analysis.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- `specs/SQL-010_post_semantics_real_model_rerun.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL-010 Live 命令（重跑参考 SQL，未使用 `--skip-reference`）
- SQL-010 Replay 命令（临时报告与 Run 目录位于 `.tmp/`）
- PowerShell JSON 字段级 Live/Replay 对账
- SQL-008/SQL-010 Case 与 Bucket 差异分析
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\ruff.exe check .`
- `.\.venv\Scripts\mypy.exe app`
- `git diff --check`

## Test Results

- 全量 pytest：373 passed in 15.78 seconds。
- 首次收口运行有 1 条过时文档契约失败；同步 Current/Next Feature 后最终全绿。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 114 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- Case：30/30；六个 Bucket 各 5 条；严格参考摘要 30/30。
- Compatible / Strict Execution Accuracy：26/30（86.67%），两种口径本次一致。
- SQL Validity / Executability / Validator Acceptance：27/30（90%）。
- Metric Accuracy：29/30（96.67%）；Trace Conformance：16/30（53.33%）。
- Grain Contract：5/15（33.33%）；Correction：2/6（33.33%），严格口径相同。
- Bucket Execution：Simple 5/5、Aggregate 5/5、Time 4/5、JOIN 4/5、TopN 5/5、
  Comparison 3/5。
- 结果失败：T03、J02、C02、C05。相对 SQL-008，S03、S04、A05、J03、C04 转为通过，
  T03 新增失败；模型运行具有非确定性，不能把 Case 变化全部归因于单一规则。
- Safety：12/12 危险 SQL 被拒绝，危险放行 0。
- Live/Replay：Evaluation、Safety、Gate、Dataset、Prompt、Runtime、Model、Database 和
  Cache 摘要字段全部一致。
- Gate 3：false。`N04`、`C01` 仅有额外 Schema Trace；多标签有
  `Schema Linking Error`，但兼容 `error_category` 主分类为空。

## Acceptance Criteria

1. Passed：30 条 Case、六个 Bucket、兼容和严格参考摘要完整。
2. Passed：兼容/严格 Execution、Trace、Grain 与 Correction 全部按新契约报告。
3. Partial：Safety 通过且多标签完整，但 2 条失败缺少兼容主分类，Gate 为 false。
4. Passed：Live/Replay 评测主体、Safety、Gate 和身份字段完全一致。
5. Passed：历史 SQL-002/005/008 产物未修改，Replay Cache 与临时报告未进入 Git。
6. Passed：全量 pytest、Ruff、mypy 和 whitespace Gate 全部通过。

## Known Issues

- EVAL-002 的主分类仍按 Table/Column Recall 判断，无法分类只有额外表/列的 Trace 偏差；
  EVAL-003 将只修此评测缺陷，不修改本次真实产物。
- T03、C02、C05 在一次修复后仍被 Validator 拒绝；J02 可执行但结果不匹配。
- 14/30 Case 的完整 Trace 不符合 Golden；10/15 Grain 风险 Case 不符合 Grain 契约。
- Qdrant client 1.16.2 与 server 1.19.0 的既有版本兼容警告仍存在，本次未中断。
- Token/Cost 仍 unavailable，因为当前图没有暴露模型用量。

## Diff Review Summary

- 本 Feature 未修改 `app/`、Prompt、Metadata、Policy、Golden 或评测器代码。
- 所有运行产物写入独立 SQL-010 路径，SQL-002/005/008 历史产物保持不变。
- Replay Cache 与临时 Replay 输出位于 Git 忽略的 `.tmp/`，不纳入提交。
- 报告保留 Gate false，不用 26/30 掩盖分类完整性缺陷。
