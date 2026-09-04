# 经营归因分析智能体设计包

## 当前状态

这是一个面向后续开发的 **Spec-driven 设计包**，不是已实现、已部署或已通过验收的应用。目录中的文档、JSON Schema 和 Feature Spec 用于在写代码之前固化需求、边界、数据契约、测试方法和实施顺序。

未来的代码目标是构建一个面向企业经营分析的多轮归因分析系统：用户围绕一个业务异常持续追问，系统根据统一指标口径查询数据，先检查数据质量，再做指标拆解、维度下钻和变化贡献计算，最后生成可追溯的阶段性结论和最终报告。

## 系统要解决的问题

传统 BI 看板擅长展示“发生了什么”，NL2SQL 擅长把自然语言转成查询。本系统将两者向前延伸，为“为什么发生”提供受控的诊断链路：

```text
自然语言问题
    -> 明确指标、范围、时间和对比基准
    -> 验证异常与数据完整性
    -> 指标拆解和维度下钻
    -> 计算变化量与贡献度
    -> 补充库存、促销、退款等证据
    -> 校验数字、口径和证据一致性
    -> 输出结论、不确定性和建议
```

大模型负责理解、规划、选择工具和表达；SQL、统计方法和受控工具负责确定性计算。没有实验或因果识别时，系统只能输出“变化贡献”或“相关证据”，不得把它表述为已证明的因果关系。

## 目标技术架构

| 层次 | 预定技术 | 主要职责 |
| --- | --- | --- |
| API 与实时通信 | FastAPI，REST，WebSocket | 认证接入、会话、任务、附件、结果和实时事件 |
| 智能体编排 | LangGraph | 可检查状态、条件路由、工具循环、中断恢复和轮次限制 |
| 业务与任务数据 | MySQL | 用户、会话、任务、结果、指标定义、元数据和审计记录 |
| 语义检索 | Qdrant | 指标、表、字段、分析方法和文档切片的向量召回 |
| 词法与枚举值检索 | Elasticsearch | 地区、商品、会员等真实字段值的精确或模糊匹配 |
| 模型接入 | 可替换 Provider Adapter | LLM 与 Embedding 通过配置切换，业务代码不依赖具体厂商 |
| 文件存储 | 本地目录或对象存储适配器 | 附件、临时工作区、导出报告，按用户与会话隔离 |

整体分为三个面：控制面管理会话和任务，分析面编排归因过程，数据与知识面提供统一指标、查询和证据能力。详细分层见 [架构设计](docs/02_architecture.md)。

## 文档导航

第一次阅读建议按以下顺序：

1. [产品需求](docs/01_product_requirements.md)：定义用户、业务闭环、功能范围与验收条件。
2. [架构设计](docs/02_architecture.md)：定义系统边界、组件、依赖方向和运行链路。
3. [领域与指标模型](docs/03_domain_and_metric_model.md)：定义指标、维度、基准期、证据和结论语义。
4. [智能体工作流](docs/04_agent_workflow.md)：定义 LangGraph 状态、节点、路由、重试和停止条件。
5. [归因方法](docs/05_attribution_methodology.md)：定义指标拆解、贡献度、维度下钻和因果语义边界。
6. [数据模型](docs/06_data_model.md)、[API 与实时协议](docs/07_api_and_realtime.md)：定义持久化和对外契约。
7. [安全与治理](docs/08_security_and_governance.md)、[评测与测试](docs/09_evaluation_and_testing.md)：定义上线门槛。
8. [实施计划](docs/10_implementation_plan.md)、[部署与运维](docs/11_deployment_and_operations.md)：定义交付顺序和运行要求。

完整索引、阅读路线和文档修改规则见 [文档地图](docs/00_document_map.md)。

## 机器可校验契约

| 契约 | 用途 |
| --- | --- |
| [Agent State Schema](contracts/agent-state.schema.json) | 限制 LangGraph State 只保存当前任务的可序列化动态数据 |
| [Analysis Result Schema](contracts/analysis-result.schema.json) | 校验问题定义、指标、证据、结论、待补数据和建议 |
| [Realtime Event Schema](contracts/realtime-event.schema.json) | 校验 WebSocket 事件类型、顺序字段和任务关联字段 |

合同与专题文档冲突时，不能静默选一个实现；必须先修正对应 Spec 和契约，再修改代码。

## Feature Spec 导航

