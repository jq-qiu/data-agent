# Agent 工作流详细设计

## 1. 设计原则

- LLM 负责理解、规划和表达；
- Registry、Query Builder、Validator、Executor 和 Analyzer 负责确定性约束；
- 一个诊断问题由多项结构化任务组成，不等于一条 SQL；
- V1 单轮完成，禁止无上限自主循环；
- 所有节点输入输出使用可校验结构。

当前 V1 的 Analysis Question Parser、Capability Assessment 和 Analysis Planner 均为确定性实现。这里“LLM 负责规划”描述的是受限的后续演进方向，不表示当前诊断运行时已经调用 LLM 规划。

## 2. V1 Graph

```text
START
  ↓
IntentRouter
  ├── QUERY ──► ExistingNL2SQL ──► QueryAnswer ──► END
  │
  └── DIAGNOSIS
          ↓
  AnalysisQuestionParser
          ↓
  CapabilityAssessment
          ↓
  AnalysisPlanner
          ↓
  AnalysisTaskExecutor
          ↓
  DeterministicAnalyzer
          ↓
  EvidenceChecker
          ↓
  ReportGenerator
          ↓
         END
```

`EvidenceChecker` 与 `ReportGenerator` 可以在 ANA-007 中实现，但必须保持两个独立逻辑步骤。Report Generator 的输入只能是 Validated Evidence。

## 3. Intent Router

输出：

```json
{
  "intent": "QUERY | DIAGNOSIS | UNSUPPORTED",
  "confidence": 0.0,
  "reason": ""
}
```

示例：

- “2018 年 5 月 GMV 是多少” → QUERY；
- “为什么 2018 年 5 月 GMV 下降” → DIAGNOSIS；
- “预测明年销量并自动调价” → UNSUPPORTED。

低置信度时不得强行进入诊断。

## 4. Analysis Question Parser

输出：

```json
{
  "target_metric": "gmv",
  "current_period": {
    "start": "2018-05-01",
    "end": "2018-05-31"
  },
  "baseline_period": {
    "start": "2018-04-01",
    "end": "2018-04-30"
  },
  "comparison_type": "previous_period",
  "scope": {
    "region": null,
    "category": null
  },
  "requested_dimensions": ["region", "category"],
  "requested_factors": ["traffic", "promotion", "inventory"]
}
```

时间、指标或 Scope 缺失且无法安全推导时，应输出结构化错误，不得默认猜测。

## 5. Capability Assessment

能力判断以规则为主，输入：

- Parsed Question；
- Metric Registry；
- Metadata/Relationship Registry；
- 数据可用时间范围；
- DWS 和 Evidence 字段状态；
- 数据质量检查结果。

输出：

```json
{
  "level": "association_diagnosis",
  "supported_methods": [
    "period_comparison",
    "metric_decomposition",
    "dimension_contribution",
    "traffic_validation",
    "promotion_validation",
    "inventory_validation"
  ],
  "unsupported_methods": ["causal_inference"],
  "available_dimensions": ["region", "category"],
  "missing_evidence": [],
  "data_quality_status": "pass"
}
```

Planner 只能选择 `supported_methods`。

## 6. Analysis Planner

V1 最多生成四类任务：

```text
T1 period_comparison
T2 metric_decomposition
T3 dimension_contribution
T4 candidate_validation
```

任务协议：

```json
{
  "task_id": "T3",
  "method": "dimension_contribution",
  "metric": "gmv",
  "current_period": ["2018-05-01", "2018-05-31"],
  "baseline_period": ["2018-04-01", "2018-04-30"],
  "dimension": "category",
  "scope": {},
  "depends_on": ["T1"]
}
```

限制：

- 最大任务数由配置固定；
- 不支持的方法不能进入计划；
- 不允许 Planner 输出 SQL；
- 计划失败不能自动进入无限重试。

## 7. Analysis Task Executor

执行器根据 `method` 路由到受控 Query Builder：

```text
period_comparison_builder
metric_decomposition_input_builder
dimension_contribution_builder
candidate_factor_builder
```

Query Builder：

- 从 Registry 获取公式、表和字段；
- 只接受结构化白名单参数；
- 生成参数化、只读 SQL；
- 复用统一 SQL Validator 和 Executor；
- 返回 Query ID、SQL 指纹、口径版本和结构化结果。

## 8. Deterministic Analyzer

Analyzer 不调用 LLM，至少包含：

```text
PeriodComparisonAnalyzer
GmvShapleyAnalyzer
DimensionContributionAnalyzer
CandidateFactorAnalyzer
```

输入输出必须可序列化，并包含：

```text
analysis_result_id
method
input_query_ids
metric_version
values
reconciliation
warnings
```

## 9. State 与 Context

### 9.1 State

建议 V1 动态状态：

```text
question
intent
parsed_question
capability
analysis_plan
current_task_index
query_results
analysis_results
validated_evidence
final_answer
errors
```

State 中禁止放：

```text
MySQL Client
Qdrant Client
Elasticsearch Client
Repository
LLM Client
Embedding Client
Registry 实例
```

### 9.2 Context

Context 保存只读或生命周期依赖：

```text
Repositories
LLM/Embedding adapters
Metric Registry
Analysis Method Registry
SQL Validator/Executor
Runtime configuration snapshot
```

