# 诊断分析方法详细设计

## 1. 方法边界

V1 提供三类分析结果：

1. 指标恒等式拆解；
2. 互斥维度的变化贡献；
3. 候选经营因素的关联证据。

这些结果用于回答“变化来自哪里、哪些因素值得优先调查”，不能在没有实验或准实验条件时证明因果关系。

## 2. 分析执行顺序

```text
Step 1 解析目标指标、范围、当前期和基期
Step 2 检查数据质量和分析能力
Step 3 确认异常是否真实存在
Step 4 进行 GMV 两因素拆解
Step 5 按地区和品类计算变化贡献
Step 6 验证 Traffic、Promotion、Inventory
Step 7 校验证据、数字和语言强度
Step 8 输出结论、限制和下一步建议
```

如果 Step 2 或 Step 3 不通过，系统必须降级或停止后续诊断。

## 3. 期间对比

输入：

```text
metric
current_period
baseline_period
scope
```

输出：

```text
current_value
baseline_value
absolute_delta
change_rate
```

定义：

```text
absolute_delta = current_value - baseline_value

change_rate = absolute_delta / ABS(baseline_value)
```

基期为 0 或 NULL 时，`change_rate` 返回 NULL，并在 Evidence 中说明不可计算。

## 4. GMV 两因素 Shapley 拆解

定义：

```text
Q0 = 基期 Order Count
Q1 = 本期 Order Count
P0 = 基期 AOV
P1 = 本期 AOV
```

订单量贡献：

```text
delta_gmv_order = (Q1 - Q0) × (P1 + P0) / 2
```

AOV 贡献：

```text
delta_gmv_aov = (P1 - P0) × (Q1 + Q0) / 2
```

必须满足：

```text
delta_gmv_order + delta_gmv_aov
= Q1 × P1 - Q0 × P0
= current_gmv - baseline_gmv
```

金额使用 Decimal，禁止使用二进制浮点直接处理最终财务数值。对账容差由配置明确，例如 0.01。

## 5. 维度贡献

对同一个互斥且完备的维度：

```text
delta_i = current_i - baseline_i

contribution_i = delta_i / total_delta
```

约束：

- `total_delta` 的定义必须与各分组使用相同指标、过滤条件和粒度；
- 分组必须互斥且覆盖总量，否则只报告 `delta_i`，不宣称完整贡献率；
- Contribution 可以大于 100%，表示其他分组存在反向抵消；
- Contribution 可以小于 0%，表示该分组抵消了总体下降；
- 地区贡献和品类贡献属于两套分解，不能相加；
- 当 `ABS(total_delta) <= epsilon` 时不计算比例，只报告绝对变化。

品类维度中的 `category_order_count` 非跨品类可加指标，不能用于与整体 Order Count 对账。品类贡献首版以 GMV 为主。

## 6. 候选因素验证

### 6.1 Traffic

查询同一时间、地区和必要品类切片下：

```text
Visitors
Conversion Rate
Order Count
```

只有在时间方向、切片范围和指标链均一致时，才能形成 Traffic 候选 Evidence。

### 6.2 Promotion

查询：

```text
Promotion Coverage
Conversion Rate
Order Count
```

促销覆盖率下降只能作为关联证据。没有对照组时不能计算“促销造成的净增量”。

### 6.3 Inventory

查询：

```text
Inventory Fill Rate
Conversion Rate
Order Count
```

库存满足率下降与订单下降同向时可以列为候选因素，但仍需排除流量、促销和数据缺失等替代解释。

## 7. Evidence 等级

```text
high:
  数字来源明确，切片和时间一致，指标链支持，且没有直接冲突证据。

medium:
  存在同向关联，但样本、时间或替代解释有限制。

low:
  只有弱相关或证据不完整，只能列入待调查项。

unsupported:
  无可定位数据、口径不一致或存在直接冲突，禁止进入报告结论。
```

Evidence 示例：

```json
{
  "evidence_id": "E007",
  "claim": "流量下降是当前优先候选因素",
  "type": "candidate_factor",
  "factor": "traffic",
  "query_ids": ["Q006", "Q007"],
  "current_value": 8200,
  "baseline_value": 10000,
  "change_rate": -0.18,
  "support_level": "high",
  "limitations": ["Synthetic traffic data", "No experimental control"]
}
```

