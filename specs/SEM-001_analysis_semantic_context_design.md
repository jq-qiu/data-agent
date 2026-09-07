# SEM-001 Analysis Semantic Context Design

## 1. Feature

`SEM-001` 冻结经营归因分析的语义绑定、分析语义注册和规划上下文契约，为后续受限的 LLM Planner 提供事实源。本 Feature 只修改设计、计划、状态和文档契约测试，不实现新的运行时代码。

## 2. Source of Truth

按以下优先级执行：

1. 用户当前明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md` 至 `docs/06_evaluation.md`；
5. `specs/META-001_metadata_adaptation.md`、`specs/ANA-002_analysis_question_parser.md`、`specs/ANA-003_capability_assessment.md`、`specs/ANA-004_analysis_planner.md`；
6. `AGENTS.md`；
7. `README.md`；
8. 当前代码行为。

若上述事实源冲突，停止相关实现，不自行创造指标口径、物理字段、维度枚举、分析方法或业务规则。

## 3. Background

当前 V1 已实现：

- Metadata Catalog、指标公式和物理字段映射；
- NL2SQL 的指标、字段和字段值召回；
- 诊断问题的确定性解析、能力评估和确定性规划；
- 结构化 `AnalysisTask`、Controlled Query、确定性 Analyzer、Evidence 和报告。

当前缺少一份明确契约来回答：

- 用户表达如何绑定到规范指标、维度、维度值和时间；
- GMV 等指标允许怎样拆解、下钻和验证候选因素；
- 静态分析知识与当前数据可用能力怎样合并；
- 未来 LLM Planner 可以看到什么、输出什么、不能做什么；
- 规划失败时怎样校验、降级和限制模型调用次数。

## 4. Design Decisions

### 4.1 物理元数据与分析语义分层

物理 Metadata Catalog 继续管理表、列、JOIN、粒度、物理公式和字段值，不复制到规划层。新增设计中的分析语义注册只表达业务含义：

- `MetricAnalysisDefinition`：指标显示名、分析恒等式、可用拆解、可下钻维度和可验证因素；
- `DimensionDefinition`：维度业务含义、值域来源、是否互斥完备和适用分析方法；
- `CandidateFactorDefinition`：候选因素、主要指标、辅助指标、最低 Evidence 条件和限制；
- `AnalysisToolDefinition`：方法名称、参数契约、前置能力、输出类型和任务依赖规则。

分析语义通过规范 ID 引用物理 Metadata Catalog，不能自行定义表、字段、JOIN 或指标计算公式。一个事实源按消费者生成不同投影：NL2SQL 使用物理投影，Planner 使用业务分析投影，Report 使用展示和声明投影。

### 4.2 Planner 前必须完成 Semantic Grounding

`Semantic Grounding`（语义绑定）将用户表达转换为规范业务对象，顺序为：

1. Metric Resolver：指标名称和别名绑定；
2. Dimension Resolver：维度名称和别名绑定；
3. Dimension Value Resolver：维度值绑定；
4. Time Resolver：本期、基期和比较方式绑定；
5. Scope Validator：校验维度值、时间和指标适用范围。

优先使用确定性精确匹配和受控别名；未来如增加检索，只能返回 Registry 中已存在的规范候选，并经过阈值、类型和 Scope 校验。未绑定成功时应返回结构化歧义或不支持结果，不能让 Planner 猜测。

绑定结果沿用 `ParsedAnalysisQuestion`，保存规范指标 ID、时间、比较类型、Scope、请求维度和请求因素，不保存物理 SQL。

### 4.3 静态分析语义与动态运行时能力分离

静态 Registry 描述“理论上允许怎样分析”；`RuntimeCapability` 描述“当前请求的数据实际上能支持什么”，包括：

- 当前期和基期覆盖；
- 可用维度和非空 Evidence；
- 数据质量状态；
- 支持与不支持的方法；
- 缺失证据；
- 是否存在实验或准实验条件。

Planner 只能选择静态 Registry 允许且 `RuntimeCapability` 支持的交集。

### 4.4 PlannerSemanticContext

`PlannerSemanticContext`（规划器语义上下文）是针对单次请求构建的、紧凑、不可变、可序列化的业务分析说明书。它只包含：

- 已绑定的 `ParsedAnalysisQuestion`；
- 目标指标的分析恒等式和允许的拆解关系；
- 已解析 Scope 和规范维度值；
- 当前可用维度、候选因素和分析工具；
- 缺失 Evidence、数据质量和非因果限制；
- 最大任务数、依赖和停止规则。

它明确不包含：

- 物理表名、列名、JOIN、SQL 或数据库连接；
- 原始查询行或完整高基数字段值列表；
- Synthetic Ground Truth 原因标签；
- 密钥、Token、Cookie 或完整连接串。

### 4.5 AnalysisTask 就是类型化工具调用

现有 `AnalysisTask` 已包含 `method` 和白名单参数，是诊断执行链中的类型化工具调用。后续 Planner 继续输出 `AnalysisPlan[AnalysisTask]`，不新增一套重复的通用 `ToolCall` 协议。Tool Dispatcher 按 `method` 路由到受控 Query Builder，Planner 不生成 SQL。

### 4.6 未来采用混合规划策略

`SEM-001` 只冻结策略，不实现 LLM 调用：

- 唯一标准路径：确定性 Planner，规划阶段调用模型 0 次；
- 存在多个合法分析路径：LLM Planner 最多调用 1 次；
- 意图本身存在允许澄清的歧义：整次归因请求最多额外调用 1 次模型，因此总上限为 2 次；
- LLM 输出必须通过 `AnalysisPlanValidator`；
- 输出无效、超时或模型不可用时不自动重试，立即回退确定性 Planner；
- Validator 必须拒绝不支持方法、越权维度、改变指标/时间/Scope、超出任务上限、非法依赖和任何 SQL 字段。

### 4.7 计算、证据和语言边界保持不变

- Query Builder 和 Executor 负责受控数据访问；
- Analyzer 负责确定性数学计算；
- Evidence Checker 负责来源、范围、数字和声明强度校验；
- Report Generator 只消费 Validated Evidence；
- 无实验或准实验设计时，只能输出事实或关联候选，不得使用“导致、造成、证明”等因果表述。

## 5. Target Flow

```text
用户自然语言
  ↓
