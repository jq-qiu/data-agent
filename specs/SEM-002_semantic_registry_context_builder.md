# SEM-002 Semantic Registry and Context Builder

## 1. Feature

实现归因分析的受控语义绑定、分析语义 Registry 投影和 `PlannerSemanticContext` Builder。系统优先使用 Metadata Catalog 中的规范值与别名；确定性绑定不足时，可通过 Qdrant 召回指标/逻辑维度候选、通过 Elasticsearch 召回地区/品类规范值候选，并在 Catalog 白名单、置信度和歧义规则校验后输出 `READY`、`CLARIFICATION_REQUIRED` 或 `UNSUPPORTED`。

本 Feature 不接入 LLM Planner，不修改现有生产 Graph、API、前端或诊断计算链。

## 2. Source of Truth

1. 用户当前明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md` 至 `docs/06_evaluation.md`；
5. `specs/SEM-001_analysis_semantic_context_design.md`；
6. `specs/META-001_metadata_adaptation.md`；
7. `specs/ANA-002_analysis_question_parser.md`、`specs/ANA-003_capability_assessment.md`、`specs/ANA-004_analysis_planner.md`；
8. `AGENTS.md`、`README.md` 和当前代码行为。

若事实源冲突，停止相关实现，不创造指标口径、物理字段、维度值、分析方法或因果规则。

## 3. In Scope

- 定义严格、不可变、可 JSON 序列化的语义候选、绑定状态和绑定结果；
- 复用现有 `AnalysisQuestionParser` 作为确定性第一路径；
- 只有确定性绑定缺失或显式维度无法识别时才调用受控检索；
- 实现 Qdrant/Embedding 指标和字段候选召回，并把字段候选映射为 `region | category` 逻辑维度；
- 实现 Elasticsearch 字段值候选召回，只允许映射到 `dim_region.state_code` 与 `dim_category.category_id` 的规范 Scope 值；
- 所有检索候选必须存在于注入的 Metadata Catalog 或分析语义 Registry；
- 唯一、超过阈值且满足分差的候选才可自动绑定；歧义不得猜测；
- 将缺少指标/时间/基期或歧义 Scope 转换为 `CLARIFICATION_REQUIRED`，并提供稳定原因和完整问题示例；
- 将非诊断意图、明确不支持的指标、非法期间和产品边界外请求转换为 `UNSUPPORTED`；
- 定义 `MetricAnalysisDefinition`、`DimensionDefinition`、`CandidateFactorDefinition` 和 `AnalysisToolDefinition`；
- 从 Metadata Catalog 构建并校验 V1 Analysis Semantic Registry，不复制物理指标公式；
- 从 `ParsedAnalysisQuestion`、`CapabilityAssessment` 和 Registry 构建无物理 Schema 的 `PlannerSemanticContext`；
- 将 Capability 的物理缺失字段转换为逻辑限制代码，不直接传入 Planner 上下文；
- 使用 Stub/Mock 完成普通测试，并保存固定功能评测结果；
- 更新实现状态和直接相关架构文档。

## 4. Out of Scope

- 不实现、调用或配置 LLM Planner、Prompt 或 `AnalysisPlanValidator`；
- 不修改现有 Intent Router、`AnalysisQuestionParser`、Capability Assessor 或确定性 Analysis Planner 行为；
- 不把新节点接入现有 LangGraph、Query Service、API 或前端；
- 不实现真正的多轮补槽、`conversation_id` 或 Checkpointer；
- 不生成 SQL、不执行数据库查询、不修改 Qdrant/ES 索引；
- 不修改 AOV、GMV、Order Count、NL2SQL、Controlled Query、Analyzer、Evidence 或 Report 业务逻辑；
- 不开放 seller 维度、价格、退款、配送或严格因果推断；
- 不进入 `PLAN-LLM-001`、`CLARIFY-001` 或其他后续 Feature。

## 5. Frozen Contracts

### 5.1 Binding Status

```text
READY
CLARIFICATION_REQUIRED
UNSUPPORTED
```

只有 `READY` 可以携带 `ParsedAnalysisQuestion` 并进入 Capability Assessment。非 READY 结果必须包含稳定 `reason`；候选与用户建议不得包含物理表、字段、SQL、连接信息或原始数据行。

### 5.2 Retrieval Policy

```text
确定性规范值/别名
  ↓ 未完成
