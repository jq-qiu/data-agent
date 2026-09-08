# SQL-004 Deterministic SchemaLinkingPlan

## 1. Feature

在开放式 NL2SQL 的 SQL 生成之前，用确定性的 `SchemaLinkingPlan` 冻结本次查询的
指标、表、列、JOIN 路径、规范分组维度和 Registry 过滤，让 `generate_sql` 只负责
把方案翻译为 SQL，避免模型在最后一步猜测 JOIN 与业务维度。

## 2. Source of Truth

1. 用户授权与当前冻结范围。
2. 本 Specification。
3. `docs/03_metadata_and_nl2sql.md`、`docs/02_data_and_metric_design.md`。
4. `AGENTS.md`、`README.md`、`IMPLEMENTATION_STATUS.md`。
5. `specs/SQL-002_nl2sql_evaluation.md`、`specs/SQL-003_grouped_topn_query_support.md`
   及对应 Completion Report。
6. 当前 SQL Graph、Metadata Catalog、Relationship Registry、Prompt 与 SQL Validator。

## 3. In Scope

- 新增 `SchemaLinkingPlan` 数据模型与 Validator。
- 新增确定性 Builder：指标、表、列、JOIN、group_by、display、filters、order。
- 客户地区查询通过 Registry 自动补 `dim_region`/`customer_to_region` 路径。
- DWS 已含 `category_id`/`region_id` 时优先直接分组，不额外 JOIN 维度表。
- 在 Graph 中加入 `build_schema_linking_plan` 节点并接入 `generate_sql`/`correct_sql`。
- 更新单元测试、README、状态与 Completion Report。

## 4. Out of Scope

- 不改 SQL-002/003 历史评测与数据。
- 不新增真实外部模型评测。
- 不修改诊断链路、数据、配置、索引、Qdrant/ES 内容或 SQL Validator 规则。
- 不把未实现能力描述为已提升的真实 Execution Accuracy。

## 5. Allowed Files

- `app/nl2sql/schema_linking.py`
- `app/agent/nodes/build_schema_linking_plan.py`
- `app/agent/graph.py`
- `app/agent/state.py`
- `app/agent/nodes/generate_sql.py`
- `app/agent/nodes/correct_sql.py`
- `prompts/generate_sql.prompt`
- `prompts/correct_sql.prompt`
- `test/nl2sql/test_schema_linking_plan.py`
- `test/nl2sql/test_runtime_adaptation.py`
- 本 Spec、`README.md`、`IMPLEMENTATION_STATUS.md`、Completion Report。

## 6. Acceptance

- 单测覆盖地区路径补全、DWS 品类分组优先、未知列校验和断连失败关闭。
- 全量 pytest、Ruff、mypy 不新增问题。
- 不修改历史 SQL-002 评测数字。
- SQL-004 不声称已重跑真实模型基线；真实复测属于后续 Feature。
