# 数据与指标详细设计

## 1. 设计目标

数据层同时服务两个目标：

1. DWD 多表模型用于展示开放式 NL2SQL；
2. 诊断 DWS 用于稳定、可测试的指标拆解和证据验证。

所有表必须声明粒度。指标定义必须包含公式、过滤条件、时间字段、可用维度和非可加性约束。

## 2. 数据分层

```text
ODS：原样保存 Olist CSV 和导入批次信息
 ↓
DWD：订单、订单项、支付、配送、评价及维度标准化
 ↓
Synthetic：生成 Traffic、Promotion、Inventory 和 Ground Truth Event
 ↓
DWS：按稳定分析粒度汇总可加总基础量
 ↓
Application：NL2SQL 和 Diagnosis Agent
```

ODS、DWD 原始值不能被 Synthetic Generator 覆盖。合成结果使用独立表或明确的 `analysis_*` 字段。

## 3. DWD 建议模型

### 3.1 事实表

| 表 | 粒度 | 核心字段 |
|---|---|---|
| `fact_order` | 一行一个订单 | order_id、customer_id、status、purchase_date |
| `fact_order_item` | 一行一个订单项 | order_id、item_no、product_id、seller_id、price、freight_value |
| `fact_payment` | 一行一种订单支付记录 | order_id、payment_sequential、type、installments、value |
| `fact_delivery` | 一行一个订单配送状态 | order_id、estimated_date、delivered_date、delay_days |
| `fact_review` | 一行一条评价 | review_id、order_id、score、created_at |

### 3.2 维度表

| 表 | 粒度 | 核心字段 |
|---|---|---|
| `dim_date` | 一行一天 | date_id、date、year、quarter、month、week |
| `dim_customer` | 一行一个客户 | customer_id、customer_unique_id、state |
| `dim_product` | 一行一个商品 | product_id、category_id、重量和尺寸 |
| `dim_category` | 一行一个标准品类 | category_id、葡萄牙语名称、英文名称 |
| `dim_seller` | 一行一个卖家 | seller_id、state |
| `dim_region` | 一行一个巴西州 | state_code、display_name |

`fact_payment` 与 `fact_order_item` 都可能对订单形成一对多关系，禁止直接同时 JOIN 后聚合支付金额或商品金额。必须先在订单粒度分别聚合，再 JOIN。

## 4. GMV 唯一口径

V1 冻结：

```text
item_sales_amount = fact_order_item.price

GMV = SUM(item_sales_amount)
```

默认规则：

- 运费 `freight_value` 不计入 GMV；
- 订单状态过滤规则必须由 Metric Registry 固定；
- 所有 DWS、Golden SQL 和 Analyzer 使用同一口径；
- `payment_value` 不作为 V1 GMV，避免多支付记录和业务语义差异。

## 5. 诊断 DWS

### 5.1 `dws_sales_region_daily`

粒度：

```text
日期 × 客户所在州
```

字段：

```text
date_id
region_id
gmv
order_count
visitors
promoted_sku_count
active_sku_count
available_sku_count
required_sku_count
dataset_version
synthetic_version
```

用途：

- 整体/地区 GMV 趋势；
- 整体 Order Count；
- AOV 和 Shapley 拆解；
- Conversion、Promotion、Inventory 证据。

### 5.2 `dws_sales_category_daily`

粒度：

```text
日期 × 客户所在州 × 商品品类
```

字段：

```text
date_id
region_id
category_id
gmv
item_count
category_order_count
category_visitors
promoted_sku_count
active_sku_count
available_sku_count
required_sku_count
dataset_version
synthetic_version
```

用途：

- 品类 GMV 变化贡献；
- 品类内部订单和商品数量变化；
- 品类 Traffic、Promotion、Inventory 证据。

约束：

> Olist 一个订单可能包含多个品类，因此 `category_order_count` 只表示“包含该品类的去重订单数”。禁止跨品类求和并将结果解释为整体订单量。

## 6. 可加性设计

DWS 保存可加总基础量，不保存供跨日期直接相加的比率。

运行时计算：

```text
AOV = SUM(gmv) / NULLIF(SUM(order_count), 0)

Conversion Rate = SUM(order_count) / NULLIF(SUM(visitors), 0)

Promotion Coverage =
SUM(promoted_sku_count) / NULLIF(SUM(active_sku_count), 0)

Inventory Fill Rate =
SUM(available_sku_count) / NULLIF(SUM(required_sku_count), 0)
```

如果 `visitors` 是站点/州级访客，不能复制到每个品类。品类表中的 `category_visitors` 必须表示该品类页面或品类范围内的合成访客量。

## 7. 指标注册表示例

```yaml
metrics:
  gmv:
    display_name: GMV
    formula: SUM(item_sales_amount)
    base_grain: order_item
    time_column: purchase_date
    excluded_statuses: [canceled, unavailable]
    allowed_dimensions: [date, region, category, seller]

  order_count:
    display_name: 订单量
    formula: COUNT(DISTINCT order_id)
    base_grain: order
    time_column: purchase_date

  aov:
    display_name: 客单价
    formula: gmv / order_count
    aggregation: recompute_from_components
```

配置实现时必须使用项目现有配置体系或独立 Registry，不得把公式散落在 Prompt 中。

## 8. Synthetic Evidence 模型

### 8.1 指标链

```text
Visitors
   ↓
Conversion Rate
   ↓
Order Count
   ↓
AOV
   ↓
GMV
```

生成器必须从上游 Evidence 出发，沿指标链生成下游结果，不得分别随机生成相互矛盾的数值。

### 8.2 事件规则

| Event | 直接变化 | 传导路径 |
|---|---|---|
| Traffic Drop | Visitors 下降 | Visitors → Orders → GMV |
| Promotion End | Promotion Coverage 下降 | Promotion → Conversion → Orders → GMV |
| Stockout | Inventory Fill Rate 下降 | Inventory → Conversion → Orders → GMV |

具体强度必须写入版本化配置，不应硬编码在 Analyzer 中。

### 8.3 Ground Truth

```text
fact_business_event
-------------------
event_id
event_type
start_date
end_date
region_id
category_id
effect_strength
direct_metric
expected_metric
expected_direction
ground_truth_rank
random_seed
generator_version
```

至少覆盖：

- 单因素；
- 双因素；
- 无明显异常；
- 缺失 Evidence、必须降级。

## 9. 数据质量与对账

Gate 1 至少验证：

- Raw 文件数与导入批次；
- 各表行数、主键唯一性和外键孤儿；
- 订单、订单项和金额的基准统计；
- DWD GMV 与两张 DWS 的 GMV 对账；
- 一对多 JOIN 膨胀检测；
- 整体订单量不依赖品类订单量求和；
- 分母为 0 时比例返回 NULL；
- `Orders ≈ Visitors × Conversion Rate` 在定义容差内成立；
- `GMV ≈ Orders × AOV` 在金额精度容差内成立；
- 相同 Seed、Generator Version 生成相同 Ground Truth。

