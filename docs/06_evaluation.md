# 评测与错误分析详细设计

## 1. 评测声明

首版 10 条诊断数据是功能回归集，用于验证诊断链路、证据约束和数值一致性，不代表生产环境下的统计泛化能力。

任何指标提升必须来自同一数据集版本、代码版本、模型版本和评测方法下的基线对比。没有真实运行记录时，只能称为设计目标。

## 2. 分层评测

```text
Metadata Retrieval
      ↓
Question Understanding
      ↓
Schema Linking
      ↓
SQL Generation/Execution
      ↓
Analysis Planning
      ↓
Numeric Analysis
      ↓
Evidence Validation
      ↓
Final Report
```

最终答案错误时必须标记主要错误层，不能只调整最终 Prompt。

## 3. Metadata 数据集

首版 10～15 条，覆盖：

- 指标别名；
- 表和字段别名；
- 巴西州代码与中英文名称；
- 商品品类；
- JOIN 关系；
- 一对多粒度警告；
- 无关候选噪声。

指标：

```text
Metric Hit@1
Table Recall@K
Column Recall@K
Join-key Recall
Value Grounding Accuracy
MRR
Context Precision
Context Recall
Context Token Count
```

## 4. NL2SQL Golden Dataset

首版固定 30 条：

| 类型 | 数量 |
|---|---:|
| 简单查询 | 5 |
| 聚合 | 5 |
| 时间 | 5 |
| 多表 JOIN | 5 |
| TopN | 5 |
| 期间对比 | 5 |

每条样本至少包含：

```json
{
  "case_id": "sql_001",
  "question": "2018年5月GMV是多少",
  "expected_metric_ids": ["gmv"],
  "expected_tables": ["fact_order", "fact_order_item"],
  "expected_columns": ["purchase_date", "price", "order_id"],
  "reference_sql": "...",
  "expected_result": "versioned fixture or checksum",
  "risk_tags": ["time", "one_to_many_join"]
}
```

主要指标：

```text
SQL Validity Rate
SQL Executability
Execution Accuracy
Metric Accuracy
Table Accuracy/Recall
Column Accuracy/Recall
JOIN Accuracy
Grain Safety Rate
Correction Success Rate
```

Execution Accuracy 以规范化结果集为主，不要求 SQL 字符串完全一致。

## 5. Diagnosis Golden Dataset

首版固定 10 条：

| Case | Ground Truth |
|---|---|
| D01-D02 | Traffic Drop |
| D03-D04 | Promotion End |
| D05-D06 | Stockout |
| D07 | Traffic + Promotion |
| D08 | Traffic + Stockout |
| D09 | No Clear Evidence |
| D10 | Evidence Missing / Degrade |

单条结构：

```json
{
  "case_id": "D05",
  "question": "为什么2018年5月圣保罗州GMV下降？",
  "expected_problem": {
    "metric": "gmv",
    "current_period": "2018-05",
    "baseline_period": "2018-04",
    "scope": {"region": "SP"}
  },
  "expected_methods": [
    "period_comparison",
    "metric_decomposition",
    "dimension_contribution",
    "inventory_validation"
  ],
  "ground_truth_causes": ["stockout"],
  "expected_evidence_ids": ["..."],
  "forbidden_claims": ["库存不足已经被证明是唯一原因"]
}
```

## 6. Diagnosis 指标

```text
Single Cause Hit@1
Root Cause Recall@3
Evidence Precision
Evidence Recall
Numeric Consistency
Contribution Reconciliation Error
Unsupported Claim Rate
Correct Degradation Rate
Causal-language Violation Rate
```

解释：

- `Single Cause Hit@1`：单原因样本中第一候选是否命中；
- `Root Cause Recall@3`：Ground Truth 原因在前三候选中的覆盖率；
- `Evidence Precision`：输出 Evidence 中真正支持结论的比例；
- `Unsupported Claim Rate`：缺少 Evidence 的事实或原因断言比例；
- `Numeric Consistency`：报告数字与 Query/Analyzer 结果逐项一致；
- `Correct Degradation Rate`：应降级案例是否正确说明能力限制。

10 条样本只报告分子/分母，例如 `8/10`，不能夸大为生产准确率。

## 7. V1 Gate 目标

以下为发布目标，不是当前实测成绩：

```text
Numeric Consistency = 10/10
Unsupported Claim Count = 0
Causal-language Violation Count = 0
Evidence Missing Case Correctly Degraded = 1/1
Root Cause Recall@3 ≥ 8/10
```

NL2SQL 目标应在首次真实 Baseline 后制定，避免先写一个没有依据的高阈值。

