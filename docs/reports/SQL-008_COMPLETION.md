# SQL-008 NL2SQL Metric/Calendar Real-Model Rerun - Completion Report

## Feature

在 SQL-006 指标/日历约束和 SQL-007 Live/Replay 评测器上，对冻结的 30 条 NL2SQL
Golden 执行真实模型复测，并把结果写入独立 SQL-008 产物。

## Changed Files

- `data/reports/SQL-008_nl2sql_metric_calendar_evaluation.json`
- `eval_runs/sql-008-metric-calendar-v1/summary.json`
- `eval_runs/sql-008-metric-calendar-v1/nl2sql_results.csv`
- `eval_runs/sql-008-metric-calendar-v1/error_analysis.md`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `specs/SQL-008_metric_calendar_rerun.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- SQL-008 Live 命令（`--skip-reference --mode live`）
- SQL-008 Replay 命令（临时报告与 Run 目录，`--mode replay`）
- PowerShell JSON 字段级 Live/Replay 对账
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\ruff.exe check .`
- `.\.venv\Scripts\mypy.exe app`
- `git diff --check`

## Test Results

- pytest: 352 passed
- SQL-002/SQL-005 历史产物 Git diff: 0 files

## Lint Results

- Ruff: 0 findings
- `git diff --check`: no whitespace errors

## Type Check Results

- mypy: no issues in 114 source files

## Evaluation Results

- Case：30/30；六个 Bucket 各 5 条
- Execution Accuracy：22/30（73.33%），SQL-005 为 19/30
- SQL Validity / Executability / Grain Safety：30/30
- Metric Accuracy：28/30
- Table Recall：91.67%；Column Recall：85.50%；JOIN Accuracy：83.33%
- Bucket Execution：Simple 3/5、Aggregate 4/5、Time 5/5、JOIN 3/5、TopN 5/5、Comparison 2/5
- Safety：12/12 固定危险 SQL 被拒绝，危险放行 0
- Gate 3：passed
- Live/Replay：评测、Safety、Gate、版本、模型、数据库和 Cache 摘要字段无差异

## Acceptance Criteria

- 30 条 Case 和六个 Bucket 完整记录
- 30 条冻结参考校验和全部确认
- 每个失败均已分类，危险 SQL 放行 0
- Live/Replay 评测主体完全一致
- SQL-002/SQL-005 历史产物未修改
- 全量 pytest、Ruff、mypy 通过

## Known Issues

- C04 把 `dim_date.month`（`YYYY-MM`）与整数 `(4, 5)` 比较，产生 MySQL 类型转换警告并结果不匹配。
- C02 多投影 `year`，C05 无法在 DWS 整体订单口径下表达订单状态拆分。
- S03/S04 与 J02 仍有稳定排序/结果结构不匹配；J03 缺少有效订单状态过滤。
- Qdrant client 1.16.2 与 server 1.19.0 存在版本兼容警告，本次运行未中断。

## Diff Review Summary

- 本 Feature 只新增 SQL-008 评测证据和文档，没有修改运行时代码、Prompt、Policy 或 Golden。
- Replay Cache 与临时 Replay 报告保留在 Git 忽略的 `.tmp/`，未进入提交。
- SQL-002 和 SQL-005 历史报告及 Run 目录保持不变。
