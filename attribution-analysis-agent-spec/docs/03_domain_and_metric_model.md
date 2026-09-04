# 03. 领域模型与指标模型

## 1. 目的与边界

本文定义经营归因分析系统必须共享的业务语言、指标语义和数据约束。目标不是替代企业现有数仓，而是在 ODS/DWD/DWS/ADS 之上增加一层可机器读取的指标与分析语义，使 Agent、SQL 工具、报告和 BI 看板使用同一套口径。

系统默认进行的是**诊断性贡献分析**：回答“哪个指标分量或业务切片贡献了总体变化”。除非存在满足要求的实验或准实验设计，否则不得把贡献或相关关系表述为因果关系。

## 2. 限界上下文

| 上下文 | 职责 | 关键对象 |
|---|---|---|
| 指标语义 | 定义指标口径、粒度、公式和血缘 | `MetricDefinition`、`MetricTree` |
| 分析任务 | 定义问题、时间、基线、范围与状态 | `ProblemDefinition`、`AnalysisTask` |
| 数据访问 | 将语义查询编译为只读 SQL 并返回可追溯结果 | `QuerySpec`、`DatasetSnapshot` |
| 归因计算 | 进行变化分解、维度下钻和假设检验 | `AttributionRun`、`Contribution` |
| 证据治理 | 保存证据来源、质量评分和结论引用 | `Evidence`、`Claim` |
| 报告交付 | 输出结构化结果和可读报告 | `AnalysisResult`、`ExportArtifact` |

依赖方向应为：分析任务引用指标语义；归因计算只消费已校验的数据快照；报告只引用已登记证据。LLM 不能直接修改指标定义，也不能把未执行的 SQL 当作证据。

## 3. 核心术语

- **指标（Metric）**：有确定公式、统计粒度、过滤规则、单位、时间字段和负责人，可重复计算的业务量。
- **维度（Dimension）**：用于切分指标的属性，如区域、门店、品类、渠道、会员等级。
- **维度成员（Dimension Member）**：维度中的具体取值，如“华南”“广州天河店”。
- **粒度（Grain）**：一行数据所代表的最细业务实体组合，如“门店 × 商品 × 自然日”。
- **分析范围（Scope）**：过滤条件、权限条件、组织范围和维度范围的组合。
- **当前期（Current Period）**：需要解释的目标时间窗口。
- **基线期（Baseline Period）**：用于比较的时间窗口或目标值。
- **指标树（Metric Tree）**：父指标与可解释子指标之间的有向无环关系，以及它们的运算关系。
- **观察（Observation）**：由确定性查询或计算产生、尚未解释原因的事实。
- **假设（Hypothesis）**：等待证据支持或反驳的可检验陈述。
- **证据（Evidence）**：具有数据来源、时间范围、查询引用和质量信息的事实材料。
- **贡献（Contribution）**：某一分量对父指标变化量的可核算解释，不自动代表因果效应。
- **结论（Claim）**：引用证据并标注强度等级的结构化陈述。

## 4. 领域对象关系

```text
Conversation 1 ── * AnalysisTask 1 ── 0..1 AnalysisResult
                         │
                         ├── 1 ProblemDefinition
                         ├── 1 MetricDefinition ── 0..1 MetricTree
                         ├── * DatasetSnapshot
                         ├── * Hypothesis ── * Evidence
                         └── * AttributionRun ── * Contribution
```

`AnalysisTask` 是审计和恢复的边界。一轮用户消息对应一个任务；任务可以暂停等待澄清，但不得在同一会话中与另一运行任务并发修改上下文。

## 5. 指标定义模型

每个可用于分析的指标至少包含以下字段：

