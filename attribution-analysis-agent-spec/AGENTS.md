# 经营归因分析智能体工程契约

## 1 Project Mission

本仓库的目标是实现一个面向企业经营分析的多轮归因分析系统。系统通过 FastAPI 提供认证、会话、任务、附件、结果和实时通信能力，通过 LangGraph 编排问题定义、数据质量检查、指标拆解、维度下钻、变化贡献计算、证据校验和报告生成。

系统不是一个可以随意执行代码的通用 Agent，也不是只依靠 LLM 生成分析文字的聊天机器人。LLM 负责意图理解、受控规划和解释；指标、SQL、贡献度和证据必须来自可复现的数据和确定性工具。

**当前仓库状态：** 当前内容是设计包。除非对应 Feature Spec 已实现并通过验收，不得将文档中的目标结构、接口、命令或性能指标当作已存在事实。

## 2 Source of Truth

### 2.1 阅读入口

接到任务后，先阅读：

1. 本 `AGENTS.md`。
2. [文档地图](docs/00_document_map.md)。
3. 当前任务对应的 `specs/Fxxx_*.md`。
4. Feature Spec 列出的专题文档、JSON Schema 和前置 Feature。
5. 仓库的实际代码、数据库迁移和测试。

不得只阅读 Feature Spec 而跳过它引用的契约或专题文档。

### 2.2 事实优先级

对同一个事项，使用以下优先级：

1. 已人工批准的当前 Feature 验收条件和明确决策。
2. `contracts/` 中的机器可校验数据契约。
3. `docs/` 中的领域、架构、安全、接口与测试设计。
4. 已通过的测试所表达的现有行为。
5. 实际代码与配置的当前状态。

这个优先级用于发现偏差，不授权静默覆盖。任何两层冲突都必须在实现前报告，确认应修改哪一层，并使文档、契约、测试和代码重新一致。

### 2.3 不得自行推测的事实

以下内容不得由 Coding Agent 凭经验创造：

- 指标口径、统计粒度、时间字段、过滤条件和单位。
- 表、字段、主外键、JOIN 路径和数据权限。
- 用户所属组织、数据范围和敏感字段等级。
- 异常阈值、置信度分数、因果关系和业务建议的执行权限。
- 已通过的测试、线上性能、改进百分比或其他未实测数字。

## 3 Repository Boundaries

以下是目标目录职责。当前目录未存在时，只能在对应 Feature 明确授权后创建。

| 目录 | 可以包含 | 不得包含 |
| --- | --- | --- |
| `app/api/` | Router、请求响应 Schema、认证依赖、HTTP/WS 协议转换 | SQL、指标计算、业务归因规则 |
| `app/services/` | 应用用例、事务边界、任务调度、结果编排 | 连接创建、原始驱动调用、Prompt 细节 |
| `app/agent/` | 可序列化 State、Context 定义、Graph、Node、Route | 无边界递归、直接创建连接池、隐式修改外部系统 |
| `app/tools/` | 封装后且有输入输出 Schema 的查询、计算、检索、文件和导出能力 | 绕过授权的访问、任意 shell、未限流的工具循环 |
| `app/domain/` | 纯领域对象、值对象、枚举和确定性规则 | Web 框架、数据库驱动、LLM SDK |
| `app/repositories/` | 持久化和检索接口，MySQL/Qdrant/ES 实现 | LLM 调用、Prompt、跨系统用例编排 |
| `app/clients/` | 连接池、SDK 客户端、健康检查、重试和关闭 | 领域规则、召回策略、指标口径 |
| `app/prompts/` | 版本化 Prompt 和所需输出 Schema 引用 | 密钥、真实用户数据、不受测试的在线热修 |
| `app/core/` | 配置、安全基础、错误、日志、追踪和应用生命周期 | 特定经营场景的归因逻辑 |
| `contracts/` | JSON Schema 和稳定对外契约 | 实现代码 |
| `specs/` | 单 Feature 目标、边界、验收与测试计划 | 长期领域知识的重复副本 |

依赖方向必须由外向内：`api -> services -> agent/tools -> domain/repository interfaces`。基础设施实现通过 Context 注入，领域层不得反向依赖 API 或具体驱动。

## 4 Architecture Invariants

以下规则是不可破坏的红线。如果当前 Feature 必须违反其中任何一条，先提交架构决策变更，不得直接编码。

### 4.1 State 与依赖

- `AnalysisAgentState` 只保存当前任务的、可 JSON 序列化的动态数据。
- MySQL 连接池、Qdrant/ES 客户端、Repository、LLM Client、文件句柄和 Session 不得进入 State。
- 稳定能力通过 `AnalysisAgentContext` 注入；测试必须能用 fake/stub 替换它们。
- 节点不得依赖隐式全局变量获取当前用户或任务。

### 4.2 LLM 与确定性计算

