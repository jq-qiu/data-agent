# DATA-003 Synthetic Evidence and Ground Truth

## Goal

在不覆盖 Olist ODS、DWD 或已验收 DWS 原值的前提下，生成固定 Seed、固定版本、可复现的 Traffic、Promotion、Inventory Synthetic Evidence，并建立可追溯的 Ground Truth Registry。每个异常必须先改变直接 Evidence，再沿 Conversion → Order Count → GMV 链生成独立的 `analysis_*` 结果。

## Direct Sources of Truth

- `AGENTS.md`；
- `IMPLEMENTATION_PLAN.md` 中 DATA-003 与 Gate 1；
- `docs/02_data_and_metric_design.md` 中 Synthetic、Ground Truth、指标链和可加性约束；
- `docs/04_analysis_methodology.md` 中候选因素 Evidence 与降级规则；
- `docs/06_evaluation.md` 中 D01-D10 Ground Truth 分桶；
- DATA-002 已验收的两张 Olist DWS。

## Prerequisites

- DATA-002 独立提交已推送；
- `data_agent_v1_dw` 中 DATA-002 成功批次和两张 DWS 对账通过；
- ODS、DWD 和 Olist DWS 保持只读事实源；
- 用户已授权在隔离库中创建和填充本 Spec 的固定 Synthetic 表。

## Versioned Generator Contract

- Generator Version：`synthetic-v1`；
- Random Seed：由版本化 JSON 配置固定；
- 基期：2018-04-01 至 2018-04-30；
- 本期：2018-05-01 至 2018-05-31；
- 基期订单量与 GMV 从相同 Scope 的 Olist DWS 读取；
- 基期 AOV 由 `GMV / Order Count` 运行时计算；
- 本期先应用 Evidence 因子，再确定 Conversion 变化，再生成 `analysis_order_count`，最后以基期 AOV 生成 `analysis_gmv`；
- 最终金额使用 Decimal 并按 0.01 精度量化；
- 相同 DWS、配置、Seed 和 Generator Version 必须得到相同内容哈希。

## Tables and Grains

- `synthetic_generation_batch`：一行一个生成批次；
- `fact_ground_truth_case`：一行一个 D01-D10 场景；
- `fact_business_event`：一行一个已知事件，字段覆盖设计文档要求并通过 `case_id` 关联场景；
- `analysis_sales_region_daily`：`case_id × date_id × region_id`；
- `analysis_sales_category_daily`：`case_id × date_id × region_id × category_id`。

`analysis_*` 表只保存可加总基础量：Visitors、Promotion 分子/分母、Inventory 分子/分母、Analysis Order Count、Analysis GMV、数据/生成器版本。AOV、Conversion Rate、Promotion Coverage 和 Inventory Fill Rate 不持久化，必须运行时由分子分母重算。

## Ground Truth Coverage

- D01-D02：Traffic Drop；
- D03-D04：Promotion End；
- D05-D06：Stockout；
- D07：Traffic + Promotion；
- D08：Traffic + Stockout；
- D09：No Clear Evidence，基期与本期结果保持一致；
- D10：Evidence Missing / Degrade，结果下降但 Visitors 缺失，不提供可支持原因。

事件类型只允许 `traffic_drop`、`promotion_end`、`stockout`。没有实验或准实验设计，Ground Truth 仅用于合成回归，不授权因果措辞。

## In Scope

1. 版本化配置与严格结构校验；
2. 固定 Seed 的确定性日级分配；
3. 三类直接 Evidence 与单/双因素组合；
4. Evidence 变化传导到分析订单量和分析 GMV；
5. Ground Truth Case 与 Business Event 表；
6. 缺失 Evidence 和无明显异常场景；
7. 内容摘要哈希、批次审计、幂等复用；
8. DATA-001、DATA-002 与 DATA-003 的完整 Gate 1 对账。

## Out of Scope

- 更新 Olist ODS、DWD、`dws_sales_region_daily` 或 `dws_sales_category_daily` 的任何值；
- 将 Synthetic 数据伪装为 Olist 原始事实；
- 生成价格、退款、配送等 V1.1 因素；
- 构造实验、对照组或因果效应估计；
- Metadata、Metric Registry、向量/全文索引；
- NL2SQL、SQL Validator、LangGraph、Analyzer、Evidence Report 或 API；
- 诊断模型评测分数。

## Safety and Idempotency

- 配置只允许固定字段、事件枚举和仓库内版本化文件；
- 所有 SQL 由固定表定义和查询构建，不接受用户或 LLM SQL；
- 首次生成要求 Synthetic 目标表为空；已成功版本只允许重新生成预期内容并校验哈希后复用；
- 不自动删除、覆盖或修复既有 Synthetic 数据；
- 失败批次只记录异常类型；
- 普通测试使用 SQLite，真实 MySQL 生成单独标识；
- 报告不包含原始用户数据、凭据或连接信息。

## Acceptance Criteria

- [x] 固定配置包含 Generator Version、Random Seed 和 10 个场景；
- [x] D01-D10 分桶与 `docs/06_evaluation.md` 一致；
- [x] 三类事件均存在，单因素、双因素、无明显异常、缺失 Evidence 均覆盖；
- [x] Ground Truth Event 的直接指标、期望指标、方向、强度与排名可追溯；
- [x] `analysis_*` 表严格使用声明粒度且无重复；
- [x] 同配置与 Seed 在两个独立受控数据库中产生相同摘要哈希；
- [x] 同一真实数据库重复执行复用同一成功批次；
- [x] Traffic 事件先降低 Visitors，再降低分析订单量与分析 GMV；
- [x] Promotion 事件先降低 Promotion Coverage，再降低 Conversion、订单量和 GMV；
- [x] Stockout 事件先降低 Inventory Fill Rate，再降低 Conversion、订单量和 GMV；
- [x] 双因素场景的两个直接 Evidence 均按配置变化；
- [x] D09 基期/本期无明显结果变化且没有 Business Event；
- [x] D10 结果下降、Visitors 缺失且没有支持原因；
- [x] `Orders ≈ Visitors × Conversion Rate` 与 `GMV ≈ Orders × AOV` 在定义精度内成立；
- [x] 分母为 0 时比率返回 `NULL`/`None`；
- [x] Olist ODS、DWD、DWS 摘要在生成前后不变；
- [x] Gate 1 所有条件通过；
- [x] DATA-003 专项与全量 pytest 通过；
- [x] Ruff 不超过 51 项存量诊断；
- [x] mypy 不超过 40 个存量错误；
- [x] 未实现 META-001 或后续能力；
- [x] DATA-003 独立提交并推送。

## Validation Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/data/test_synthetic_evidence.py
.\.venv\Scripts\python.exe -m app.scripts.generate_synthetic_evidence
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check app/synthetic app/scripts/generate_synthetic_evidence.py test/data/test_synthetic_evidence.py
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

## Completion Rule

只有 10 个场景与三类事件在受控测试和真实隔离库中均可复现，Ground Truth、直接 Evidence、分析订单量和分析 GMV 链路一致，缺失 Evidence 正确保留，Olist 各层摘要不变，Gate 1 全部通过，完成报告、独立 Commit 和 Push 均成功后，DATA-003 才算完成。完成后停止本 Feature，再按用户的持续执行授权进入 META-001。
