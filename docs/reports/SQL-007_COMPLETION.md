# SQL-007 NL2SQL Live/Replay Evaluation - Completion Report

## Feature

为 NL2SQL 评测器增加 Live/Replay 双模式。Live 运行记录完整 `NL2SQLRun`，Replay 在
不初始化模型、检索、MySQL 等外部客户端且不执行参考 SQL 的情况下复现评测。

## Changed Files

- `app/nl2sql/evaluation.py`
- `app/scripts/evaluate_nl2sql_v1.py`
- `test/nl2sql/test_evaluation.py`
- `docs/06_evaluation.md`
- `README.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `specs/SQL-007_live_replay_evaluation.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- `.\.venv\Scripts\python.exe -m app.scripts.evaluate_nl2sql_v1 --help`
- `.\.venv\Scripts\python.exe -m pytest test/nl2sql/test_evaluation.py -q`
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\ruff.exe check .`
- `.\.venv\Scripts\mypy.exe app`
- `git diff --check`

## Test Results

- pytest: 352 passed
- Replay 专项：3 passed
- Live 记录结果与 Replay 结果结构完全一致

## Lint Results

- Ruff: 0 findings
- `git diff --check`: no whitespace errors

## Type Check Results

- mypy: no issues in 114 source files

## Evaluation Results

- 未评测；本 Feature 未调用真实模型或执行 30 条 Live 复测。

## Acceptance Criteria

- Live 运行逐 Case 写入本地 Replay Cache
- Replay 保留 Decimal、日期时间、bytes 等数据库标量类型
- Dataset/Prompt/Metadata/Policy/Model/Evaluator 身份不一致时失败关闭
- Cache 内容摘要被篡改、Case 集不完整或多余时失败关闭
- Replay 分支不初始化外部客户端、不执行参考 SQL
- 全量 pytest、Ruff、mypy 通过

## Known Issues

- 默认 Cache 位于 Git 忽略的 `.tmp/`，不会作为长期评测产物提交。
- SQL-006 后的真实模型 30 条复测属于 SQL-008。

## Diff Review Summary

- 历史 SQL-002/SQL-005 Golden 与评测产物未修改。
- Cache 不包含凭据或连接信息，默认路径不会进入 Git。
- Replay 仅复现已记录候选，不宣称替代真实模型评测。
