# EVAL-002 NL2SQL Evaluation Integrity - Completion Report

## Feature

升级 NL2SQL 评测可信度契约：兼容历史结果口径的同时新增投影位置敏感结果比较，分离
Validator、Trace 与 Grain 指标，要求修复后结果正确，并让 Replay 身份覆盖实际运行代码。

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
- `specs/EVAL-002_nl2sql_evaluation_integrity.md`
- 本 Completion Report

## Added Dependencies

- 无。

## Commands Executed

- `.\.venv\Scripts\python.exe -m pytest test/nl2sql/test_evaluation.py -q`
- `.\.venv\Scripts\python.exe -m pytest`
- `.\.venv\Scripts\ruff.exe check .`
- `.\.venv\Scripts\mypy.exe app`
- `git diff --check`
- Changed-file、历史评测产物和完整 Diff Review

## Test Results

- EVAL-002 专项：10 passed。
- 全量 pytest：373 passed in 15.55 seconds。

## Lint Results

- Ruff：0 findings。
- `git diff --check`：no whitespace errors。

## Type Check Results

- mypy：Success, no issues found in 114 source files。
- Client manager 未检查无类型函数体的既有信息提示仍存在，不是 mypy error。

## Evaluation Results

- 未评测；本 Feature 未调用真实 LLM、MySQL、Qdrant 或 Elasticsearch。
- SQL-008 的兼容 Execution Accuracy `22/30` 仍是最近一次真实结果。
- 新增 Strict Execution、Trace/Grain 和严格 Correction 口径须由 SQL-010 首次实测。

## Acceptance Criteria

1. Passed：兼容 checksum 继续忽略 Alias/投影顺序，严格 checksum 可识别投影值交换。
2. Passed：Live 严格参考摘要进入 Replay Cache，类型安全重放保持完整评测主体一致。
3. Passed：缺少严格参考摘要时 Strict Execution 明确为 unavailable，可信 Gate 不通过。
4. Passed：Validator Acceptance 与风险 Case 的 Trace/Grain 契约分别统计。
5. Passed：修复后仅可执行但结果错误时，兼容和严格 Correction Success 均为失败。
6. Passed：同一 Case 可同时记录 Schema、结果形状、结果值和 Grain 失败标签。
7. Passed：Replay v2 身份绑定 Dataset、Prompt、运行时代码、Metadata、Policy、模型、
   Evaluator、提交和 Dirty 状态，任一不一致均拒绝加载。
8. Passed：专项、全量 pytest、Ruff、mypy 与 whitespace Gate 全部通过。

## Known Issues

- SQL-010 尚未执行；不能依据评测器单元测试宣称 SQL-009 提升了 22/30。
- Strict Execution 依赖 Live 重跑参考 SQL；使用 `--skip-reference` 时明确不可用。
- Token/Cost 仍 unavailable，因为当前图没有暴露模型用量。

## Diff Review Summary

- 未修改 NL2SQL 生成运行时、Prompt、Metadata、Metric Registry、SQL Policy 或 Golden。
- 未修改 SQL-002、SQL-005、SQL-008 等历史评测产物。
- `execution_accuracy` 保留历史可比性；新增严格口径不追溯改写旧分数。
- Grain 只在 Golden 已标注粒度风险的 Case 上计分，不用 SQL Validity 冒充全量 Grain。
