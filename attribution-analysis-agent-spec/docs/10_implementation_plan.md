# 分阶段实施计划

## 1 实施原则

项目采用 Spec Driven Coding。README 说明如何运行，AGENTS 规定仓库级工程约束，docs 是架构和业务事实源，specs 将系统拆成可独立验收的 Feature。每轮只实现一个 Feature，流程固定为：

```text
Read → Inspect → Local Plan → Implement → Test → Diff Review → Report → Stop
```

每个 Feature 必须形成一个可运行、可测试、可回滚的闭环。下游 Feature 不得绕过前置 Gate；发现前置能力不足时，先回到对应 Spec 修复并复验。

## 2 Feature 依赖图

```text
F001 Foundation
   ↓
F002 Conversation and Task Runtime
   ↓
F003 Context and Metric Layer
   ↓
F004 Tool Runtime
   ↓
F005 Attribution Agent Orchestration
   ↓
F006 Evidence and Report
   ↓
F007 Evaluation Gate
```

F002 建立可靠的会话、任务和实时链路；F003 提供稳定业务口径；F004 提供受控确定性工具；F005 才允许模型进行规划；F006 在证据校验后发布结果；F007 用固定数据集决定是否可演示或发布。

## 3 里程碑概览

下表以一个小型团队的相对周期为参考，不是硬性承诺。实际排期应按人员、认证中心和数据源准备情况重新估算。

| 阶段 | 参考周期 | 可演示成果 | Gate |
|---|---:|---|---|
| 规格冻结与样例准备 | 2 至 3 天 | 文档地图、事件 Schema、两套样例数据定义 | 关键歧义均有决策记录 |
| F001 | 3 至 5 天 | 服务启动、迁移、登录 Stub、健康检查 | Foundation Gate |
| F002 | 5 至 8 天 | 登录后创建会话、上传、发送、实时状态、取消与历史回放 | Runtime Gate |
| F003 | 5 至 8 天 | 指标语义、上下文拼装、多轮摘要、配置热更新 | Context Gate |
| F004 | 7 至 10 天 | 受控 SQL、文件、检索、命令和结果文件工具 | Tool Security Gate |
| F005 | 7 至 12 天 | 澄清、规划、数据质量、拆解、下钻和检查点恢复 | Agent Gate |
| F006 | 4 至 7 天 | 六部分结果、证据引用、报告导出 | Evidence Gate |
| F007 | 5 至 8 天 | 两场景 E2E、Golden 报告、安全与性能结果 | Release Gate |

## 4 F001 Foundation

**目标：**建立后续 Feature 可以依赖的工程骨架，而不是提前实现业务 Agent。

主要任务：

1. 建立前端、API、Worker、领域、Repository、Client、迁移和测试目录。
2. 实现类型化配置、环境隔离、密钥引用、日志脱敏、trace/request ID。
3. 建立 MySQL 连接、迁移框架、事务辅助和健康检查。
4. 接入认证中心的接口边界；开发环境提供可替换认证 Stub。
5. 建立 CI：lint、format、type check、unit test、secret scan。
6. 提供开发 Compose、示例环境变量和最小启动文档。

完成证据：空库可迁移和回滚；服务 `/health/live` 与 `/health/ready` 正确；配置缺失时快速失败且不打印密钥；认证 Stub 可建立当前用户。

## 5 F002 Conversation and Task Runtime

**目标：**不依赖真实 LLM 即可完整演示会话、消息、附件、任务状态和实时事件。

主要任务：

1. 实现 `users/conversations/messages/attachments/analysis_tasks/websocket_tokens/task_logs` 模型与 Repository。
2. 实现会话 CRUD、历史消息、附件上传下载删除。
3. 将“用户消息 + 分配 seq_no + 创建任务”放入单事务，增加幂等键。
4. 用数据库活动槽唯一约束实现同会话至多一个活动任务。
5. 实现任务状态机、协作式取消、Worker 领取和丢失任务恢复。
6. 实现短时单次 WebSocket token、事件信封、顺序、重放和 HTTP 快照恢复。
7. 前端实现会话列表、聊天区、附件栏和实时任务区的最小闭环。

