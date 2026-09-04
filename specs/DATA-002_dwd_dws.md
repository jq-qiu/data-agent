# DATA-002 DWD and Diagnosis DWS

## Goal

基于已验证的 Olist ODS 表建立可重复、可对账的 DWD 多表模型和两张诊断 DWS。所有指标只使用确定性 SQL/代码计算；本 Feature 不生成 Synthetic Evidence，也不修改 NL2SQL、LangGraph 或诊断业务逻辑。

## Direct Sources of Truth

- `AGENTS.md`；
- `IMPLEMENTATION_PLAN.md` 中 DATA-002 与 Gate 1 定义；
- `docs/02_data_and_metric_design.md` 中 DWD、GMV、DWS 粒度、可加性和对账约束；
- `data/manifests/olist_v2.json` 中已验证的源版本与 ODS 文件结构。

## Prerequisites

- DATA-001 完成并已推送；
- 目标为独立的 `data_agent_v1_dw`，不得覆盖原始 `dw` 数据库；
- ODS 成功批次唯一，9 张源表与清单逐表一致；
- 用户已授权在该隔离库内执行本 Feature 的固定 DDL 与 ETL。

## In Scope

### DWD dimensions

- `dim_date`：一行一天，覆盖 Olist 订单购买日期的最小值到最大值；
- `dim_customer`：一行一个 `customer_id`；
- `dim_product`：一行一个 `product_id`；
- `dim_category`：一行一个 Olist 葡萄牙语品类名；`category_id` 等于该源名称；缺失品类使用固定值 `__unknown__`；
- `dim_seller`：一行一个 `seller_id`；
- `dim_region`：一行一个巴西州代码；`display_name` 暂保持源州代码，避免引入未冻结的地域翻译。

### DWD facts

- `fact_order`：一行一个订单；
- `fact_order_item`：一行一个 `(order_id, item_no)`；
- `fact_payment`：一行一个 `(order_id, payment_sequential)`；
- `fact_delivery`：一行一个订单的预计/实际配送信息；
- `fact_review`：一行一个 `(review_id, order_id)`，因为 Olist 的 `review_id` 单列不是唯一键。

### Diagnosis DWS

- `dws_sales_region_daily`：严格粒度 `date_id × region_id`；
- `dws_sales_category_daily`：严格粒度 `date_id × region_id × category_id`；
- `GMV = SUM(fact_order_item.price)`，不含运费；
- 指标订单状态排除 `canceled` 与 `unavailable`；
- 地区 DWS 的 `order_count` 从订单粒度去重统计，不从品类订单量求和；
- 品类 DWS 的 `category_order_count` 只表示包含该品类的去重订单数；
- `visitors`、`category_visitors`、Promotion 与 Inventory 分子分母、`synthetic_version` 在 DATA-002 保持 `NULL`，由 DATA-003 独立生成；
- DWS 不持久化 AOV、Conversion Rate、Promotion Coverage 或 Inventory Fill Rate，比率只能在运行时由可加总分子分母重算；
- `dataset_version` 使用 Olist 清单中的值 `2`。

## Out of Scope

- 修改 ODS 原始表和值；
- Traffic Drop、Promotion End、Stockout 或 Ground Truth；
- Synthetic 字段填充或事件注入；
- Metadata、Metric Registry、索引构建；
- NL2SQL、SQL Validator、LangGraph、诊断分析、报告生成或 API；
- 将支付金额作为 GMV；
- 跨品类汇总 `category_order_count` 并解释为整体订单量；
- 修改原始 `dw` 数据库。

## Build and Safety Rules

- 所有表名、列名、状态过滤和转换规则在代码中固定，不接受用户或 LLM 提供的 SQL；
- 只允许在当前配置选定的隔离 DW 内创建和重建本 Spec 声明的表；
- 主键由数据库物理约束；DWD 逻辑外键由固定关系清单和每次构建的零孤儿对账强制验证，不要求导入账号具备 MySQL `REFERENCES` 权限；
- 构建顺序必须先维度、后事实、最后 DWS；首次构建要求目标表为空，成功后只允许对账复用，不自动删除或覆盖既有数据；
- 同一 Olist 数据版本成功构建后，若完整对账仍通过则重复执行直接复用，不产生重复数据；
- 失败批次只能记录异常类型，不记录凭据、连接串或原始异常消息；
- 普通单元测试使用 SQLite 受控 Fixture，真实 MySQL 集成单独执行并标识。

## Acceptance Criteria

- [x] 11 张 DWD 表按声明粒度建立，主键唯一；
- [x] DWD 业务外键无孤儿；
- [x] DWD 订单、订单项、支付、配送、评价行数与对应 ODS 一致；
- [x] `dim_date` 连续覆盖完整购买日期范围；
- [x] 两张 DWS 的主键粒度无重复；
- [x] DWD、地区 DWS、品类 DWS 的有效订单 GMV 逐分一致；
- [x] GMV 不含运费且不使用 `payment_value`；
- [x] 地区 DWS 的整体 `order_count` 与有效订单数一致；
- [x] 品类订单量没有被用于整体订单量对账；
- [x] 一对多支付 JOIN 的膨胀金额被检测，正式 DWS 不受其影响；
- [x] 比率字段未被持久化，Synthetic 基础量保持 `NULL`；
- [x] 同版本重复执行幂等；
- [x] DATA-002 专项测试通过；
- [x] 全量 pytest 不新增失败；
- [x] Ruff 不超过 51 项存量诊断；
- [x] mypy 不超过 40 个存量错误；
- [x] 未实现 DATA-003 或后续能力；
- [x] DATA-002 独立提交并推送。

## Validation Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/data/test_data_foundation.py
.\.venv\Scripts\python.exe -m app.scripts.build_data_foundation
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check app/data_foundation app/scripts/build_data_foundation.py test/data/test_data_foundation.py
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

## Completion Rule

只有 DWD 与两张 DWS 在受控测试和真实隔离库中均成功构建，第二次执行幂等，行数、主外键、粒度、GMV、Order Count 和 Join 膨胀检查全部通过，完成报告、独立 Commit 与 Push 均成功后，DATA-002 才算完成。完成后停止本 Feature，按用户的持续执行授权再进入 DATA-003。
