# Agent 工作流详细设计

## 1. 设计原则

- LLM 负责理解、规划和表达；
- Registry、Query Builder、Validator、Executor 和 Analyzer 负责确定性约束；
- 一个诊断问题由多项结构化任务组成，不等于一条 SQL；
- V1 单轮完成，禁止无上限自主循环；
- 所有节点输入输出使用可校验结构。

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