完成证据：并发测试、幂等重试、取消 queued/running、断线恢复、越权和事件 Schema 合同全部通过。

## 6 F003 Context and Metric Layer

**目标：**给 Agent 提供可版本化的业务语义和多轮上下文，禁止模型凭空创造指标、表、字段和 JOIN。

主要任务：

1. 定义 `ProblemDefinition`、`MetricDefinition`、`DimensionDefinition`、`EvidenceRef` 和 `AnalysisContext`。
2. 建立指标注册表：公式、聚合方式、粒度、默认时间字段、过滤条件、同义词、负责人和版本。
3. 读取数仓技术元数据和显式 JOIN 关系，构建允许查询的语义层。
4. 实现指标、表、字段、连接键和字段值检索；提供精确匹配、词法和向量融合接口。
5. 实现对话窗口和 `context_summaries`，保留已确认口径、范围、证据引用和待决问题。
6. 实现配置候选快照校验、原子热更新和任务版本固定。
7. 建立离线召回数据集和分层指标。

完成证据：同义改写、歧义澄清、多轮约束继承、摘要区间、指标版本、热更新一致性和召回 Gate 通过。

## 7 F004 Tool Runtime

**目标：**在 Agent 之前交付可单独测试的确定性工具，模型只能调用经过策略网关授权的高层能力。

主要任务：

1. 统一工具协议：输入 Schema、输出 Schema、权限需求、超时、重试、取消、审计和错误码。
2. SQL 工具实现 AST 白名单、授权 Schema、参数化、EXPLAIN、成本限制、只读执行、结果脱敏。
3. 文件工具实现会话根目录、路径规范化、上传解析隔离和安全导出。
4. 文本检索工具返回来源片段、位置和置信度，不返回无法追溯的自由文本。
5. 命令工具默认关闭；启用时只提供登记的工具 ID、参数数组和沙箱。
6. 建立模型无关的工具测试 CLI，允许直接输入 fixture 验证。
7. 实现工具取消令牌、资源配额、审计和产物哈希。

完成证据：每个工具的成功、失败、超时、取消和安全拒绝均可重复；红队高危用例放行数为 0。

## 8 F005 Attribution Agent Orchestration

**目标：**把问题理解、澄清、数据质量检查、分析计划、工具调用、证据判断和归因计算组织为有限状态工作流。

建议节点：

```text
load_context
  → define_problem
  → clarify_or_continue
  → data_quality_check
  → build_hypotheses_and_plan
  → execute_tool
  → assess_evidence
  → metric_decomposition
  → dimension_contribution
  → validate_analysis
  → finalize_or_continue
```

主要约束：State 只保存本任务的可序列化动态数据；Client、Repository 和策略对象放 Context。设置最大迭代、最大工具调用、预算和停止原因。数据缺失时列明缺口，数据质量异常时优先报告，不强行生成业务归因。

完成证据：模型 Stub 路由单测、两套小型场景、检查点恢复、多轮追问、最大迭代和错误路径通过。

## 9 F006 Evidence and Report

**目标：**让结论可追溯、数字可核验、报告可下载。

主要任务：

1. 建立证据账本，每条证据包含来源、工具运行、时间、指标、口径版本、摘要和校验哈希。
2. 实现指标拆解和同粒度维度贡献对账。
3. 实现数字一致性、引用覆盖、相关性与因果表达校验。
4. 生成问题定义、关键指标、证据列表、归因结论、待补充数据、下一步建议六部分结构化结果。
5. 在一个事务中保存结果、最终助手消息并将任务置为 success。
6. 导出 Markdown，按需要扩展 DOCX/PDF；文件鉴权下载并记录审计。
7. 生成新的上下文摘要，供下一轮继续追问。

