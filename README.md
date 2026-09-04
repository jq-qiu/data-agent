# NL2SQL 经营指标异动诊断 Agent

## 1. 项目定位

本项目在现有 NL2SQL 数据问答能力上，增加受控的经营指标异动诊断能力。系统既能回答“2018 年 5 月 GMV 是多少”，也能回答“2018 年 5 月 GMV 为什么下降”。

V1 的准确定位是：

> 基于 LangGraph 与 NL2SQL 的经营指标异动诊断 Agent。

英文名称：

> NL2SQL-based Business Metric Diagnosis Agent.

V1 实现的是指标拆解、变化贡献和关联诊断，不是严格的因果推断系统。

## 2. 当前真实状态

当前仓库已有一条可复用的单轮 NL2SQL 链路，包括：

- 关键词抽取与扩展；
- Qdrant 表字段与指标语义召回；
- Elasticsearch 字段值召回；
- Schema Linking 上下文组装；
- SQL 生成、静态校验、纠错和执行；
- FastAPI SSE 查询接口。

当前尚未实现：

- Olist 数据导入与新数仓；
- 两张诊断 DWS；
- Synthetic Evidence 与 Ground Truth；
- 诊断意图路由和分析规划；
- 指标拆解、维度贡献和证据报告；
- 多轮会话。

因此，设计目标与已实现能力必须在报告和面试中严格区分。

## 3. V1 核心场景

V1 只完成一个端到端场景：

> GMV 下降诊断。

指标树：

```text
GMV
├── Order Count
└── AOV

Order Count
├── Visitors
└── Conversion Rate
```

V1 验证三类候选经营因素：

- Traffic Drop；
- Promotion End；
- Stockout。

V1 为单轮分析系统。类似“那圣保罗州呢？”的省略式追问属于 V1.1，不得作为 V1 已实现能力演示。

## 4. 总体架构

```text
User Question
      │
      ▼
Intent Router
      │
      ├──────── QUERY ────────► Existing NL2SQL Pipeline ──► Answer
      │
      └──────── DIAGNOSIS
                     │
                     ▼
          Analysis Question Parser
                     │
                     ▼
          Capability Assessment
                     │
                     ▼
             Analysis Planner
                     │
                     ▼
        Structured Analysis Tasks
                     │
                     ▼
     Controlled Query Builder/Executor
                     │
                     ▼
        Deterministic Analyzer
                     │
                     ▼
          Evidence Validation
                     │
                     ▼
             Report Generator
```

开放式问数使用 LLM NL2SQL；结构固定的诊断方法使用结构化任务和受控 SQL。两条路径共享 Metadata、Metric Registry、SQL Validator、SQL Executor 和数据访问层。

## 5. 数据方案

项目采用 Olist 匿名电商数据作为真实业务数据主体，并补充可复现的 Synthetic Evidence。

```text
Olist Raw
   ↓
DWD Facts & Dimensions
   ↓
Synthetic Event Injection
   ↓
Diagnosis DWS
   ↓
NL2SQL / Diagnosis Agent
```

原始地域保持巴西州级语义，例如 `SP` 表示 São Paulo（圣保罗州），不得伪装成国内华东或华南数据。

整体指标拆解使用：

```text
dws_sales_region_daily
粒度：日期 × 地区
```

品类贡献分析使用：

```text
dws_sales_category_daily
粒度：日期 × 地区 × 品类
```

`category_order_count` 只能在品类切片内部使用，禁止跨品类求和后解释为整体订单量。

## 6. 指标口径

```text
GMV = SUM(item_sales_amount)

Order Count = COUNT(DISTINCT order_id)

AOV = GMV / Order Count

Conversion Rate = Order Count / Visitors

Promotion Coverage = Promoted SKU Count / Active SKU Count

Inventory Fill Rate = Available SKU Count / Required SKU Count
```

具体粒度、空值规则、过滤条件和公式见 [数据与指标设计](docs/02_data_and_metric_design.md)。

## 7. 文档导航

长期事实源只有以下文档：

1. [产品范围](docs/01_product_scope.md)
2. [数据与指标设计](docs/02_data_and_metric_design.md)
3. [Metadata 与 NL2SQL](docs/03_metadata_and_nl2sql.md)
4. [诊断分析方法](docs/04_analysis_methodology.md)
5. [Agent 工作流](docs/05_agent_workflow.md)
6. [评测设计](docs/06_evaluation.md)
7. [实施计划](IMPLEMENTATION_PLAN.md)
8. [Coding Agent 工作约束](AGENTS.md)

当前第一个执行任务：[ENG-001 Engineering Baseline](specs/ENG-001_engineering_baseline.md)。

`attribution-analysis-agent-spec/` 是早期设计资料，不再作为 V1 实现事实源。发生冲突时，以根目录上述文档为准。

## 8. 开发顺序

```text
ENG-001 Engineering Baseline
  → DOC-001 Spec Cleanup
  → DATA-001 Olist Import
  → DATA-002 DWD and Diagnosis DWS
  → DATA-003 Synthetic Evidence and Ground Truth
  → META-001 Metadata Adaptation
  → SQL-001 NL2SQL Adaptation and Evaluation
  → ANA-001 ... ANA-007 Diagnosis Agent
  → EVAL-001 Diagnosis Regression
  → Minimal API and Demo
```

任何前置 Gate 未通过时，不得提前实现下游 Feature。

## 9. 本地验证

本项目的虚拟环境位于项目所在的 D 盘目录：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
```

测试、Lint 或类型检查存在存量问题时，应真实记录基线，不得伪造全绿结果，也不得在无关 Feature 中顺手重构业务代码。

## 10. 安全与配置

- 禁止提交 API Key、数据库密码、Token 和完整连接串；
- `conf/app_config.yaml` 是本地敏感配置，已从 Git 排除；
- 数据库查询账号必须只读；
- SQL 执行必须经过安全校验；
- 报告生成只能读取已验证 Evidence，不能直接读取原始查询结果自由发挥。