## 8. RAGAS 使用边界

RAGAS 可辅助评估：

- Context Precision；
- Context Recall；
- Faithfulness；
- Answer Relevancy。

项目自定义确定性指标负责：

- 指标、表、字段和 JOIN 命中；
- SQL 执行结果正确性；
- 粒度安全；
- Shapley 和贡献对账；
- Root Cause 命中；
- Evidence 来源与数字一致性。

RAGAS 分数不能代替 SQL 和业务口径核验。

## 9. Error Analysis

固定错误分类：

```text
Metadata Retrieval Error
Metric Recognition Error
Schema Linking Error
SQL Generation Error
SQL Execution Error
Analysis Planning Error
Query Builder Error
Numeric Analysis Error
Evidence Validation Error
Unsupported Claim
Degradation Error
```

每次正式运行保存：

```text
eval_runs/<run_id>/
├── summary.json
├── metadata_results.csv
├── nl2sql_results.csv
├── diagnosis_results.csv
└── error_analysis.md
```

运行记录至少包含：

- 代码提交；
- 数据集和 Synthetic Generator 版本；
- Metric Registry 版本；
- 模型、参数和 Prompt 版本；
- 样本数和分桶结果；
- 失败样本与错误分类；
- 延迟、Token 和费用；
- 已知限制。

每次迭代只修改一个主要假设，例如 TopK、别名、Prompt、规则或算法，并在完整固定数据集上回归。

## 10. 语义规划评测契约

`SEM-001` 只定义后续评测口径，本 Feature 未运行 LLM Planner 评测，也不能把设计目标写成实测结果。

### 10.1 Semantic Grounding

固定样本应覆盖指标别名、维度别名、州代码与中英文名、品类值、时间范围、歧义值、未知值和高基数噪声。至少报告：

```text
Metric Binding Accuracy
Dimension Binding Accuracy
Dimension Value Binding Accuracy
Time Resolution Accuracy
Scope Validation Accuracy
Ambiguity Rejection Accuracy
```

### 10.2 PlannerSemanticContext

逐例执行确定性契约检查：

- 必需分析关系、可用维度、因素、工具和限制是否完整；
- 物理表、字段、JOIN、SQL、原始行、Ground Truth 和秘密信息泄漏数是否为 0；
- 真实 Olist 缺失 Evidence 时是否关闭对应能力；
- Synthetic 数据是否只开放其实际存在的 Evidence；
- 上下文 Token、构建延迟和版本是否有记录。

### 10.3 Plan 与回退

后续 `PLAN-LLM-001` 至少报告：

```text
Supported Method Precision = 100%
Metric/Time/Scope Mutation Count = 0
Task Limit Violation Count = 0
Invalid Dependency Count = 0
Schema Leakage Count = 0
Deterministic Fallback Success Rate = 100%
Planner Model Calls <= 1
Total Attribution Model Calls <= 2
```

同时记录确定性路径比例、LLM 路径比例、Validator 拒绝原因、回退原因、规划延迟、Token 和费用。模型输出正确性必须与相同 Golden Dataset 上的确定性基线对比；没有真实运行不得宣称提升。

### 10.4 SEM-002 固定功能评测

`SEM-002` 使用 12 条固定样本和 Stubbed Qdrant/Elasticsearch 契约完成组件级评测：

```text
Exact Match = 12/12
Binding Status Accuracy = 12/12
READY Exact = 5/5
Clarification Exact = 4/4
Unsupported Exact = 3/3
Retrieval Policy Match = 12/12
Physical Schema Leakage Count = 0
LLM Call Count = 0
```

该结果验证代码契约，不代表真实外部检索准确率。未执行真实 Qdrant/Elasticsearch 检索时必须明确写“未评测”，不能用 Stub 结果替代线上召回指标。

### 10.5 CLARIFY-001 单轮澄清集成评测

`CLARIFY-001` 的生产级评测至少报告：

```text
READY Continues Existing Graph Rate = 100%
Non-READY Data Access Count = 0
Clarification Reason Accuracy = 100%
Missing/Ambiguous Field Accuracy = 100%
Logical Candidate Schema Leakage Count = 0
Canonical Reparse Equality Rate = 100%
Single Terminal Event Rate = 100%
LLM Call Count = 0
```

固定评测应覆盖缺少时间、缺少指标、不完整基期、歧义 Scope、明确不支持指标、非法期间、完整诊断和原 QUERY/UNSUPPORTED 分支。真实 Qdrant/Elasticsearch 语义检索尚未运行时，必须写“未评测”，不能用 SEM-002 的 Stub 契约分数冒充线上召回指标。
