# EVAL-003 Primary Failure Classification Completeness

修复 SQL-010 真实运行暴露的兼容单主错误分类遗漏：当候选 Trace 包含 Golden 之外的
额外表或列时，多标签已判定 Schema 偏差，但 `classify_failure` 只检查 Recall，错误返回空。

## In Scope

- 主错误分类使用表、列和 JOIN 的精确符合判断，与 `failure_labels` 的 Schema 判定一致。
- 增加“结果正确但存在额外表/列”回归测试，保证主分类为 `Schema Linking Error`。
- 增加所有多标签失败都存在主分类的单元契约。
- 升级 Evaluator 版本，使旧 Replay Cache 失败关闭。
- 更新评测设计、状态、计划与独立 Completion Report。

## Out of Scope

- 不修改 NL2SQL Runtime、Prompt、Metadata、Metric Registry、Policy 或 Golden。
- 不修改或重算 SQL-010 及更早历史评测产物；SQL-010 的 Gate false 保持历史事实。
- 不运行真实模型或外部服务，不处理 T03/J02/C02/C05 Runtime 失败。
- 不改变兼容/严格结果、Trace、Grain 或 Correction 公式。

## Allowed Files

- `app/nl2sql/evaluation.py`
- `app/scripts/evaluate_nl2sql_v1.py`
- `test/nl2sql/test_evaluation.py`
- `test/test_documentation_contract.py`
- `docs/06_evaluation.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- 本 Spec 与 Completion Report

## Acceptance

- 额外表、额外列、缺少表、缺少列和 JOIN 偏差均得到 `Schema Linking Error` 主分类。
- 结果正确但 Trace 不精确的 Case 仍计为结果正确，同时被分类为结构失败。
- 任何非空 `failure_labels` 都有非空 `error_category`。
- Evaluator 版本变化后 EVAL-002/SQL-010 旧缓存不能直接重放。
- SQL-010 和历史评测产物 Git Diff 为零。
- 全量 pytest、Ruff、mypy 和 `git diff --check` 通过。
