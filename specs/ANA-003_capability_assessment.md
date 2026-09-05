# ANA-003 Capability Assessment

## 1. Feature

对 ANA-002 已验证的 GMV 诊断结构执行确定性的静态与运行时能力判断，输出 `supported_methods`、`unsupported_methods`、可用维度、缺失 Evidence 和数据质量状态。没有时间覆盖、必要字段、非空数据或通过的数据质量时不得开放相应方法；严格因果在 V1 始终不开放。

## 2. Source of Truth

1. 用户当前明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md`；
5. `docs/02_data_and_metric_design.md`；
6. `docs/04_analysis_methodology.md`；
7. `docs/05_agent_workflow.md`；
8. `docs/06_evaluation.md`；
9. `conf/meta_config.yaml` 的 Metric、Table、Column、Dimension 与 Relationship Registry；
10. `data/reports/DATA-002_data_foundation.json` 与 `data/reports/DATA-003_synthetic_evidence.json` 的已验收数据质量事实；
11. `specs/ANA-002_analysis_question_parser.md` 与已验收的 Parsed Question Schema；
12. `AGENTS.md`、`README.md` 和现有代码行为。

## 3. In Scope

- 定义严格的 Data Capability Profile、Data Quality、Analysis Method、Capability Level 与 Assessment Schema；
- Data Profile 描述当前请求 Scope/期间内可用日期范围、已存在列、具有非空值的列、数据质量状态和因果设计标志；
- 所有列必须使用 `table.column` 标识并存在于注入的 Metadata Catalog；
- 支持 `warehouse` 与 `synthetic_case` 两类已验收数据源快照，保持 Olist 与 Synthetic Evidence 边界；
- `period_comparison` 仅在当前期、基期和 GMV 基础量可用时开放；
- `metric_decomposition` 在整体/地区 Scope 要求地区 DWS 的整体 Order Count；仅在单一 Category Scope 内允许使用该品类切片的 `category_order_count`，禁止跨品类相加替代整体订单量；
- `dimension_contribution` 只在请求维度有对应的互斥 DWS/analysis 表 GMV、日期和维度键时开放；
- Traffic、Promotion、Inventory Validation 分别要求同 Scope 下的直接 Evidence、Order Count/Conversion 组件和分母字段均存在且非空；
- 单个候选因素缺失只关闭该方法并列出缺失字段，不隐藏其他可用方法；
- 基础期间/GMV 不可用或数据质量失败时关闭全部请求方法；
- `causal_inference` 始终出现在 `unsupported_methods`，即使快照声称存在实验标志也不越过 V1 产品边界；
- Capability Node 通过注入持有 Catalog 与 Data Profile，只把可序列化 Assessment 写入 State；
- 固定完整、部分缺失、期间不足、数据质量失败、维度缺失和因果边界样本并保存真实结果。

## 4. Out of Scope

- 不连接 MySQL、Qdrant 或 Elasticsearch，不自动探测真实数据库；
- 不修改 DATA-002/003 数据、Synthetic 配置、Metadata 配置或注册表；
- 不判断异常是否实际发生，不计算数值、变化率、Shapley 或维度贡献；
- 不生成 AnalysisPlan、AnalysisTask 或 SQL，不执行查询；
- 不校验 Evidence 内容或生成报告；
- 不修改现有 Query Graph、NL2SQL、SQL Policy 或 API；
- 不开放严格因果推断，不新增价格、退款、配送等 V1.1 方法；
- 不进入 ANA-004。

## 5. Frozen Capability Contract

完整能力输出固定为：

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

方法顺序固定为期间对比、指标拆解、维度贡献、Traffic、Promotion、Inventory、Causal。`missing_evidence` 只包含稳定的日期角色、数据质量标志或 Catalog 列标识；不得包含凭据、SQL 或原始数据值。

## 6. Allowed Files

- `specs/ANA-003_capability_assessment.md`；
- `app/diagnosis/__init__.py`；
- `app/diagnosis/capability.py`；
- `app/scripts/evaluate_capability_assessment_v1.py`；
- `data/evaluation/capability_assessment_golden_v1.json`；
- `data/reports/ANA-003_capability_assessment_evaluation.json`；
- `test/diagnosis/test_capability_assessment.py`；
- `ANA-003_COMPLETION.md`；
- `IMPLEMENTATION_STATUS.md`。

## 7. Local Plan

1. 定义严格的 Profile、Method、Level 与 Assessment Schema；
2. 从 Catalog 验证两类数据源的方法依赖，并确定当前 Scope 的基础表与候选因素字段；
3. 实现时间覆盖、数据质量、维度和逐因素降级规则；
4. 实现依赖注入节点，不连接生产 Graph；
5. 固定完整/降级样本并生成版本化评测报告；
6. 执行专项/全量 pytest、Ruff、mypy、敏感信息与 Diff Review；
7. 完成报告、独立提交并推送后停止 ANA-003。

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_capability_assessment.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_capability_assessment_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## 9. Acceptance Criteria

- Schema 拒绝未知字段、重复列/方法/维度、非限定列和非法日期范围；
- Data Profile 中任何列不存在于 Catalog 时 Assessment 拒绝运行；
- 完整 Profile 为一般 GMV 原因问题开放六个 V1 方法，仅关闭 Causal；
- Period/GMV 缺失或超出可用范围时不开放任何下游方法；
- Order Count 缺失时可保留 Period Comparison，但关闭 Decomposition 和依赖它的候选因素；
- Region 与 Category 维度能力分别由对应表/键/GMV 字段判断，不混用两个粒度；
- `category_order_count` 只允许在单一 Category Scope 内作为拆解或候选因素组件，绝不跨品类聚合用于整体 GMV 拆解；
- 单一 Traffic/Promotion/Inventory Evidence 缺失只关闭对应方法并明确缺失列；
- 数据质量失败关闭所有请求方法并标记 `data_quality_status = fail`；
- 因果设计标志不能在 V1 开放 `causal_inference`；
- Node 输出 JSON 可序列化，State 不包含 Catalog 或 Data Profile；
- 固定样本全部保存真实逐例结果和错误明细；
- 现有 Parser、Query Graph、SQL、Metadata、数据、数据库和 API 未修改；
- 全量 pytest 不回退，Ruff/mypy 不超过 ANA-002 基线 31/36。

## 10. Completion Boundary

完成 ANA-003 报告、独立提交并推送后停止，不得在本 Feature 中实现 ANA-004 Analysis Planner。
