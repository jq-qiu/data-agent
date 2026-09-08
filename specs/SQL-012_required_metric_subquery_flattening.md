# SQL-012 Required Metric Subquery Flattening

针对 SQL-010 T03 的单一失败假设：一次 LLM 修复把单表指标聚合包进无必要派生表，导致
物理必需指标列 Trace 丢失，并携带未使用的方案外投影。对严格满足安全形状的修复 SQL
执行确定性扁平化，再送回同一 Validator。

## In Scope

- 只处理外层单一 `SELECT` 从一个派生表读取、内层只从一个 Plan 表读取的形状。
- 内层禁止 JOIN、聚合、GROUP BY、HAVING、ORDER BY、LIMIT、DISTINCT 和窗口函数。
- 外层禁止 JOIN 和已有 WHERE；仅把外层引用的派生列映射回内层裸物理列。
- 将内层 WHERE 原样提升到外层，丢弃没有被外层引用的冗余内层投影。
- 所有最终使用列必须属于 Plan，且 Plan 必须声明 `required_metric_columns`。
- 单元测试、设计文档、状态和独立 Completion Report。

## Out of Scope

- 不处理多表/CTE/嵌套派生表、分组 TopN 或任何会改变聚合层级的结构。
- 不处理 C02 日历 Literal、C05 GROUP BY 或 J02 结果差异。
- 不修改 Validator、Prompt、Golden、Metadata、Metric Registry、Policy 或历史评测产物。
- 不增加修复轮数，不运行真实模型复测。

## Allowed Files

- `app/nl2sql/repair.py`
- `app/agent/nodes/correct_sql.py`
- `test/nl2sql/test_sql_repair.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report

## Acceptance

- T03 形状扁平为同一物理表聚合，并保留原日期过滤和输出 Alias。
- 未使用的内层 `region_id` 投影不会进入结果 SQL。
- Alias 投影可正确映射回物理列。
- 多表、内层聚合/分组/排序/Limit/Distinct、外层 WHERE、方案外列或无必需指标列 Plan
  均安全保持原 SQL。
- 扁平化结果仍必须通过原 Validator；修复轮数与安全规则不变。
- SQL-010 与历史评测产物未修改；全量 pytest、Ruff、mypy、`git diff --check` 通过。