| 字段 | 必填 | 含义 |
|---|---:|---|
| `metric_id` | 是 | 全局稳定标识，不随中文名称变化 |
| `metric_name` | 是 | 展示名称，如“成交金额” |
| `aliases` | 是 | 用户可能使用的别名 |
| `description` | 是 | 业务含义及不包含的范围 |
| `expression` | 是 | 受控表达式或已审核 SQL 模板 |
| `aggregation_type` | 是 | `sum`、`count_distinct`、`average`、`ratio` 等 |
| `grain` | 是 | 指标可安全聚合的最细粒度 |
| `unit` | 是 | 元、单、件、人、百分比等 |
| `time_column` | 是 | 业务时间字段，而非默认使用入库时间 |
| `default_filters` | 是 | 支付状态、退款处理等固化口径 |
| `allowed_dimensions` | 是 | 可安全下钻的维度 |
| `owner` | 是 | 口径负责人或团队 |
| `version` | 是 | 指标版本 |
| `effective_from/to` | 是 | 口径生效区间 |
| `source_lineage` | 是 | DWS/DWD 表与字段血缘 |

示例：

```json
{
  "metric_id": "sales.gmv.paid",
  "metric_name": "支付成交金额",
  "aliases": ["GMV", "成交额", "销售额"],
  "description": "已支付且未全额退款订单的商品成交金额",
  "expression": "SUM(paid_amount - refunded_amount)",
  "aggregation_type": "sum",
  "grain": ["store_id", "product_id", "date_id"],
  "unit": "CNY",
  "time_column": "paid_at",
  "default_filters": ["pay_status = 'PAID'"],
  "allowed_dimensions": ["region", "store", "category", "product", "channel"],
  "owner": "data-governance",
  "version": "2.1.0",
  "effective_from": "2026-01-01",
  "effective_to": null,
  "source_lineage": ["dws_store_product_day.paid_gmv"]
}
```

### 5.1 指标不变量

1. 同一 `metric_id + version` 的公式、默认过滤和单位不可变；变更必须创建新版本。
2. 查询结果必须记录实际使用的 `metric_version`。
3. 不同币种、时区或含税口径不得直接相加。
4. 下钻维度必须属于 `allowed_dimensions`，且查询粒度不得细于授权范围。
5. 比率指标必须保留分子、分母，不能对行级比率直接求平均。
6. JOIN 前必须声明两侧粒度；一对多关系需要预聚合或去重，避免金额膨胀。
7. 结果中的当前值、基线值和贡献值必须使用相同指标版本，除非结果明确标注口径变更。

## 6. 指标树

### 6.1 节点与关系

指标树必须是有向无环图。一个父节点可按以下关系拆解：

| `relation_type` | 形式 | 典型例子 | 推荐算法 |
|---|---|---|---|
| `additive` | `Y = ΣXi` | 总销售额 = 各门店销售额之和 | 加法变化贡献 |
| `product` | `Y = ΠXi` | GMV = 订单数 × 客单价 | Shapley 乘法分解 |
| `ratio` | `Y = A / B` | 转化率 = 订单用户数 / 访问用户数 | 分子分母联合分析 |
| `funnel` | 阶段递进 | 曝光 → 点击 → 加购 → 支付 | 流量与阶段转化分解 |
| `lookup` | 业务映射 | 毛利率等级、目标达成档位 | 规则解释，不做数值分摊 |

每条边至少包含：`parent_metric_id`、`child_metric_id`、`relation_type`、`order`、`valid_from`、`valid_to`。乘法或比率关系还应保存表达式，避免由 LLM 猜测公式。

### 6.2 示例指标树

```text
支付成交金额 GMV
├── product: 支付订单数
└── product: 客单价 AOV

支付订单数
├── product: 访问用户数
└── product: 访问到支付转化率

支付成交金额（另一条可选分析路径）
└── additive: 区域/门店/品类/渠道切片
```

同一指标可以有多条分析路径，但一轮归因必须记录选中的路径，且不能把不同维度的贡献相加。例如“门店贡献”和“品类贡献”分别都可解释总体变化，但同一订单同时属于一个门店和一个品类，两组贡献不能再次求和。

## 7. 问题定义

自然语言问题必须先归一化为 `ProblemDefinition`：