Qdrant：指标、允许的逻辑维度候选
Elasticsearch：允许的地区/品类规范值候选
  ↓
Registry 白名单 + 类型 + 阈值 + 分差 + 歧义校验
```

- Qdrant 低于阈值的候选不得使用；
- 第一、第二候选分差不足时不得自动选择；
- ES 同一逻辑维度返回多个规范值时必须要求澄清；
- 检索故障不得绕过校验或抛出外部错误细节，必须失败关闭；
- 不将完整字段值域或 Qdrant 物理字段候选传给 Planner。

### 5.3 PlannerSemanticContext

上下文只包含：规范问题、指标分析恒等式、当前可用的逻辑维度/候选因素/分析工具、逻辑限制、数据质量和硬约束。

上下文禁止包含：物理表名、字段名、JOIN、SQL、数据库连接、原始行、完整值域、Ground Truth、密钥或 Token。

现有 `AnalysisTask` 仍是类型化工具调用。本 Feature 不生成 AnalysisPlan。

## 6. Allowed Files

- `specs/SEM-002_semantic_registry_context_builder.md`
- `app/diagnosis/grounding.py`
- `app/diagnosis/semantics.py`
- `app/diagnosis/__init__.py`
- `app/scripts/evaluate_semantic_grounding_v1.py`
- `data/evaluation/semantic_grounding_golden_v1.json`
- `data/reports/SEM-002_semantic_grounding_evaluation.json`
- `test/diagnosis/test_semantic_grounding.py`
- `test/diagnosis/test_planner_semantic_context.py`
- `test/test_documentation_contract.py`
- `docs/03_metadata_and_nl2sql.md`
- `docs/04_analysis_methodology.md`
- `docs/05_agent_workflow.md`
- `docs/06_evaluation.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/SEM-002_COMPLETION.md`

## 7. Local Plan

1. 定义并校验 Analysis Semantic Registry 与 Planner 上下文 Schema；
2. 实现上下文 Builder 的能力交集、逻辑限制和 Schema 防泄漏；
3. 定义语义候选、检索协议和 Qdrant/ES 生产适配器；
4. 实现确定性优先、检索兜底、歧义/缺失/不支持分类；
5. 增加固定单元测试和版本化功能评测；
6. 更新直接相关文档与状态；
7. 运行验证、Diff Review、完成报告、提交并推送后停止。

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_semantic_grounding.py test/diagnosis/test_planner_semantic_context.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_semantic_grounding_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

外部 Qdrant、Elasticsearch 和 Embedding 在普通单元测试与固定功能评测中使用 Stub/Mock。若执行真实检索 Smoke，必须明确记录为只读外部集成，且不得输出配置或连接信息。

## 9. Acceptance Criteria

- 完整规范问题不调用检索即可返回 `READY`；
- 缺少关键内容返回 `CLARIFICATION_REQUIRED`，不默默猜测；
- 非诊断意图、明确不支持指标或非法产品边界返回 `UNSUPPORTED`；
- Qdrant 只提供 Registry 中存在的指标和允许逻辑维度候选；
- Elasticsearch 只提供允许列的规范地区/品类值；
- 低置信度、多候选和检索故障均失败关闭；
- 检索后仍由现有 Parser 生成规范 `ParsedAnalysisQuestion`；
- Registry 中所有指标引用、维度物理映射和因素指标均能在 Metadata Catalog 校验；
- `PlannerSemanticContext` 只包含当前请求与 Capability 交集，不含物理 Schema；
- Capability 的物理缺失字段不会泄漏到 Planner 上下文；
- Real/Synthetic Capability 差异仍由现有 Capability Assessment 决定；
- 现有 Parser、Capability 和 Planner 回归不变；
- 固定评测记录真实结果，测试与检查结果如实披露；
- 未修改任何数据、数据库、索引、API 或前端。

## 10. Completion Boundary

完成 `SEM-002` 测试、评测、Diff Review、Completion Report、独立提交和推送后停止。未经用户明确授权，不进入 `PLAN-LLM-001` 或 `CLARIFY-001`。