`specs/` 将工程分成可独立实现、测试、Review 和回滚的小闭环：

- [Feature 使用说明](specs/README.md)
- [Feature 模板](specs/FEATURE_TEMPLATE.md)
- [F001 工程基线](specs/F001_foundation.md)
- [F002 持久化与配置](specs/F002_persistence_and_config.md)
- [F003 会话任务与实时通信](specs/F003_conversation_task_realtime.md)
- [F004 元数据与检索](specs/F004_metadata_and_retrieval.md)
- [F005 归因工作流](specs/F005_attribution_workflow.md)
- [F006 结果附件与导出](specs/F006_result_attachment_export.md)
- [F007 评测门禁](specs/F007_evaluation_gate.md)

每一次开发只选一个 Feature，并按 [AGENTS.md](AGENTS.md) 规定的 `Read -> Inspect -> Local Plan -> Implement -> Test -> Diff Review -> Report -> Stop` 闭环执行。

## 预期仓库结构

以下是实施阶段的目标结构，不表示这些代码已存在：

```text
attribution-analysis-agent/
|-- app/
|   |-- api/                 # HTTP/WebSocket 边界和 Schema
|   |-- services/            # 应用用例与事务编排
|   |-- agent/               # State、Context、Graph、Node 和 Route
|   |-- tools/               # 受控的查询、计算、检索和导出工具
|   |-- domain/              # 纯领域模型与规则
|   |-- repositories/        # 持久化与检索接口及实现
|   |-- clients/             # MySQL、Qdrant、ES、LLM 等连接生命周期
|   |-- prompts/             # 经评测与版本化的 Prompt
|   `-- core/                # 配置、日志、安全、错误和可观测性
|-- migrations/              # 数据库迁移
|-- tests/                   # unit、integration、contract、evaluation
|-- evals/                   # Golden Dataset 和评测脚本
|-- docs/                    # 长期有效的架构与专题设计
|-- contracts/               # JSON Schema 与对外契约
|-- specs/                   # 单 Feature 执行规格
`-- AGENTS.md                # Coding Agent 的仓库级工作契约
```

## 开发与验收方法

设计包采用以下阶段门禁：

1. **契约门禁**：需求 ID、数据 Schema、状态机和接口语义无冲突。
2. **基础设施门禁**：MySQL、Qdrant、ES、模型适配器和文件存储完成健康检查与集成测试。
3. **离线知识门禁**：指标、表字段、JOIN 关系和字段值索引通过固定样本验证，才进入 Agent 实现。
4. **工作流门禁**：每个节点有单元测试，分支路由、重试、取消、恢复和上限有集成测试。
5. **评测门禁**：固定 Golden Dataset，分层检查检索、SQL、归因、忠实性、延迟和安全，通过错误分析定向迭代。

在代码实现之前，本设计包不提供有效的启动命令，也不声称任何测试结果或性能数据。

## 首期交付边界

首期建议选择“库存异常分析”和“市场表现分析”两个演示场景，因为它们能覆盖销售、订单、库存、渠道和促销等常见数据。首期包含：

- 授权登录、会话和单会话单运行任务。
- 附件上传、解析状态、隔离存储和可追溯下载。
- 指标查询、数据质量检查、对比、拆解、下钻、贡献度和证据组装。
- 实时事件、任务取消、结果保存、六部分结构化输出和 Markdown 导出。
- 固定样本数据、完整演示链路和可重复评测。

首期不包含自动执行补货、调价或营销操作，不包含对任意系统命令的无限制执行，也不将贡献度分析宣称为严格因果推断。

## 如何使用这个设计包

### 人工评审

1. 先确认产品需求中的 MVP 范围、两个演示场景和验收数值。
2. 再评审指标模型、归因方法和 Agent 工作流，确认哪些结论可计算、哪些只能表述为相关。
3. 检查 JSON Schema、数据表和 API 的字段对应。
4. 对每个 Feature Spec 单独确认前置条件和验收条件。
5. 在评审通过后，才开始 F001；不要一次把所有模块交给 Coding Agent 生成。

### Coding Agent

Coding Agent 首先必须完整读取 [AGENTS.md](AGENTS.md)，再读取当前 Feature 指定的 Source of Truth。发现代码与文档不一致时，应停止并报告，不得用自己的假设补全指标口径、Schema、JOIN 关系或安全规则。

