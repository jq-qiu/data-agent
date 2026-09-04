# Feature Specs 使用说明

## 1 目的

本目录把经营归因分析系统拆成七个顺序 Feature。每个 Feature 是一次独立实现、测试、Review 和回滚单元，不是给 Coding Agent 的模糊“大需求”。实现者必须以 Spec 的验收标准为准，并从 `docs` 中读取业务和架构事实。

## 2 文档事实源

| 要回答的问题 | 首选文档 |
|---|---|
| 系统为什么做、面向谁 | `../README.md`、`../docs/01_product_requirements.md` |
| 组件如何协作、代码如何分层 | `../docs/02_architecture.md` |
| Agent 状态、节点、路由和归因方法 | `../docs/03_agent_workflow.md`、`../docs/04_attribution_methodology.md` |
| 工具和证据如何定义 | `../docs/05_tool_and_evidence_design.md` |
| 表、约束、幂等和取消如何落库 | `../docs/06_data_model.md` |
| HTTP、WebSocket 和事件字段 | `../docs/07_api_and_realtime.md`、`../contracts/realtime-event.schema.json` |
| SQL、文件、命令和配置安全 | `../docs/08_security_and_governance.md` |
| 指标、数据集和发布 Gate | `../docs/09_evaluation_and_testing.md` |
| 实施顺序和验收追踪 | `../docs/10_implementation_plan.md` |
| 环境、发布、监控和恢复 | `../docs/11_deployment_and_operations.md` |

文档冲突时不得凭经验选择。先记录冲突位置、影响和建议决策，由人确认后更新唯一事实源。

## 3 Feature 顺序

| ID | Feature | 核心交付 | 依赖 |
|---|---|---|---|
| F001 | [Foundation](F001_foundation.md) | 工程骨架、配置、数据库、认证边界、日志、CI | 无 |
| F002 | [Conversation Task Runtime](F002_conversation_task_runtime.md) | 会话、消息、附件、任务、取消、实时链路 | F001 |
| F003 | [Context and Metric Layer](F003_context_and_metric_layer.md) | 指标语义、元数据、多轮摘要、热更新 | F002 |
| F004 | [Tool Runtime](F004_tool_runtime.md) | 受控 SQL、文件、检索、命令、产物 | F003 |
| F005 | [Attribution Agent Orchestration](F005_attribution_agent_orchestration.md) | 澄清、计划、工具循环、归因工作流 | F004 |
| F006 | [Evidence and Report](F006_evidence_and_report.md) | 证据账本、六部分结果、导出、摘要回写 | F005 |
| F007 | [Evaluation Gate](F007_evaluation_gate.md) | 两场景 Golden、E2E、安全性能和发布报告 | F006 |

只能在当前 Feature Gate 通过后进入下一项。如果 F005 文件尚未落盘，F006 不得开始实现。

## 4 Spec 状态

每个 Feature 在任务系统或 PR 中标记：

```text
draft → ready → in_progress → in_review → accepted
                     └──────────────▶ blocked
```

- `draft`：仍有影响实现的未决问题。
- `ready`：范围、依赖和验收已明确。
- `in_progress`：一次只允许一位主实现者修改该 Feature 范围。
- `in_review`：实现和必要测试完成，等待人工 Review。
- `accepted`：Gate 通过，可进入下一 Feature。
- `blocked`：前置依赖、环境或业务决策缺失，明确记录解除条件。

## 5 每轮 Coding Agent 工作契约

### 5.1 开始前

1. 读取仓库 `AGENTS.md`、本文件、目标 Spec 和直接引用的 docs。
2. 检查实际代码、迁移、测试和当前 git 状态，不假定文件已存在。
3. 给出 Local Plan，包括：目标、允许修改文件、不会做的事、测试和风险。
4. 发现缺失前置 Feature 时停止并报告，不顺手补做多个 Feature。

### 5.2 实现中

- 遵守架构不变量：Client 管连接生命周期；Repository 管数据访问；Service 管用例；Agent Node 管状态转换；安全策略独立于 Prompt。
- Agent State 只含可序列化动态数据；Client、Repository、连接池、模型和策略对象放运行时 Context。
- 不虚构表、字段、指标、JOIN 和结果，只使用配置、数据库或文档事实。
- 不硬编码密钥、IP、凭据和生产路径。
- 数据模型、接口和事件变更先更新合同和迁移测试。
- 每次只改变一个清晰行为，避免无关重构。

### 5.3 完成前

至少执行目标 Spec 指定的：

```text
format and lint
type check
unit tests
contract tests
required integration tests
feature evaluation or security tests
git diff review
```

某项因环境无法执行时，不得写“通过”，而要报告命令、阻塞原因、已有替代证据和仍需谁完成。

### 5.4 完成报告

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

报告后停止，等待人工 Review。除非人明确要求，不自动提交、不提前进入下一 Feature。

## 6 通用 Definition of Done

Feature 只有同时满足以下条件才可进入 `in_review`：

- 实现没有超出 In Scope，也没有修改无关文件。
- 新增行为有单元测试；跨层行为有集成或合同测试。
- 失败、取消、超时、并发和权限路径均被覆盖，不只测试 Happy Path。
- 新增日志已脱敏，事件不包含隐藏思维链或敏感原始数据。
- 新增配置有类型、默认值、范围、热更新属性和安全分类。
- 接口、Schema、迁移和文档与实现一致。
- 所有必要 Gate 通过，git diff 已人工可读地检查。
- 没有未解释的测试跳过、临时代码、硬编码秘密或虚构业务数据。

## 7 变更管理

- Spec 变更使用决策记录说明原因、备选方案、兼容性和影响 Feature。
- 已 accepted 的上游合同发生破坏性修改时，下游 Feature 状态退回 `blocked`，完成兼容评估后再恢复。
- WebSocket、结果 JSON、指标定义和上下文摘要带显式版本；至少兼容当前和上一版本。
- 发布 Gate 阈值修改必须保留历史、样本数和业务理由，不能为了让失败构建变绿而临时调低。