```json
{
  "question_text": "为什么本月华南销售额下降？",
  "analysis_type": "diagnostic",
  "metric_id": "sales.gmv.paid",
  "current_period": {
    "start": "2026-08-01",
    "end": "2026-09-01",
    "timezone": "Asia/Shanghai",
    "granularity": "day"
  },
  "baseline": {
    "type": "previous_period",
    "start": "2026-07-01",
    "end": "2026-08-01",
    "alignment": "calendar_aligned"
  },
  "filters": [
    {"dimension_id": "region", "operator": "eq", "values": ["华南"]}
  ],
  "candidate_dimensions": ["store", "category", "channel"]
}
```

以下任一信息缺失或有多义时必须澄清：指标无法唯一匹配、时间范围无法解析、比较基准影响结论、筛选值映射到多个字段、用户无权访问目标范围。可由组织配置提供默认值，但输出必须明确披露默认选择。

## 8. 基线模型

支持的基线类型：

| 类型 | 适用场景 | 对齐要求 |
|---|---|---|
| `previous_period` | 日常环比 | 等长窗口、相同业务时区 |
| `same_period_last_year` | 强季节性业务 | 同节假日或同星期结构 |
| `rolling_average` | 异常监控 | 排除未完成周期，可配置窗口 |
| `budget` | 经营目标分析 | 目标口径和实际口径一致 |
| `peer_group` | 门店横向比较 | 同类型、同生命周期门店 |
| `custom` | 用户指定 | 明确起止时间和选择理由 |

基线确定规则：用户明确指定优先；否则使用指标配置的默认基线；仍无法确定时进入澄清。系统不得静默选择最有利于某一结论的基线。

## 9. 数据快照与血缘

一次工具查询产生一个不可变 `DatasetSnapshot`，至少记录：

- `snapshot_id`、`task_id`、`query_id`；
- 数据源、表/指标版本、参数化查询模板或查询哈希；
- 当前期与基线期、过滤条件、实际粒度；
- 行数、抽取时间、数据水位和完整性状态；
- 结果内容的对象存储引用与内容哈希；
- 执行用户、权限策略版本、脱敏策略版本。

分析结果只保存必要的聚合值和快照引用。不得在 Agent State 中保存数据库连接、访问令牌或大体量原始数据。

## 10. 证据、假设与结论

`Hypothesis` 的生命周期：

```text
proposed → testing → supported | partially_supported | refuted | unresolved
```

每个结论必须：

1. 引用至少一个 `evidence_id`；
2. 标注结论等级；
3. 给出贡献值或可核查观察值；
4. 披露反向证据、缺失数据和方法限制；
5. 由规则计算置信分，而非让 LLM 自报概率。

结论等级统一为：

- `descriptive`：仅描述观察到的变化；
- `associational`：两个变化在时间或切片上相关；
- `contributory`：依据恒等式或可核算分解得到变化贡献；
- `causal`：存在合格的实验/准实验设计并通过假设检查。

详细计算和证据门槛见 [05_attribution_methodology.md](./05_attribution_methodology.md)。

## 11. DWD、DWS、ADS 的职责映射

| 数仓层 | 在本系统中的职责 | 禁止事项 |
|---|---|---|
| DWD | 提供去重、标准化、粒度明确的业务明细 | 不直接让 LLM 任意拼接大量明细表 |
| DWS | 提供可复用的公共指标及维度聚合 | 不同口径不得使用同一指标 ID |
| ADS | 提供经营日报、预警、归因榜单等场景结果 | 不把 ADS 临时字段反向当作公共指标定义 |

Agent 优先查询 DWS 或指标服务；只有在缺少聚合指标且权限允许时，才由受控查询工具访问 DWD。归因结果可写入 ADS，但不得回写事实源。

## 12. 设计检查清单

- [ ] 指标是否有唯一 ID、版本、公式、粒度、单位、时间字段和负责人？
- [ ] 当前期与基线期是否按相同时区、相同完整度对齐？
- [ ] 指标树是否无环，拆解关系是否可计算？
- [ ] 比率是否保留分子分母，JOIN 是否可能重复计数？
- [ ] 各维度贡献是否分别展示，避免跨维度重复相加？
- [ ] 每个结论是否有证据引用、等级、限制和可复算血缘？
- [ ] “贡献/相关”是否被误写为“导致”？
