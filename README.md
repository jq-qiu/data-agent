# NL2SQL 经营指标异动诊断 Agent

## 1. 项目定位

本项目在现有 NL2SQL 数据问答能力上，增加受控的经营指标异动诊断能力。系统既能回答“2018 年 5 月 GMV 是多少”，也能回答“2018 年 5 月 GMV 为什么下降”。

V1 的准确定位是：

> 基于 LangGraph 与 NL2SQL 的经营指标异动诊断 Agent。

英文名称：

> NL2SQL-based Business Metric Diagnosis Agent.

V1 实现的是指标拆解、变化贡献和关联诊断，不是严格的因果推断系统。

## 2. 当前真实状态

当前 MVP V1 已完成并验证以下链路：

- 关键词抽取与扩展；
- Qdrant 表字段与指标语义召回；
- Elasticsearch 字段值召回；
- Schema Linking 上下文组装；
- SQL 生成、静态校验、纠错和执行；
- Olist 隔离数仓、诊断 DWS 与可复现 Synthetic Evidence；
- 强规则优先、歧义语义兜底的混合意图路由，以及确定性的问题解析、能力评估和分析规划；
- 受控查询、确定性计算、Evidence 校验和诊断报告；
- FastAPI SSE 单轮查询与诊断接口。
- Vue 3/Vite 单轮经营分析前端，支持流式进度、问数表格与证据化诊断展示。
- FastAPI 同源托管前端与 API 的单进程本地运行方式。
- 可复现的 Synthetic 诊断演示入口，展示 Traffic Drop、Promotion End 与 Stockout 完整证据链。

API-001 的六个固定问题已通过真实服务依赖的 HTTP/SSE 演示。真实
Olist DWS 中 Traffic、Promotion 和 Inventory 候选字段为空时，诊断会明确
降级，不会伪造 Evidence。当前仍不支持：

- 省略式多轮会话；
- 登录、租户、权限和附件；
- 严格因果推断或自动经营动作；
- 生产部署、监控与多租户前端能力。

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

意图路由优先使用确定性规则识别 Top/Bottom N、聚合、同比/环比、占比、分布和阈值等问数表达。只有无法由规则判定的请求才调用结构化语义分类器；预测、外部动作、省略式追问和严格因果等强边界不会交给模型覆盖。路由为 QUERY 只表示请求进入 NL2SQL 链路。SQL-003 已将受控分组 TopN（ROW_NUMBER 窗口、每组至多 N 行、稳定标识打破并列）纳入只读校验和固定评测。

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

实施进度以 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) 为准。已完成 Feature 的规范和报告保留在仓库中，例如 [ENG-001 Engineering Baseline](specs/ENG-001_engineering_baseline.md) 与 [ENG-001 Baseline Report](ENG-001_BASELINE.md)。进入新 Feature 时必须先在 `specs/` 中建立对应 Spec，不得依赖 README 中容易过时的“当前任务”描述。

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

## 10. 本地运行

运行前需要准备：

- 已安装项目 Python 依赖，以及 Node.js/npm；
- 本地忽略的 `conf/app_config.yaml`；
- 配置中的 DW 数据库必须是隔离库 `data_agent_v1_dw`；
- MySQL、Qdrant、Elasticsearch、Embedding 和 LLM 服务已经可访问。

推荐使用单进程启动命令：

```powershell
.\.venv\Scripts\python.exe -m app.scripts.serve
```

启动器会在前端依赖缺失时执行锁文件安装，生成新的生产构建，然后由 FastAPI 在同一端口托管网页和 `/api/query`。默认访问地址是 `http://127.0.0.1:8000`。

只执行安全预检和构建、不启动服务：

```powershell
.\.venv\Scripts\python.exe -m app.scripts.serve --check
```

可选参数：`--install` 强制重新执行 `npm ci`；`--skip-build` 使用已经存在且验证通过的 `frontend/dist`；`--host` 和 `--port` 修改监听地址。默认仅绑定本机回环地址，部署到网络接口必须由操作者显式选择。

`GET /api/health/live` 只表示 Web 进程存活，不代表数据库、检索服务或模型服务已经就绪。当前方式面向单机和受控环境，不包含 TLS、域名、反向代理、高可用或生产 SLA。

前端开发时仍可分别运行 FastAPI 与 `npm run dev --prefix frontend`，Vite 会将 `/api` 代理到本地 8000 端口。

## 11. 安全与配置

- 禁止提交 API Key、数据库密码、Token 和完整连接串；
- `conf/app_config.yaml` 是本地敏感配置，已从 Git 排除；
- 数据库查询账号必须只读；
- SQL 执行必须经过安全校验；
- 报告生成只能读取已验证 Evidence，不能直接读取原始查询结果自由发挥。
