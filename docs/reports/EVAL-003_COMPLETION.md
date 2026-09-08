# EVAL-003 Primary Failure Classification Completeness - Completion Report

## Feature

修复只有额外表/列时多标签已判定 Schema 偏差、兼容主分类却为空的问题，并将 Evaluator
升级到 v3，使旧 Replay Cache 继续失败关闭。

## Changed Files

- `app/nl2sql/evaluation.py`
- `app/scripts/evaluate_nl2sql_v1.py`
- `test/nl2sql/test_evaluation.py`
- `test/test_documentation_contract.py`
- `docs/06_evaluation.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `specs/EVAL-003_primary_failure_classification.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- `.\.venv\Scripts\python.exe -m pytest test/nl2sql/test_evaluation.py -q`
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\ruff.exe check .`
- `.\.venv\Scripts\mypy.exe app`
- `git diff --check`
- SQL-010 与历史评测产物 Diff Review

## Test Results

- EVAL-003 专项：11 passed。
- 全量 pytest：374 passed in 16.79 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 114 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- 未评测；本 Feature 不调用真实模型、数据库或检索服务。
- SQL-010 仍为兼容/严格 Execution 26/30、历史 Gate false，不追溯改写。

## Acceptance Criteria

1. Passed：表、列或 JOIN 任何非精确符合均获得 `Schema Linking Error` 主分类。
2. Passed：结果正确且含额外表/列时，Execution 保持正确、Trace 失败并获得主分类。
3. Passed：专项场景验证非空 `failure_labels` 必有非空 `error_category`。
4. Passed：Evaluator 升级为 v3，旧缓存身份不一致时失败关闭。
5. Passed：SQL-010 与更早历史评测产物未修改。
6. Passed：全量 pytest、Ruff、mypy 和 whitespace Gate 全部通过。

## Known Issues

- SQL-010 历史 Gate false 不可变；修复只作用于未来评测。
- T03、C02、C05 的修复 SQL 仍不符合 Plan；J02 仍是可执行结果差异。
- 下一项 SQL-011 只处理 Plan-aware 修复这一共同假设，不包含 J02。

## Diff Review Summary

- Runtime、Prompt、Metadata、Policy、Golden 和历史评测产物均未修改。
- 结果、Trace、Grain、Correction 公式未变化；只收紧兼容主分类条件。
- Cache Schema 仍为 v2，但 Evaluator 身份从 v2 升到 v3，旧缓存不能误复用。
