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

`SchemaLinkingPlan` 同时冻结 `required_metric_columns`、`calendar_table`、规范分组列、
显示列、排序和固定过滤。开放式问数的 Validator 必须再次核对 SQL 没有使用方案外
表、列或 JOIN，并要求 GROUP BY、ORDER BY 和固定过滤与方案一致；生成节点和执行节点
都使用同一 Plan 复验，不能在修复后绕过。

`dim_date.month` 使用 `YYYY-MM` 字符串，`date` 比较值使用 `YYYY-MM-DD`，`year`、
`quarter` 和 `date_id` 使用整数。Validator 在执行前拒绝类型错配。物理明细行数不绑定
业务 `item_count`；包含订单状态筛选/拆分时，不使用缺少状态粒度的 DWS `order_count`。

一次受限 LLM 修复后仍必须回到同一 Validator。SQL-011 在该回路中只增加 Plan-aware 的
确定性类型规范化：仅当 Calendar Table 为 `dim_date` 时，将修复结果中的四位 `year`、
1-4 `quarter` 和八位 `date_id` 数字字符串转换为整数 Literal；`month`、`date` 和其他表
值保持不变。该步骤不放宽 Validator、不新增字段/JOIN，也不增加修复轮数。

SQL-012 还只识别一种冗余派生表：外层单一聚合读取内层单表裸列投影，内层没有 JOIN、
聚合、分组、排序、Limit、Distinct 或窗口，且最终物理列完全属于 Plan。此时将内层过滤
原样提升、把外层引用还原为物理列并丢弃未使用投影；任何复杂形状都保持原 SQL 交回
Validator 拒绝，不能借“修复”改变聚合层级。

SQL-013 不根据 Plan 自动创造 SQL，而是把当前 Validator Error 与允许表、必需指标列、
Calendar Table、Join 等式、精确 GROUP BY/ORDER BY 和固定过滤格式化为独立短约束，再
注入同一次 LLM 修复。GROUP BY 偏差会额外要求每组一行并禁止条件聚合透视；修复结果
仍经过 SQL-011/012 的窄规范化和原 Validator。SQL-015 再接受无表名前缀的派生列引用，
并把 Plan 内物理 `date_id` 的 ISO 日期字符串归一为仓库整数格式，仍不改变聚合层级。

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

## 9. 分析语义层与语义绑定

### 9.1 同一事实源的三种投影

Metadata Catalog 继续作为表、字段、JOIN、粒度、指标物理公式和规范字段值的事实源。归因分析在其上增加业务分析语义，但不能复制或改写物理定义：

| 消费者 | 获得的投影 | 不应获得的内容 |
|---|---|---|
| NL2SQL | 表、字段、JOIN、粒度、指标公式和值候选 | 密钥、连接串、无关全库 Schema |
| Planner | 指标分析关系、可下钻维度、候选因素、分析工具和运行时限制 | 物理表列、JOIN、SQL、数据库连接和原始行 |
| Report | 显示名、口径版本、声明类型、Evidence 引用和限制 | 未校验查询结果和 Ground Truth 标签 |

因此，Planner 不通过读取全部数据库 Schema 自由设计分析。物理公式仍由 Metric Registry 提供，分析语义只用规范 ID 关联这些定义。

### 9.2 Semantic Grounding（语义绑定）

进入 Planner 之前，系统必须把自然语言绑定为规范业务对象：

```text
用户问题
  ↓
Metric Resolver（指标绑定）
Dimension Resolver（维度绑定）
Dimension Value Resolver（维度值绑定）
Time Resolver（时间与基期绑定）
Scope Validator（分析范围校验）
  ↓
ParsedAnalysisQuestion（规范化分析问题）
```

绑定优先级为“精确规范值 → 受控别名 → 受控检索候选 → 结构化歧义或不支持”。检索只能召回 Registry 已存在的对象，不能创造指标、维度、字段值或时间范围。当前诊断 Parser 已实现确定性规范值和别名绑定；`SEM-002` 实现受控检索兜底，`CLARIFY-001` 已把三种绑定结果接入生产单轮 API 与前端。真实 Qdrant/Elasticsearch 召回准确率仍未评测，不能用 Stub 契约结果替代。

维度值绑定需要保留业务角色。例如问题中的 `PR` 在当前 Olist 诊断口径中绑定为客户所在州，不得因为物理库同时存在卖家州就自动改写 Scope。高基数字段只能按当前问题检索少量候选，不能把完整值域塞入模型上下文。

### 9.3 PlannerSemanticContext（规划器语义上下文）

`PlannerSemanticContext` 是针对单次请求生成的、紧凑、不可变、可序列化的业务分析说明书，包含：

- 已绑定的指标、时间、基期和 Scope；
- 指标允许的分析恒等式和拆解关系；
- 当前可用维度、候选因素和分析工具；
- 缺失 Evidence、数据质量和非因果限制；
- 最大任务数、任务依赖和停止规则。

它不包含物理表名、列名、JOIN、SQL、数据库连接、原始查询行、完整高基数字段值列表或 Synthetic Ground Truth 原因标签。后续物理字段映射只能在已校验计划之后由受控 Query Builder 完成。

`SEM-002` 已实现可独立调用的绑定与投影组件：确定性 Parser 优先；绑定不足时，Qdrant 只召回 Catalog 中存在的指标及可映射为 `region | category` 的字段候选，Elasticsearch 只召回允许值列中的规范地区/品类值。唯一、超过阈值且分差足够的候选才可自动绑定，否则输出 `CLARIFICATION_REQUIRED` 或 `UNSUPPORTED`。检索结果不会把物理字段 ID 带入 `PlannerSemanticContext`。

当前生产单轮 API 已使用 `SemanticGrounder` 完成确定性优先、受控检索兜底和澄清分流；`PlannerSemanticContextBuilder` 仍是可独立调用的规划上下文组件，尚未进入生产诊断规划路径。`PLAN-LLM-001` 已实现 `BoundedPlannerPolicy` 与 `AnalysisPlanValidator`，但真实模型规划尚未评测，也未接入生产 Graph/API；现有对外诊断运行时继续使用确定性 Planner。