## 10. 错误和停止条件

错误分类：

```text
UNSUPPORTED_INTENT
UNKNOWN_METRIC
INVALID_TIME_RANGE
MISSING_BASELINE
INSUFFICIENT_DATA
DATA_QUALITY_FAILED
QUERY_BUILD_FAILED
SQL_VALIDATION_FAILED
SQL_EXECUTION_FAILED
NUMERIC_RECONCILIATION_FAILED
EVIDENCE_VALIDATION_FAILED
```

V1 停止条件：

- 普通问数得到结果或达到 SQL 修复上限；
- 诊断问题完成计划中的有限任务；
- 数据质量失败；
- 关键指标或基期缺失；
- 数字无法对账；
- Evidence 校验失败；
- 达到最大任务数或运行预算。

## 11. V1 API 契约方向

保持单轮请求：

```json
{
  "question": "为什么2018年5月GMV下降？"
}
```

响应：

```json
{
  "intent": "DIAGNOSIS",
  "answer": "...",
  "analysis_trace": [],
  "evidence": [],
  "limitations": []
}
```

当前已有 API 使用 `query` 字段。是否保持兼容或迁移到 `question` 必须在 API-001 单独决策，不能在分析 Feature 中顺手修改。

## 12. 目标语义规划流程

`SEM-001` 冻结的目标流程如下；新增节点均为后续 Feature，当前运行时流程仍以第 2 节为准。

```text
用户自然语言
  ↓
Semantic Grounding（语义绑定）
  ├─ 指标绑定
  ├─ 维度绑定
  ├─ 维度值绑定
  ├─ 时间绑定
  └─ Scope 校验
  ↓
ParsedAnalysisQuestion（规范化分析问题）
  ↓
Analysis Semantic Registry（静态分析知识）
  +
RuntimeCapability（当前数据可用能力）
  ↓
PlannerSemanticContext Builder
  ↓
PlannerSemanticContext（单次请求规划说明书）
  ↓
Planner Policy
  ├─ 唯一合法路径：Deterministic Planner
  └─ 多个合法路径：LLM Planner，最多一次
  ↓
AnalysisPlanValidator
  ├─ 通过：Validated AnalysisPlan
  └─ 失败/超时/模型不可用：不重试模型，确定性回退
  ↓
AnalysisTask Tool Dispatcher
  ↓
Controlled Query Builder / Executor
  ↓
Deterministic Analyzer
  ↓
Evidence Checker
  ↓
Report Generator
```

### 12.1 PlannerSemanticContext Builder

Builder 只组合已验证业务对象，不做指标计算或数据访问。输入是 `ParsedAnalysisQuestion`、静态分析语义和 `RuntimeCapability`；输出是不可变、可序列化的 `PlannerSemanticContext`。上下文不暴露物理表、字段、JOIN、SQL、数据库连接、原始行或 Ground Truth。

### 12.2 Planner Policy 与模型调用预算

- 标准问题只有唯一合法路径时使用确定性 Planner，规划阶段模型调用为 0；
- 存在多个合法路径且确实需要语义取舍时，LLM Planner 最多调用一次；
- 如果意图本身存在允许澄清的歧义，整次归因请求最多再调用一次，因此模型调用总上限为 2；
- LLM 不写 SQL、不选择物理表列、不计算指标或贡献率；
- 模型输出无效、超时或不可用时，不进行模型重试，直接使用确定性回退。

### 12.3 AnalysisPlanValidator

Validator 必须拒绝：

- `RuntimeCapability.supported_methods` 之外的方法；
- Registry 未开放的维度、候选因素或参数；
- 改变原问题指标、时间、基期或 Scope 的任务；
- 超过最大任务数、非法依赖、循环依赖或无停止条件的计划；
- SQL、表名、列名、JOIN 或任意命令。

通过后的 `AnalysisPlan` 才能进入执行链。现有 `AnalysisTask` 本身就是类型化工具调用，由 Tool Dispatcher 按 `method` 路由到受控 Builder，不新增重复协议。

### 12.4 实现状态

`SEM-002` 已实现 Semantic Grounder、Analysis Semantic Registry 和 Context Builder。Grounder 输出固定状态：`READY` 才可进入 Capability；`CLARIFICATION_REQUIRED` 表示需要补充或选择；`UNSUPPORTED` 表示超出当前产品能力。

`CLARIFY-001` 已将 Grounder 接入生产单轮 DIAGNOSIS 分支，执行顺序固定为 `Intent Router -> Semantic Grounding -> Runtime Capability -> Existing Diagnosis Graph`。非 `READY` 结果在读取运行时数据能力前终止，并返回稳定原因、缺失/歧义字段、逻辑候选、推荐完整问题和安全 Trace；`READY` 结果继续使用现有确定性 Parser、Capability、Planner 和执行链，检索补全后的绑定通过等价规范问题重新交给 Parser，不修改 Graph 或诊断算法。前端区分 query、diagnosis、clarification、unsupported 和 error，推荐问题按钮只填入输入框，不建立会话记忆。

受限 LLM Planner 与 Validator 仍计划在 `PLAN-LLM-001` 实现；在该 Feature 完成并实测前，不得对外宣称运行时已使用 LLM 进行归因规划。
