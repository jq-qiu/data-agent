# EVAL-002 NL2SQL Evaluation Integrity

修复 NL2SQL 评测器中会高估结果正确性、Grain 与修复成功率，或让 Replay 在运行时代码
变化后仍被错误复用的可信度缺口。本 Feature 只修改评测契约，不执行真实模型复测。

## In Scope

- 保留历史 `execution_accuracy` 的值集合兼容口径，并新增保留投影位置与列数的严格结果口径。
- Live 运行记录严格参考结果摘要；Replay 必须从同一缓存恢复该摘要并复现相同评测主体。
- 将 Trace 精确符合、Golden 粒度契约符合与 Validator 接受率分开报告。
- Correction Success 必须要求修复后的结果正确，不能只要求 SQL 可执行。
- 一条 Case 可同时记录多个失败标签；保留单一主错误分类供历史消费者兼容。
- Replay 身份加入当前提交、运行时代码摘要和工作树状态，代码变化后旧缓存必须失效。
- 更新单元测试、评测设计文档和当前状态文档。

## Out of Scope

- 不修改 NL2SQL 运行时、Prompt、Metadata、Metric Registry、SQL Policy 或 Golden Dataset。
- 不修改 SQL-002、SQL-005、SQL-008 等历史评测产物。
- 不运行真实 LLM、MySQL、Qdrant 或 Elasticsearch 复测，不更新 22/30 的当前实测结论。
- 不新增 Token/Cost 采集；当前图未暴露该用量时继续明确标为 unavailable。
- 不提前执行 SQL-010 或按旧失败继续增加 Runtime 规则。

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

## Metric Contract

- `execution_accuracy`：兼容历史报告，只比较每行值的集合，不检查投影位置。
- `strict_execution_accuracy`：逐行保留投影位置和列数，未排序结果只忽略行顺序。
- `trace_conformance_rate`：Metric、表、列和 JOIN Trace 全部精确符合 Golden。
- `validator_acceptance_rate`：仅表示 SQL 通过 Validator，不冒充独立 Grain 结论。
- `grain_contract_accuracy`：只对带 Grain 风险标签的 Case 计分，要求有效 SQL、Metric、表、列和 JOIN 全部符合 Golden。
- `correction_success_rate`：发生修复后，必须有效、可执行且兼容结果正确。
- `strict_correction_success_rate`：发生修复且严格参考摘要可用时，必须严格结果正确。

## Acceptance

- 交换同一行的投影值时，兼容 checksum 可相同，但严格 checksum 必须不同。
- Live 产生的严格参考摘要进入 Replay Cache；Replay 结果与 Live 评测主体一致。
- 缺少严格参考摘要时不会把严格准确率伪报为 0 或 1，而是明确不可用。
- `grain_safety_rate` 不再等同于 SQL Validity；输出独立 Grain 契约口径及适用 Case 数。
- 修复后仅可执行但结果错误的 Case 不计为 Correction Success。
- 结果错误与 Trace 偏差可同时出现在失败标签中，并在错误分析中分开展示。
- Replay Cache 在运行时代码摘要、提交或工作树状态不一致时拒绝加载。
- 全量 pytest、Ruff、mypy 和 `git diff --check` 通过。
