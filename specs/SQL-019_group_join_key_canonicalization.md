# SQL-019 Group-by Join-key Canonicalization

解决 SQL-018 J02：模型把 `dim_product.category_id`（与 `dim_category.category_id` 经
product_to_category 等值 Join）放入 GROUP BY，Plan 要求使用规范 `dim_category.category_id`。
同时修复过滤后的 Table Info 若漏掉已登记 Join 键，Plan.columns 必须补全，否则任何合法
JOIN 侧列都会被误判为方案外。

## In Scope

- SchemaLinkingPlan Builder 把所有已登记 Join 的左/右列加入 plan.columns。
- 在最后一次修复输出重入 Validator 前，将 GROUP BY 中等价 Join 键替换为 Plan 规范列。
- 替换只在 Plan Join 关系明确等值、目标列唯一且属于 Plan 分组/显示列时发生。
- 保持 ORDER BY、SELECT 与过滤不变。
- 单元测试、设计文档、状态与独立 Completion Report。

## Out of Scope

- 不处理 C05 Pivot、N03 缺失 Join/Filter、T05 日历过度 Join 或 TopN 漂移。
- 不放宽 Validator；非等价、多候选或无法解析的 GROUP BY 保持原样交回拒绝。
- 不修改 Prompt、Golden、Metadata、Policy、Evaluator 或历史评测产物。
- 不运行真实模型复测；收益由后续独立 Rerun 验证。

## Allowed Files

- `app/nl2sql/schema_linking.py`
- `app/nl2sql/repair.py`
- `app/agent/nodes/correct_sql.py`
- `test/nl2sql/test_schema_linking_plan.py`
- `test/nl2sql/test_sql_repair.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report

## Acceptance

- Plan Builder 输出 columns 必含每个 registered Join 的左/右物理列。
- SQL GROUP BY `dim_product.category_id` 可被规范成 Plan 的 `dim_category.category_id`。
- 无对应 Join、目标不唯一或 SQL 非 GROUP BY 时不改写。
- 全量 pytest、Ruff、mypy 与 `git diff --check` 通过。
