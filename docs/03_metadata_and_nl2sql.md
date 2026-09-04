# Metadata 与 NL2SQL 详细设计

## 1. 目标

让开放式业务问题在受控元数据上下文中生成只读 SQL，同时为诊断 Agent 提供相同的表、字段、指标和字段值语义。

## 2. 当前可复用链路

当前 LangGraph 已包含：

```text
extract_keywords
→ expand_recall_keywords
→ recall_column / recall_metric / recall_value
→ merge_retrieved_info
→ filter_table / filter_metric
→ add_extra_context
→ generate_sql
→ validate_sql
→ correct_sql（失败路径）
→ execute_sql
```

后续应适配新数据，而不是重写整条链路。

## 3. Metadata 对象

### 3.1 Table Metadata

```text
table_name
role
grain
description
time_column
primary_key
allowed_join_relations
```

### 3.2 Column Metadata

```text
table_name
column_name
data_type
role
description
aliases
examples
is_sensitive
value_index_enabled
```

### 3.3 Metric Metadata

```text
metric_id
display_name
description
formula
base_grain
time_column
status_filters
allowed_dimensions
component_metrics
aliases
version
```

### 3.4 Relationship Metadata

```text
left_table
left_column
right_table
right_column
cardinality
allowed
grain_warning
```

JOIN 关系必须来自 Relationship Registry，不能让 LLM 根据字段名自行猜测。

## 4. 检索职责

### 4.1 Qdrant

用于语义召回：

- 表；
- 字段；
- 指标；
- 字段和指标别名。

指标召回默认候选数可从 Top5 起步，但最终 TopK 必须通过固定评测集调整，不能把 Top5 本身当成质量结论。

### 4.2 Elasticsearch

用于真实字段值匹配，例如：

- 州代码和州名称；
- 商品品类；
- 支付类型；
- 订单状态。

字段值别名必须最终映射到真实列和值，不得只向 Prompt 添加自由文本。

### 4.3 MySQL Metadata

保存规范化的表、字段、指标和关系事实，作为过滤、上下文拼装和离线检查的数据来源。

## 5. Schema Linking 输出

推荐使用结构化结果：

```json
{
  "metric_ids": ["gmv"],
  "tables": ["fact_order_item", "fact_order", "dim_date"],
  "columns": [
    "fact_order_item.price",
    "fact_order_item.order_id",
    "fact_order.purchase_date"
  ],
  "filters": [
    {"column": "dim_date.month", "value": "2018-05"}
  ],
  "join_relations": ["order_item_to_order"],
  "grain_warnings": []
}
```

在生成 SQL 前必须检查：

- 指标是否存在；
- 指标公式所需字段是否齐全；
- JOIN 是否在白名单；
- 一对多 JOIN 是否会放大指标；
- 字段值是否属于目标列；
- 时间字段和粒度是否正确。

## 6. 两类 SQL 路径

### 6.1 开放式问数

```text
Question
→ Metadata Retrieval
→ Schema Linking
→ LLM SQL Generation
→ Static and Safety Validation
→ Execution
→ Limited Repair
→ Result Formatting
```

适用于查询空间较大的自然语言问数。

### 6.2 标准诊断任务

```text
AnalysisTask
→ Metric/Method Registry
→ Controlled Query Builder
→ Same SQL Validator
→ Same SQL Executor
→ Structured Query Result
```

期间对比、Shapley 输入、维度贡献和三类候选因素验证均使用受控查询，不让 LLM 自由设计数学逻辑。

## 7. SQL 安全与正确性

最低要求：

- 只允许单条 `SELECT` 或受控 CTE 查询；
- 禁止 DDL、DML、事务和多语句；
- 禁止 `INTO OUTFILE`、系统表和注释绕过；
- 使用只读数据库账号；
- 表和列必须属于白名单；
- 设置超时、最大返回行数和允许扫描范围；
- 修复次数设置上限；
- 执行错误不能直接拼入最终业务结论。

## 8. Metadata Golden Dataset

首版准备 10～15 条样本，每条包含：

```json
{
  "case_id": "meta_001",
  "question": "2018年5月圣保罗州GMV是多少",
  "expected_metric_ids": ["gmv"],
  "expected_tables": ["fact_order", "fact_order_item", "dim_region"],
  "expected_columns": ["price", "purchase_date", "customer_state"],
  "expected_join_relations": ["order_item_to_order", "order_to_region"],
  "expected_values": ["SP"]
}
```

至少报告：

- Metric Hit@1；
- Table Recall@K；
- Column Recall@K；
- Join-key Recall；
- Value Grounding Accuracy；
- Context Precision/Recall；
- Context Token Count。

RAGAS 可辅助评估 Context Precision、Context Recall、Faithfulness 和 Answer Relevancy，但不能替代字段、JOIN、指标公式和 SQL 执行结果的确定性检查。

