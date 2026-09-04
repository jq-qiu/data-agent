# F003 Context and Metric Layer

## 1 Feature 状态

- 建议初始状态：`ready`
- 前置依赖：F002 accepted
- 后续消费者：F004 至 F007

## 2 目标

建立版本化的业务语义层和多轮分析上下文，使后续 Agent 只能基于已登记指标、表、字段、值域和 JOIN 关系制定计划。完成后可独立输入用户问题和历史消息，输出可审计的候选问题定义与受控上下文，但不执行真实 SQL 或归因。

## 3 In Scope

- 问题定义、指标、维度、数据源对象、JOIN 关系、检索候选和上下文的数据模型。
- 指标注册表与技术元数据加载、校验、版本发布。
- 指标、表、字段、连接键和字段值的精确、词法与向量检索接口。
- 上下文选择、Token 预算、证据引用和来源标识。
- 会话窗口、上下文摘要生成/读取/失效与多轮约束继承。
- 非密钥配置热更新、任务配置版本固定和集群版本可见性。
- Context 层离线 Golden 数据和分层指标。

## 4 Out of Scope

- SQL 或文件工具执行。
- Agent 自主工具循环和归因算法。
- 最终报告与导出。
- 让 LLM 自动发布新指标口径。模型可以建议别名，但必须人工审核后进入注册表。

## 5 领域合同

### 5.1 ProblemDefinition

```json
{
  "analysis_type":"diagnostic",
  "metric_id":"sales.gmv",
  "current_period":{"start":"2026-08-01","end":"2026-08-31","grain":"day"},
  "baseline_period":{"type":"previous_period","start":"2026-07-01","end":"2026-07-31"},
  "scope_filters":[{"dimension_id":"region.name","operator":"eq","value":"华南"}],
  "drilldown_dimensions":["store.id","product.category","channel.id"],
  "question_text":"为什么本月华南销售额下降？",
  "assumptions":[],
  "ambiguities":[]
}
```

`ambiguities` 非空且影响计算时，调用者必须进入澄清，不得把候选第一名直接当事实。

### 5.2 MetricDefinition

```json
{
  "metric_id":"sales.gmv",
  "display_name":"销售额",
  "aliases":["GMV","成交额","销售金额"],
  "description":"支付成功且未完全取消订单的实付金额",
  "formula":{"type":"sum","field":"fact_order.paid_amount"},
  "grain":["day","store","product","channel"],
  "default_time_field":"fact_order.paid_at",
  "filters":[{"field":"fact_order.order_status","operator":"in","value":["paid","completed"]}],
  "unit":"CNY",
  "owner":"sales_data_team",
  "version":3,
  "effective_from":"2026-01-01",
  "status":"active"
}
```

公式使用受控 AST 或已验证表达式，不将任意 SQL 字符串直接交给模型执行。派生指标必须声明分子、分母、零值策略和精度，例如 AOV 为 `GMV / distinct_order_count`，不能错误关联销量字段。

### 5.3 JoinRelation

```json
{
  "left":"fact_order.region_id",
  "right":"dim_region.region_id",
  "cardinality":"many_to_one",
  "join_type":"left",
  "effective_from":"2026-01-01",
  "version":1
}
```

表关联只能来自显式关系，不根据相似字段名自动创造。多对多关系必须指定桥表和去重/聚合策略。

### 5.4 AnalysisContext

Context 输出至少包含：

```text
problem_definition_candidate
metric_candidates with score and source
allowed_tables and columns
join_graph
grounded_values
recent_messages
context_summary
prior_evidence_refs
unresolved_questions
config_version metric_catalog_version metadata_version
token_budget and truncation_log
```

Client、Repository、模型和数据库连接不属于该可序列化对象，而属于运行时依赖 Context。

## 6 元数据和指标来源

1. **人工业务配置**：表/字段业务说明、别名、角色、指标公式、粒度、过滤条件、负责人和版本。
2. **数据源技术元数据**：真实表列、类型、可选小样例和值域统计。
3. **显式关系配置**：主外键、基数、桥表、默认 JOIN 方向。
4. **字段真实值索引**：地区、会员等级、品类等受控枚举或高频值；敏感和高基数字段不建立明文索引。

构建过程必须校验：字段存在、类型与聚合兼容、指标关系可达、别名冲突、版本生效区间、敏感等级和数据权限。失败时整个候选版本不发布。

## 7 检索流程

```text
规范化问题和历史约束
  → 指标名称或别名精确匹配
  → 词法检索和向量检索并行
  → 候选融合与重排
  → 值到字段 Grounding
  → 根据指标补齐公式字段
  → 根据 Join Graph 补齐连接键
  → 权限过滤
  → Token 预算裁剪
  → 输出候选及来源分数
```

### 7.1 指标检索

- 精确别名命中优先；冲突别名必须结合业务域或触发澄清。
- 默认 Top-K 由配置控制，Top-5 是候选上限而非天然提高精确率的保证。
- 评价重点为 Metric Hit@1 和 Precision；指标库过小时不得用 Top-5 宣称优化有效。
- 向下游同时提供 metric_id、公式、口径、版本和候选理由，不只提供名称文本。

### 7.2 表字段与连接键

- 先召回业务字段，再根据指标公式和过滤条件补齐必需字段。
- 根据 Join Graph 求最短允许路径，补齐主外键；若有多条同等路径则标记歧义。
- 字段层重点优化 Recall 和 Join-key Recall，因为遗漏会使 SQL 无法正确生成。
- 禁止为提高 Recall 而将全库 Schema 无限制放入上下文。