完成证据：六部分 Schema、数字一致 100%、贡献对账、导出一致性、失败不发布和下载权限测试通过。

## 10 F007 Evaluation Gate

**目标：**把“能跑”升级为“有证据地知道在哪些场景可靠”。

主要任务：

1. 固定库存异常与退款模式两套种子数据和 Golden 对话。
2. 建立问题理解、检索、SQL、证据、归因、报告、安全和性能评测器。
3. 运行基线，按错误分类定位主要瓶颈。
4. 每次只修改一个假设，并做基线对比与全量回归。
5. 建立 CI 快速集、夜间全量集和发布前安全性能集。
6. 产出可复现实验报告，不把目标阈值写成实测结果。

完成证据：评测文档中的所有硬 Gate 通过，并由业务和数据开发各至少一人复核代表性结果。

## 11 横向工作流

### 11.1 每个 Feature 开始前

- 读取 `AGENTS.md`、文档地图、当前 Feature Spec 和直接依赖。
- 检查仓库实际状态、现有测试和未提交变更。
- 列出本轮允许修改文件、验收标准和验证命令。
- 如果 Spec 与代码冲突，先记录决策，不自行扩大范围。

### 11.2 实现中

- 数据库变化先迁移和 Repository 测试，再应用服务和接口。
- 先写失败测试或最小可观察验收，再实现。
- 外部依赖通过接口和 Stub 隔离，单元测试不访问真实模型。
- 安全校验位于工具运行时，不能只写在 Prompt 中。
- 每个状态变化、工具调用和配置版本均可追踪。

### 11.3 完成报告

每次报告包含：

```text
Changed Files
Added Dependencies
Commands Executed
Unit Test Results
Integration Test Results
Evaluation Results
Known Issues
Acceptance Criteria
Git Diff Review Summary
```

必要测试失败时不能声明完成。报告后停止，等待人工 Review，再决定提交与进入下一 Feature。

## 12 验收追踪矩阵

| 用户验收需求 | 负责 Feature | 自动化证据 |
|---|---|---|
| 授权登录进入工作台 | F001、F002 | 认证集成和浏览器 E2E |
| 创建、改名、删除、切换会话 | F002 | API、权限、级联清理测试 |
| 上传、解析、删除和下载附件 | F002、F004 | 类型、路径、权限和解析测试 |
| 发送消息并查看实时过程 | F002、F005 | WebSocket 合同、顺序和 E2E |
| 取消分析和历史回放 | F002 | 状态机、取消、重连和快照测试 |
| 六部分结构化输出 | F006 | 结果 Schema 与内容校验 |
| 导出并重新下载 | F006 | 产物一致性与鉴权测试 |
| 配置重载即时生效 | F003 | 快照原子性与版本固定测试 |
| 至少两个完整业务场景 | F007 | Golden E2E 报告 |

## 13 风险与前置条件

| 风险 | 早期验证 | 缓解 |
|---|---|---|
| 认证中心接口未准备 | F001 使用契约 Stub | 尽早做 staging 联调，不让业务开发被阻塞 |
| 企业指标口径不统一 | F003 先选两个场景开评审 | 指标注册表带负责人和版本，争议不交给模型决定 |
| 数据源权限过大 | F004 前创建只读账号 | Schema/列白名单、审计和脱敏 |
| Agent 调试不可复现 | 模型 Stub 和固定配置 | 每次任务记录版本、种子或可用参数和工具轨迹 |
| 实时连接跨实例丢事件 | F002 先做持久游标 | Pub/Sub 只负责实时分发，HTTP/事件记录负责恢复 |
| 模型费用和延迟失控 | 每 Feature 记录预算 | 最大迭代、Token、工具次数、缓存和小模型路由 |
| 演示数据过于简单 | F007 加陷阱和无答案样本 | 按风险标签分桶，保留盲测集 |