- LLM 可以理解、拆解问题、选择白名单工具和生成解释，不能自己生成“事实数字”。
- 指标值、变化量、贡献率、排名、同环比和数据质量结果必须来自 SQL 或经测试的计算函数。
- 模型输出必须通过结构化 Schema 校验；校验失败只能在受限次数内重试。
- Prompt 必须版本化，版本号要写入任务记录或追踪属性。

### 4.3 指标、Schema 和检索

- MySQL 中的批准指标与技术元数据是结构化事实源；Qdrant 和 ES 是可重建的检索派生层。
- Qdrant 优先用于指标、表字段和文档的语义召回；ES 优先用于真实枚举值和文本的词法检索。
- 切换 Embedding 模型、向量维度或文本拼接策略时，必须创建新索引版本并运行离线召回评测，不得混用新旧向量。
- 任何指标计算都必须带指标版本、粒度、时间范围、过滤条件和来源快照。

### 4.4 SQL 与工具安全

- 经营数据库使用只读账号；只允许单条 `SELECT` 或经批准的只读 CTE。
- SQL 必须通过 AST/语句类型检查、表字段白名单、权限过滤、超时、最大扫描和最大返回行数限制。
- 用户提供的值使用参数化绑定，不得通过字符串拼接进入 SQL。
- 默认不提供任意命令执行。如必须引入计算型命令工具，只允许白名单命令、隔离工作区、无网络沙箱、资源配额和完整审计。
- 任务取消必须传递到工具执行层，不能只改数据库状态。

### 4.5 证据与结论

- 每个数值性结论都必须引用至少一条 Evidence，Evidence 必须关联数据来源、查询或文件片段、时间范围和指标版本。
- 显示给用户的数字必须能追溯到工具返回的结构化字段，不得只存在于 LLM 文本。
- 贡献度、统计相关和业务一致性证据只能支持诊断性归因；没有 A/B 实验、准实验或明确因果识别时，不得使用“导致”“因为所以”等因果表述。
- `confidence` 必须由可解释的规则计算，或明确标记为待校准的实验字段，不得让 LLM 凭感觉给分。
- 证据不足时输出“待补充数据”，不得用常识补全用户的事实。

### 4.6 任务、会话和实时事件

- 一条用户分析消息对应一个 `analysis_task`；同一会话同一时间最多一个运行中任务。
- 状态只允许按文档中的状态机转移；终态不得回到 `running`。
- 创建任务、保存最终结果和处理重复请求必须幂等。
- WebSocket 事件必须带 `event_id`、`task_id`、`conversation_id`、`seq_no` 和时间；同任务内 `seq_no` 严格递增。
- 多轮上下文通过历史消息、阶段结果和带范围的摘要恢复，不得无限制把全部对话塞入 Prompt。
- 用户、会话、附件、临时文件、任务、结果和推送通道必须同时进行权属校验。

### 4.7 配置、密钥与可替换模型

- LLM 和 Embedding 通过明确的 Provider Protocol/Adapter 接入，领域与 Agent 节点不得导入具体厂商 SDK。
- 模型名称、Base URL、超时、重试、温度和向量维度必须通过配置注入。
- API Key、数据库密码、会话密钥和 OAuth 密钥只能来自环境变量或密钥管理系统，不得写入代码、YAML、测试快照、日志或文档。
- 热更新只允许指定的非敏感、可热更新配置；先校验，后原子替换，失败保留旧配置并写审计日志。

## 5 Single Feature Development Workflow

每一轮开发只执行一个 Feature，固定流程为：

```text
Read -> Inspect -> Local Plan -> Implement -> Test -> Diff Review -> Report -> Stop
```

### 5.1 Read

- 读完本文档、当前 Feature 及其所有引用。
- 列出验收条件、前置 Feature、允许修改的文件和禁止范围。

### 5.2 Inspect

- 检查当前仓库和工作树，保护用户已有修改。
- 确认前置代码、迁移、契约和测试是否真实存在并通过。
- 如前置不成立，报告阻塞，不得顺手实现前置 Feature。

### 5.3 Local Plan

- 根据真实代码状态制定 3 至 7 步局部计划。
- 计划必须将每个代码变更映射到某个验收条件，并列出将执行的测试。
- 不重新设计整个系统，不扩展到下一个 Feature。

### 5.4 Implement

- 优先实现最小可验证变更，同时补充或先写相应测试。
- 不修改与当前 Feature 无关的文件，不做顺手重构，不预先写未来模块。
- 任何公共契约变更必须在同一变更中同步更新 Schema、测试和相关文档。

### 5.5 Test

- 按本文档第 6 节和 Feature 测试计划执行验证。
- 如有必要测试未运行或失败，不得宣称完成。

### 5.6 Diff Review

逐文件检查差异，至少确认：