语义绑定：指标 / 维度 / 维度值 / 时间 / Scope
  ↓
ParsedAnalysisQuestion（规范化分析问题）
  ↓
分析语义 Registry + RuntimeCapability（当前运行时能力）
  ↓
PlannerSemanticContext（单次请求的规划说明书）
  ↓
Planner Policy（确定性优先，必要时一次 LLM 规划）
  ↓
AnalysisPlanValidator（计划校验器）
  ↓ 失败时确定性回退
Validated AnalysisPlan（已校验分析计划）
  ↓
AnalysisTask Tool Dispatcher（类型化工具调度）
  ↓
物理字段映射与 Controlled Query
  ↓
确定性分析 → Evidence 校验 → 证据化报告
```

## 6. In Scope

- 建立本 Feature Spec；
- 冻结语义绑定、分析语义 Registry、运行时能力和 `PlannerSemanticContext` 契约；
- 冻结未来 Planner Policy、Validator、模型调用上限和确定性回退；
- 明确 NL2SQL、Planner 和 Report 的不同元数据投影；
- 明确 Real Olist 与 Synthetic Evidence 的能力差异；
- 更新架构、评测、实施顺序和状态文档；
- 增加文档契约测试，防止后续误写为已实现能力。

## 7. Out of Scope

- 任何 Python、TypeScript、SQL、DDL、配置或 Prompt 运行时实现；
- 调用或接入 LLM Planner；
- 修改现有 Question Parser、Capability Assessment 或 Analysis Planner；
- 修改 AOV、NL2SQL、LangGraph、Controlled Query、Analyzer、Evidence 或 Report 业务逻辑；
- 构建向量索引、字段值索引或数据库对象；
- 多轮会话、登录权限、附件、任务平台或命令执行；
- 价格、退款、配送和严格因果推断。

## 8. Allowed Files

- `specs/SEM-001_analysis_semantic_context_design.md`
- `docs/03_metadata_and_nl2sql.md`
- `docs/04_analysis_methodology.md`
- `docs/05_agent_workflow.md`
- `docs/06_evaluation.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `test/test_documentation_contract.py`
- `docs/reports/SEM-001_COMPLETION.md`

## 9. Local Plan

1. 记录现有文档契约测试基线；
2. 写入本 Spec；
3. 更新四份直接架构文档和 README；
4. 在实施计划和状态中登记分阶段落地顺序；
5. 增加文档契约测试；
6. 执行定向测试、全量测试、Ruff、mypy、链接/敏感模式检查和 `git diff --check`；
7. 审查 diff，填写完成报告并停止。

## 10. Verification

```powershell
.\.venv\Scripts\python.exe -m pytest test/test_documentation_contract.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
```

另外执行 Markdown 本地链接检查和敏感模式检查。敏感模式检查只报告文件路径和问题类型，不输出疑似秘密内容。

## 11. Acceptance Criteria

- 设计文档能回答字段、指标、字段取值、时间和 Scope 如何进入归因分析；
- 物理 Metadata 与分析语义职责清晰，指标公式仍只有一个事实源；
- `PlannerSemanticContext` 的输入、内容和禁止内容明确；
- 静态分析能力与当前数据可用能力分离；
- 当前确定性 Planner 和未来 LLM Planner 的实现状态没有混淆；
- 未来 Planner 的模型调用次数、校验和回退规则明确；
- `AnalysisTask` 继续作为类型化工具调用；
- Real Olist 缺 Evidence 时降级，Synthetic 数据可展示完整链路；
- 未修改运行时代码和既有指标口径；
- 所有实际检查结果如实记录。

## 12. Completion Boundary

完成本 Feature 的文档、测试、Diff Review 和 Completion Report 后停止。未经用户明确授权，不进入 `SEM-002` 或 `PLAN-LLM-001`。