## 8. 降级规则

- 指标不存在：返回 unsupported metric；
- 时间或基期不完整：请求用户补充或返回不可比较；
- 当前期没有异常：报告“未确认显著下降”，不继续寻找原因；
- 缺少 Traffic：跳过流量验证并列出缺失数据；
- 缺少 Promotion：跳过促销验证；
- 缺少 Inventory：跳过库存验证；
- 缺少处理组、对照组或因果设计：禁止 causal inference；
- Evidence 冲突：展示冲突，不选择性隐藏。

正确降级属于成功结果，不属于系统失败。

## 9. Report 结构

```text
1. 问题定义
2. 异常确认
3. 指标拆解
4. 维度贡献
5. 候选因素证据
6. 数据限制和建议
```

报告中的每一个关键数字必须带 `query_id` 或 `analysis_result_id`，关键结论必须引用一个或多个 Validated Evidence。

## 10. 分析语义契约

### 10.1 四类静态定义

分析语义 Registry 只描述业务分析知识，并通过规范 ID 引用物理 Metadata：

```text
MetricAnalysisDefinition
  指标显示名、分析恒等式、允许拆解、可下钻维度、可验证因素

DimensionDefinition
  维度业务角色、值域来源、是否互斥完备、允许的方法

CandidateFactorDefinition
  候选因素、主要指标、辅助指标、最低 Evidence 条件、限制

AnalysisToolDefinition
  方法、参数协议、前置能力、输出类型、依赖和停止规则
```

`MetricAnalysisDefinition` 中的 `GMV = Order Count × AOV` 是分析恒等式；`GMV = SUM(item_sales_amount)` 和 `AOV = GMV / COUNT(DISTINCT order_id)` 仍是 Metric Registry 中唯一的物理计算口径，不能在分析语义中另写一套公式。

`DimensionDefinition` 必须区分同名业务概念的角色。V1 地区贡献和 Scope 使用客户所在州；卖家所在州即使存在物理字段，也不能自动作为同一维度开放。

候选因素最低 Evidence 契约为：

| 候选因素 | 主要指标 | 辅助链路 | 最低结论强度 |
|---|---|---|---|
| Traffic | Visitors | Conversion Rate、Order Count | 关联候选 |
| Promotion | Promotion Coverage | Conversion Rate、Order Count | 关联候选 |
| Inventory | Inventory Fill Rate | Conversion Rate、Order Count | 关联候选 |

### 10.2 静态语义与 RuntimeCapability

静态 Registry 回答“系统理论上允许怎样分析”；`RuntimeCapability`（当前运行时能力）回答“这个问题在当前数据切片上实际能做什么”。后者至少校验期间覆盖、非空 Evidence、可用维度、数据质量、支持方法和因果条件。Planner 只能使用二者的交集。

真实 Olist 数据中三类候选因素字段为空时，`RuntimeCapability` 应关闭相应验证并报告缺失；Synthetic 数据存在固定 Seed 和版本化 Evidence 时，可以开放完整候选因素验证。Synthetic Ground Truth 仅用于生成与评测，不能进入 Planner 或 Report 上下文。

### 10.3 声明类型

Evidence 和报告至少区分：

- `FACT`：直接由已验证数据支持的事实；
- `ASSOCIATION`：时间、范围和指标链一致的候选关联；
- `CAUSAL`：需要实验或准实验设计支持的因果声明。

当前 V1 只允许 `FACT` 和 `ASSOCIATION`。没有实验或准实验设计时，`CAUSAL` 必须被 Capability、Plan Validator 和 Evidence Checker 拒绝。

### 10.4 类型化分析工具

现有 `AnalysisTask` 已是类型化工具调用：`method` 选择 Registry 中的分析能力，其余字段是白名单参数。Planner 只负责组合 `AnalysisTask`，Query Builder 负责物理字段映射，Analyzer 负责计算。后续不再增加一套语义重复的通用 `ToolCall`。

`SEM-002` 已实现 Analysis Semantic Registry 及其 Catalog 引用校验，并复用现有 `CapabilityAssessment` 构建请求级逻辑投影。真实/Synthetic 的字段可用性仍由现有 Capability 链决定；本 Feature 没有修改该判断、Analyzer 或 Evidence。LLM Planner 仍未实现。