- 变更全部属于当前 Feature。
- 没有用户密钥、账号、个人数据或真实业务数据泄漏。
- 没有虚构指标、Schema、JOIN 或测试结果。
- 没有破坏本文档的 Architecture Invariants。
- 测试真正观察了行为，没有只为通过而放宽断言。

### 5.7 Report and Stop

按第 8 节固定格式报告，然后停止。未收到新的明确任务时，不得自动开始下一个 Feature，不得自动提交、推送或部署。

## 6 Testing and Validation Rules

### 6.1 基本原则

- 测试重现性优先于方便性；固定随机种子、时区、样例数据和模型温度。
- 单元测试不调用真实 LLM 或公网；使用 fake/stub 并校验输入输出契约。
- 需要 MySQL、Qdrant 或 ES 的集成测试使用独立测试实例和非真实业务数据，每次可重置。
- 契约测试必须用 `contracts/*.schema.json` 校验代表性成功、失败、取消和恢复样本。
- 评测使用版本化 Golden Dataset；禁止为了调优一直修改同一份测试标注而不保留独立验证集。
- 质量门禁看分层指标和失败分类，不用一个模糊的“总分”代替错误分析。

### 6.2 分层验证

| 层次 | 必须覆盖的行为 |
| --- | --- |
| Unit | 领域公式、指标口径校验、贡献度、状态路由、权限决策、路径校验、事件序号 |
| Integration | Client 生命周期、Repository 交互、迁移、索引构建、SQL 只读防护、任务取消、结果事务 |
| Contract | Agent State、Analysis Result、Realtime Event、API 请求与响应 |
| Workflow | 澄清分支、数据异常分支、证据不足分支、成功、失败、取消、超时、最大循环与检查点恢复 |
| Evaluation | Metric Hit@1、Table/Field/Join-key Recall、Value Grounding、SQL Execution Accuracy、证据覆盖、结论忠实性、P95 延迟与安全拦截 |
| End to end | 两个演示场景从登录、建会话、发消息、实时进度到结果导出和继续追问 |

### 6.3 默认命令契约

工程基线 Feature 实现后，应在 `pyproject.toml` 中固化版本和命令。若 Feature 没有更严格规定，最低执行：

```bash
ruff check .
ruff format --check .
mypy app
pytest -q tests/unit
pytest -q tests/contract
```

如修改基础设施或跨层工作流，还必须执行相关 integration/workflow 测试。如修改 Prompt、模型、Embedding、召回、SQL 生成或归因逻辑，还必须执行 Golden Dataset 回归。

当前仓库仅有设计文档时，上述命令只是实施阶段的强制契约，不是已执行或已通过的证明。

## 7 Scope Control

- 一次只接受一个 Feature ID。如请求同时覆盖多个 Feature，先要求拆分或明确优先顺序。
- 只修改 Feature Spec 允许的目录和文件。对公共契约的必要修改须先获得明确批准。
- 不做无关重命名、格式化、依赖升级、代码移动或“顺便修复”。
- 不用 mock 的绿灯代替必要的集成验证，也不在评测代码中针对具体样本写特判。
- 发现未记录决策、不安全默认值或前置缺失时，先停止并报告；不能扩大授权范围来消除阻塞。
- 不创建 Git commit、不推送远程、不部署、不执行生产数据迁移，除非当前用户明确要求。

## 8 Definition of Done and Completion Report

### 8.1 Definition of Done

只有同时满足以下条件，才能声称 Feature 完成：

- Feature 的所有前置条件成立，且每条验收条件都有可查证的证据。
- 实现符合目录边界和全部 Architecture Invariants。
- 数据库迁移、Schema、API、事件、文档和代码保持一致。
- 相关 Unit、Contract、Integration、Workflow 和 Evaluation 测试全部通过。
- lint、format check 和 type check 通过。
- 已检查完整 diff，无无关变更、密钥、真实用户数据、虚构事实或安全倒退。
- 已记录已知限制和未解决问题；任何必要问题未解决时状态为未完成。

### 8.2 完成报告格式

每个 Feature 结束时使用以下结构：

```text
Feature: Fxxx <name>
Status: completed | incomplete | blocked

Changed Files:
- <path>: <why>

Acceptance Criteria:
- AC-xx: pass | fail | not-run - <evidence>

Commands Executed:
- <exact command>

Test Results:
- Unit: <result>
- Contract: <result>
- Integration/Workflow: <result>
- Evaluation: <result>
- Lint/Type: <result>

Added or Changed Dependencies:
- <dependency and reason, or none>

Known Issues and Risks:
- <issue, impact and next action, or none>

Git Diff Review:
- <scope, secrets, contract consistency and invariant review summary>

Next Step:
- Stop and wait for human review.
```

“未运行”、“因环境缺失无法验证”和“测试失败”必须如实报告，不得写成“已完成”或“应该没问题”。