### 7.3 字段值 Grounding

- 对用户实体同时返回 `canonical_value/column_id/match_type/score`。
- “广东”可映射为 `dim_region.province=广东省`，但需要索引或映射证据。
- 一个值落到多个字段且影响语义时进入澄清。
- 受限字段值只返回可用于参数化查询的内部引用，不向模型暴露明文。

## 8 上下文组装与预算

上下文优先级从高到低：

1. 当前问题、用户已确认的澄清和硬权限。
2. 正确指标定义、当前期/基准期、范围和数据质量规则。
3. 必需表列、JOIN 路径和值 Grounding。
4. 上一轮有效结论、证据引用和未决项。
5. 相关附件片段和候选维度。
6. 低分候选和补充样例。

Token 超限时按低优先级裁剪，并记录 `truncation_log`。指标公式、过滤条件、连接键和权限条件不得被裁掉。上下文中的每个片段带来源 ID 和可信类型，附件/数据库文本明确标记为不可信证据而非指令。

## 9 多轮摘要

### 9.1 摘要内容

摘要必须保留：

- 用户已确认的问题、指标、时间、基线和范围。
- 已完成分析的阶段性结论，但必须附证据引用。
- 已否定假设、未解决歧义、待补充数据和后续建议。
- 指标、元数据和配置版本。

不得只生成自由散文。建议内部先生成结构化摘要，再渲染 `summary_text`。

### 9.2 区间与失效

- 摘要仅覆盖完整闭区间 `[start_seq_no,end_seq_no]`，不能包含正在输出的消息。
- 同一会话有效摘要区间不重叠；新摘要可合并旧摘要，但要保存来源区间和 source_hash。
- 被覆盖消息、附件或指标版本发生变化时，摘要标记失效并重建。
- 冲突时以原始消息、工具证据和指标注册表为准。

### 9.3 继承规则

“那华南呢？”继承上一轮指标、时间和基线，只覆盖范围；“改看订单数”覆盖指标但保留明确时间和范围。若历史约束已过期或用户说“重新开始”，不得继续继承。

## 10 配置和口径热更新

- 候选配置加载后执行 Schema、跨字段、别名冲突、指标公式、Join Graph、权限和依赖健康校验。
- 只有完整快照通过后才能原子发布，生成新的 `config_version/catalog_version`。
- 运行中任务固定旧版本；新任务使用新版本。
- 所有实例报告当前版本，分裂超时则从 readiness 摘除。
- 密钥和命令根白名单不可热更新。
- 回滚选择历史有效快照并重复相同验证和审计流程。

实现 `POST /api/admin/reload`，合同以接口文档为准。

## 11 验收场景

### AC1 同义指标命中

Given 至少 10 个包含相近指标的目录，When 输入“华南卖了多少钱”，Then `sales.gmv` 为 Hit@1，返回完整公式、时间字段和版本，而不是只返回字符串。

### AC2 歧义澄清

Given “销量”在业务中可能指件数或订单数，When 无额外上下文，Then ambiguities 标出两个候选并要求澄清，不自动选择。

### AC3 JOIN 补齐

Given 问题涉及订单金额和地区，When 组装上下文，Then包含 fact_order、dim_region 及登记的 region_id 连接键，Join-key Recall 命中。

### AC4 多轮继承

Given 上一轮已确认“本月对上月的 GMV”，When 用户说“那华南呢”，Then继承指标和两个时期，只新增华南范围。

### AC5 摘要失效

Given 摘要 source_hash 对应消息 1 至 20，When管理员修复其中关联的指标口径并发布新版本，Then新任务不会把旧摘要中的数字当成当前事实，必要时重建或标注历史版本。

### AC6 原子热更新

Given version 12 正在运行任务，When合法配置发布 version 13，Then旧任务始终使用 12，新任务使用 13；非法 version 14 不部分生效。

## 12 测试与评测

- Unit：指标公式验证、别名冲突、Join Graph、融合排序、预算裁剪、摘要区间和继承规则。
- Integration：技术元数据同步、索引构建、配置发布/回滚、多实例版本同步。
- Contract：ProblemDefinition、MetricDefinition、AnalysisContext 和 reload API Schema。
- Offline Eval：Metric Hit@1、Table/Column/Join-key Recall、Value Grounding、Context Precision/Recall、Token 数。
- Security：受限元数据过滤、敏感值索引禁止、附件 Prompt 注入边界、管理员接口权限。

## 13 Gate

- 固定测试集 Metric Hit@1 ≥ 90%，Join-key Recall ≥ 95%，Context Recall ≥ 90%；同时报告样本数和分场景结果。
- 所有指标公式均引用真实授权字段，所有 JOIN 均来自显式关系。
- 必须澄清样本 Recall ≥ 95%，无证据猜测次数为 0。
- 摘要区间无重叠、source_hash 可验证、多轮继承测试通过。
- 热更新失败保留旧版本，运行任务版本不漂移，多实例最终一致。
- 未执行任何真实 SQL、命令或完整 Agent 流程，保持 Feature 边界。

## 14 完成报告附加项

报告指标目录数量、同义词冲突数、索引版本、Golden 样本数、各召回指标、平均上下文 Token、热更新测试和仍需业务确认的口径。

