# SQL-013 Structured Plan Repair Constraints

针对 SQL-010 C05 的单一失败假设：完整 Plan YAML 虽已传给 LLM 修复，但错误相关的
Calendar Join、精确 GROUP BY/ORDER BY 约束不够显著，模型把分组查询改写成条件聚合。
从冻结 Plan 生成短、确定、错误导向的修复约束，仍由同一 Validator 最终裁决。

## In Scope

- 从 SchemaLinkingPlan 格式化允许表、必需指标列、Calendar Table、精确 Join、
  GROUP BY、ORDER BY 和固定过滤。
- 当错误为 GROUP BY 偏差时，明确禁止把分组值透视成多个条件聚合输出。
- 将结构化约束作为独立 Prompt 变量注入一次性 LLM 修复。
- 无 Plan 时输出明确的 unavailable 文本，不创造约束。
- 单元测试、Prompt 契约测试、设计文档、状态和独立 Completion Report。

## Out of Scope

- 不用 AST 自动生成聚合公式、Join 或业务过滤，不替代 LLM 修复。
- 不处理 C02、T03 或 J02，不增加修复轮数。
- 不放宽 Validator，不修改 Golden、Metadata、Metric Registry、Policy 或历史评测产物。
- 不运行真实模型复测。

## Allowed Files

- `app/nl2sql/repair.py`
- `app/agent/nodes/correct_sql.py`
- `prompts/correct_sql.prompt`
- `test/nl2sql/test_sql_repair.py`
- `test/nl2sql/test_runtime_adaptation.py`
- `test/test_documentation_contract.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- 本 Spec 与 Completion Report

## Acceptance

- C05 形状的 Plan 约束明确列出 fact_order→dim_date Join、精确 Group/Order 和 Calendar。
- GROUP BY 错误约束明确禁止条件聚合透视，并要求每组一行。
- 过滤的 include/exclude 方向和值完整呈现；无 Plan 不虚构内容。
- Repair Prompt 必须包含并传入结构化约束，LLM 调用次数和 Validator 回路不变。
- SQL-010 与历史评测产物未修改。
- 全量 pytest、Ruff、mypy 和 `git diff --check` 通过。
