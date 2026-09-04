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

