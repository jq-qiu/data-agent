# F005 — 经营归因 Agent 编排

## 0. 元信息

| 字段 | 内容 |
|---|---|
| Spec ID | `F005` |
| 状态 | `Draft` |
| 负责人 | Agent/Analysis Backend |
| 必需评审 | Product、Data Governance、Backend、Security |
| 目标版本 | `v0.1` |
| 前置 Feature | `F001 Foundation`、`F002 Conversation and Task Runtime`、`F003 Context and Metric Layer`、`F004 Tool Runtime` |
| 后续 Feature | `F006 Evidence and Report`、`F007 Evaluation Gate` |
| 状态契约 | [`agent-state.schema.json`](../contracts/agent-state.schema.json) |
| 结果契约 | [`analysis-result.schema.json`](../contracts/analysis-result.schema.json) |
| 详细设计 | [`04_agent_workflow.md`](../docs/04_agent_workflow.md)、[`05_attribution_methodology.md`](../docs/05_attribution_methodology.md) |

## 1. 背景与目标

用户希望围绕“为什么销售额下降”“哪些门店贡献了退款增长”等经营问题持续追问。单次 NL2SQL 只能返回数据，不能稳定处理指标口径、基线、数据质量、指标拆解、维度贡献、证据冲突和多轮上下文。

本 Feature 交付一个受控状态工作流：它把 LLM 限定在问题理解、计划建议、假设生成和结果表达环节，把权限、查询、数据质量、贡献计算、证据评分和发布校验交给确定性组件。

### 1.1 成功标准

- 给定固定 State、工具 Stub、配置版本和随机种子，工作流路由及数值结果可复现。
- 所有执行路径在成功、澄清、质量阻断、预算耗尽、取消或失败状态终止，不存在无限循环。
- 每个主要结论可追踪到本任务证据；每个数字可追踪到快照或确定性计算。
- 加法和 Shapley 分解在配置容差内与总体变化对账。
- 无合格因果设计时，结果中不出现 `causal` 结论。
- worker 中断后可从最后一个成功节点继续，已成功工具调用不重复产生副作用或成本。

## 2. 非目标

- 不在本 Feature 中实现认证、会话 CRUD、附件存储、通用 WebSocket 或工具底层执行器。
- 不允许模型自由生成并直接运行 SQL、Shell 命令或任意文件路径。
- 不实现通用预测、自动经营决策或自动执行补货/营销操作。
- 不承诺从观察数据自动发现严格“根因”。默认输出贡献分析和相关线索。
- 不在 State 中保存数据库结果全集或运行时客户端。
- 不允许跨指标版本或不一致粒度进行贡献分解。

## 3. 参与者与权限

| 参与者 | 能力 | 约束 |
|---|---|---|
| 分析用户 | 发起问题、回答澄清、取消、查看阶段和结果 | 仅访问其租户和数据权限范围 |
| 系统管理员 | 配置预算、阈值、模型和功能开关 | 不能借管理页面读取未授权业务明细 |
| Agent Worker | 领取任务、执行状态机、保存检查点 | 使用短期服务身份；不得扩大用户权限 |
| 指标负责人 | 审核指标树、口径和默认基线 | 版本发布后不可原地修改 |
| 数据/业务评审人 | 审核部分或高风险结论 | 人工意见必须形成审计记录 |

## 4. 前置 Gate

F005 开发前必须通过：

1. F002 可原子创建消息与任务，保证同一会话最多一个活动任务，并支持取消和事件顺序。
2. F003 能返回带版本的指标、允许维度、指标树、规范维度成员和多轮上下文。
3. F004 提供结构化、可取消、可审计的只读工具；SQL 工具已经通过 AST、权限、超时和行数限制测试。
4. 至少准备一套小型固定数据：两期 GMV、订单数、客单价、门店和库存证据。
5. State 和结果 Schema 能被项目选定的 Draft 2020-12 校验器加载。

任一 Gate 未通过，不得用 Prompt 临时绕过。

## 5. 不变量

- INV-01：`AgentState` 必须满足 State Schema，且不包含凭据、连接、客户端、可调用对象和大结果集。
- INV-02：任务固定使用启动时的指标版本、配置版本和权限策略版本；恢复时若权限收紧必须重新授权或终止。
- INV-03：指标、当前期、基线、范围未唯一确定前不得执行归因查询。
- INV-04：`data_quality.gate = block` 时不得生成业务原因结论。
- INV-05：LLM 输出的数字在被工具验证前不得登记为观察或证据。
- INV-06：任何 `contributory` 结论都必须引用已对账的 `attribution_run`。
- INV-07：任何 `causal` 结论都必须包含通过规则检查的 `causal_assessment`。
- INV-08：不同 `analysis_view`（如门店和品类）的贡献不得相加。
- INV-09：一条结论至少引用一条本任务且通过硬门槛的证据。
- INV-10：所有循环受次数、工具数、SQL 数、LLM 数、墙钟时间和无进展条件约束。
- INV-11：所有高风险建议仅供人工确认，本 Feature 不执行外部业务动作。
- INV-12：任务终态只允许 `success`、`failed`、`cancelled`；等待澄清使用 `waiting_user`，不占 worker。

## 6. 用户故事与验收标准

### US-01 明确且完整的问题

作为分析用户，我希望系统解释“本月华南 GMV 为什么比上月下降”，并给出可核查贡献与证据。

```gherkin
Given GMV 指标唯一匹配且本月、上月数据完整
And 用户有权访问华南数据
When 用户提交归因问题
Then 系统查询当前期与基线期总体 GMV
And 使用登记的指标树进行指标拆解
And 至少按一个允许维度生成可对账贡献视图
And 最终结果满足 analysis-result.schema.json
And 每个结论引用有效 evidence_id
```

### US-02 信息歧义时澄清

```gherkin
Given 用户只输入“最近销售怎么样”
And “最近”与比较基准均没有组织默认值
When define_problem 完成
Then 任务状态变为 waiting_user
And 系统一次提出不超过 3 个必要问题
And 不执行归因 SQL
When 用户补充指标、时间和基线
Then 系统从检查点恢复并继续原任务
```

### US-03 数据质量阻断

```gherkin
Given 当前期订单数据水位只有预期的 60%
When check_data_quality 执行
Then data_quality.gate 为 block
And 系统不执行业务归因节点
And 结果状态为 data_issue
And 结果说明数据缺口与建议重试时间
```

### US-04 预算耗尽时交付部分结果

```gherkin
Given 已确认总体变化和部分门店贡献
And 所有剩余 SQL 预算已经耗尽
When 工作流判断是否继续
Then 停止原分析循环
And 结果状态为 partial
And method_summary.stopping_reason 为 budget_exhausted
And 未验证假设和缺失数据被披露
```

### US-05 worker 中断恢复

```gherkin
Given query_overview 已成功并保存检查点和工具幂等记录
And worker 在 decompose_metric 前崩溃
When 新 worker 领取同一任务
Then 系统从最后一个成功检查点恢复
And 不重复执行已成功的 overview 查询
And 事件 seq_no 连续且客户端可去重
```

### US-06 多轮追问

```gherkin
Given 上一轮已确认指标为 GMV、当前期为本月、基线为上月、范围为华南
When 用户追问“A 门店具体是哪些商品？”
Then load_context 继承已确认指标、时间、基线和门店范围
And 将本轮候选维度限制为商品或品类
And 输出新的任务、快照、证据和结果引用
```

### US-07 防止因果越级

```gherkin
Given 证据只显示缺货率和销量下降同期发生
And 不存在实验或准实验设计
When synthesize_result 生成“缺货导致销量下降”
Then validate_result 拒绝该 causal 表述
And 最多触发一次受约束措辞修复
And 修复后的 claim_level 不高于 associational
```

### US-08 用户取消

```gherkin
Given 任务处于 running 且正在执行可取消查询
When 用户取消任务
Then Worker 在下一个协作式取消点停止
And 未开始的新工具调用不再执行
And 任务最终状态为 cancelled
And 已保存证据保持审计可见但不发布分析结果
```

## 7. 功能需求

### 7.1 State 与依赖

- FR-01（MUST）：编排器只向检查点存储符合 `agent-state.schema.json` 的 State。
- FR-02（MUST）：Repository、Client、模型、Clock、Policy 和配置对象必须通过 `RuntimeContext` 注入，不得序列化。
- FR-03（MUST）：每个成功节点原子增加 `state_version` 并保存检查点；并发旧版本写入必须失败。
- FR-04（MUST）：任务恢复时重新构造 Runtime Context 并重新校验权限和取消状态。

### 7.2 问题定义与澄清

- FR-05（MUST）：系统必须解析指标、当前期、基线、过滤范围和候选维度。
- FR-06（MUST）：指标多候选分差小于配置阈值、值映射多义或关键时间缺失时必须澄清。
- FR-07（MUST）：一次最多返回 3 个澄清问题，默认最多 2 轮；等待期间释放 worker。
- FR-08（MUST）：采用组织默认基线时，结果的 `defaults_disclosed` 必须为 `true`。

### 7.3 计划与数据质量

- FR-09（MUST）：计划只能使用指标注册表允许的指标路径、维度和 F004 白名单工具。
- FR-10（MUST）：每个计划步骤必须包含稳定 `step_id`、依赖、状态和尝试次数。
- FR-11（MUST）：总体查询前检查新鲜度、完整性、唯一性、口径版本、粒度和当前/基线一致性。
- FR-12（MUST）：质量 `block` 时路由到数据问题结果；质量 `warn` 时继续但写入限制。

### 7.4 变化确认与归因

- FR-13（MUST）：系统计算当前值、基线值、绝对变化和相对变化；基线为零时相对变化为 `null`。
- FR-14（MUST）：变化未达到物质性规则时输出 `no_anomaly`，不得强行生成原因。
- FR-15（MUST）：加法指标使用成员变化量分解并输出残差、容差和 `reconciled`。
- FR-16（MUST）：两因子乘法指标使用精确 Shapley；多因子超过 8 个时允许固定随机种子采样。
- FR-17（MUST）：每个维度形成独立 `analysis_view`；禁止跨视图累加贡献。
- FR-18（SHOULD）：对同方向贡献项达到 80% 覆盖率后停止继续展开长尾，阈值可按指标配置。
- FR-19（MUST）：分解不能对账时不得形成 `contributory` 结论，并记录契约或数据质量错误。

### 7.5 假设与证据

- FR-20（MUST）：每个假设必须包含可观察预期、支持证据、反向证据和缺失数据。
- FR-21（MUST）：证据必须具有来源引用、快照引用、时间、质量硬门槛和规则计算分数。
- FR-22（MUST）：LLM 不得直接写入最终证据分数；评分服务按配置权重计算。
- FR-23（MUST）：假设状态仅允许 `supported/partially_supported/refuted/unresolved` 等契约枚举。
- FR-24（MUST）：无合格因果设计时，结论等级最高为 `contributory` 或 `associational`。

### 7.6 循环、终止与结果

- FR-25（MUST）：分析循环默认最多 3 轮、20 次工具调用、12 次 SQL、8 次 LLM 调用和 300 秒运行时间。
- FR-26（MUST）：连续一轮无新增证据、重复查询、全部假设不可验证或预算耗尽时必须停止。
- FR-27（MUST）：部分完成属于成功交付，使用 `result_status=partial` 并披露停止原因；系统故障才使用 `failed`。
- FR-28（MUST）：最终结构化结果必须满足 `analysis-result.schema.json`，并通过引用、数字、单位、对账、权限和结论等级校验。
- FR-29（MUST）：可修复的结构/措辞问题最多返回综合节点 1 次；数值与权限问题不可由模型修复绕过。
- FR-30（MUST）：持久化与发布必须幂等，同一任务只能有一个有效最终结果版本。

### 7.7 事件与审计

- FR-31（MUST）：每个节点状态变化和工具开始/完成都发布带 `task_id`、`seq_no`、时间和 `trace_id` 的事件。
- FR-32（MUST）：事件、State 和普通日志不得包含密钥、连接串、未脱敏明细或完整模型 Prompt。
- FR-33（MUST）：必须审计指标版本、配置版本、权限策略版本、工具调用、快照和停止原因。

## 8. 工作流

### 8.1 节点顺序

```text
accept_task
  → load_context
  → define_problem
  → request_clarification? ── waiting_user ──┐
  → resolve_metric_and_baseline              │
  → authorize_and_plan                       │
  → check_data_quality                       │
      ├─ block → produce_data_issue_result   │
      └─ pass/warn                           │
  → query_overview                           │
      ├─ no material change → no_anomaly     │
      └─ material change                     │
  → decompose_metric                         │
  → drill_down_dimensions                    │
  → form_and_test_hypotheses                 │
  → assess_evidence                          │
      ├─ progress + budget → loop             │
      └─ sufficient/no data/budget → synthesize
  → validate_result
      ├─ repairable once → synthesize
      ├─ invalid → failed
      └─ valid → persist_and_publish → success
```

具体节点输入、输出和失败策略以 [`04_agent_workflow.md`](../docs/04_agent_workflow.md) 为准。

### 8.2 路由真值表

| 条件 | 优先级 | 目标 |
|---|---:|---|
| `cancel_requested = true` | 1 | `cancelled` |
| 权限拒绝 | 2 | `failed(policy_denied)` |
| 关键问题未确定且仍可澄清 | 3 | `waiting_user` |
| 澄清轮数耗尽 | 4 | `partial(missing_data)` |
| `data_quality.gate = block` | 5 | `data_issue` |
| 变化未达到物质性阈值 | 6 | `no_anomaly` |
| 证据充分 | 7 | `synthesize_result` |
| 任一预算耗尽 | 8 | `partial(budget_exhausted)` |
| 本轮无新增证据 | 9 | `partial(no_progress)` |
| 有进展且有预算 | 10 | 下一轮下钻/验证 |

路由由代码按固定优先级执行，模型不能返回任意下一节点。

## 9. 配置

```yaml
agent:
  max_analysis_iterations: 3
  max_tool_calls: 20
  max_sql_queries: 12
  max_llm_calls: 8
  max_wall_time_seconds: 300
  max_clarification_rounds: 2
  max_validation_repairs: 1
  min_new_evidence_per_iteration: 1

attribution:
  max_exact_shapley_factors: 8
  sampled_shapley_permutations: 1000
  random_seed: 20260904
  top_n: 5
  target_directional_coverage: 0.80
  reconciliation_abs_tolerance: 0.01
  reconciliation_relative_tolerance: 0.0001

evidence:
  min_primary_score: 0.65
  source_quality_weight: 0.25
  relevance_weight: 0.20
  temporal_alignment_weight: 0.15
  magnitude_weight: 0.15
  consistency_weight: 0.15
  corroboration_weight: 0.10
```

配置发布需要 Schema 校验、权重和为 1、候选快照和原子切换。任务启动后固定配置版本。

## 10. State、Context 与节点接口

```python
class Node(Protocol):
    async def run(
        self,
        state: AgentState,
        context: RuntimeContext,
    ) -> NodeOutcome: ...

@dataclass(frozen=True)
class NodeOutcome:
    patch: dict[str, Any]
    route: Route
    events: tuple[DomainEvent, ...]
```

实现规则：

- State 输入视为不可变；节点返回最小 patch。
- patch 合并后先过 JSON Schema，再保存检查点。
- Context 包含指标注册表、查询服务、归因引擎、证据库、策略引擎、模型、事件发布器和 Clock。
- 测试时全部 Context 依赖可替换为 Stub/Fake。
- 节点不得读取未声明的进程全局配置。

## 11. 工具使用规则

| 工具 | 最大单次超时 | 瞬时错误重试 | 关键限制 |
|---|---:|---:|---|
| `resolve_metric` | 5s | 1 | 候选与分数必须可审计 |
| `resolve_dimension_value` | 5s | 1 | 多义时不得静默选择 |
| `query_metric` | 30s | 2 | 只读、参数化、租户过滤、行数限制 |
| `check_data_quality` | 20s | 1 | 规则结果不得由模型覆盖 |
| `decompose_additive` | 10s | 0 | 必须输出残差和对账标识 |
| `decompose_product_shapley` | 20s | 0 | 固定算法版本和随机种子 |
| `search_attachment` | 10s | 1 | 只访问会话授权附件和安全片段 |
| `register_evidence` | 5s | 1 | 内容哈希去重 |

`idempotency_key = task_id + step_id + attempt`。成功输出保存 `output_ref` 后，恢复流程先查幂等记录，不重复调用。

## 12. 结构化结果规则

最终输出包含：

1. `problem_definition`：指标、时间、基线、范围和默认值披露；
2. `key_metrics`：当前值、基线值、差值、变化率、单位和快照；
3. `attribution_views`：每个指标路径/维度的独立贡献与对账；
4. `evidence_list`：来源、时间、质量评分和快照；
5. `conclusions`：结论等级、假设状态、支持/反向证据与限制；
6. `missing_data`：缺失项、影响和建议来源；
7. `next_actions`：至少 2 条，包含负责人角色、成功指标和人工审批标记；
8. `limitations/method_summary/lineage`：方法、停止原因、配置和内容哈希。

报告 Markdown/PDF 由 F006 从结构化对象渲染。不得另行让模型生成包含新数字的自由文本报告。

## 13. 安全与治理

- 任务权限是调用用户权限的交集，不因 Agent 服务账号而扩大。
- QuerySpec 编译器强制授权表、列、行级过滤和聚合最小粒度。
- 附件文本和数据库值均视为不可信数据，不得把其中指令提升为系统指令。
- 仅允许 AST 验证后的单条只读 `SELECT/CTE`；禁止 DDL/DML、多语句、注释绕过和系统库访问。
- State、事件和普通日志采用 ID/摘要引用；原始结果进入受控快照存储。
- 结论中的小样本和敏感切片按阈值抑制或聚合为“其他”。
- 任务取消、权限拒绝、因果升级和质量 gate 均进入审计日志。

## 14. 可观测性与 SLO

记录：

- 每节点 P50/P95 耗时、进入/退出计数和失败率；
- 每工具成功率、重试、取消、超时、缓存命中和查询成本；
- 每任务循环数、SQL/LLM 次数、Token、墙钟时间和停止原因；
- 数据质量 gate、贡献对账失败率、证据覆盖率和因果越级拦截数；
- 恢复次数、重复工具调用数（目标为 0）和事件缺口数。

开发验收目标：固定小型数据集单任务 P95 小于 30 秒（不含真实外部 LLM/数据源网络），工作流终止率 100%，对账正确率 100%，Schema 合格率 100%。生产 SLO 由真实基线压测后另行冻结，不得把开发目标当作实测结果。

## 15. 测试计划

### 15.1 单元测试

| 测试 ID | 覆盖 | 断言 |
|---|---|---|
| F005-U01 | FR-01～04 | State 可序列化；Context 对象无法进入 Schema；乐观锁生效 |
| F005-U02 | FR-05～08 | 歧义路由澄清；默认基线披露；轮数上限生效 |
| F005-U03 | FR-11～12 | `pass/warn/block` 路由正确 |
| F005-U04 | FR-13～14 | 基线零值与无实质变化正确处理 |
| F005-U05 | FR-15 | 加法含增长抵消项仍精确对账 |
| F005-U06 | FR-16 | 两因子示例贡献为 `-10250/+4750`，合计 `-5500` |
| F005-U07 | FR-17～19 | 跨视图不相加；残差超限阻断贡献结论 |
| F005-U08 | FR-20～24 | 硬门槛、评分、反向证据和因果降级正确 |
| F005-U09 | FR-25～29 | 每种停止条件和一次修复限制正确 |
| F005-U10 | FR-31～33 | seq_no、脱敏字段和审计字段正确 |

### 15.2 集成测试

1. `metric registry fake + tool runtime fake + checkpoint DB` 跑通正常路径。
2. 在每个节点后注入崩溃，验证恢复结果与不中断结果相同。
3. 工具超时、瞬时错误、永久错误、取消分别验证重试和终态。
4. 两个 worker 同时领取任务，仅一个可提交新 State 版本。
5. WebSocket 断开重连后按 `seq_no` 补齐事件，无重复 UI 消息。
6. 权限在检查点后收紧，恢复任务不得继续读取原范围。

### 15.3 场景验收

**场景 A：库存关联的 GMV 下降**

- 基线：1,000 单 × 100 元 = 100,000 元；
- 当前：900 单 × 105 元 = 94,500 元；
- 预期：总体 `-5,500`；订单数贡献 `-10,250`，客单价贡献 `+4,750`；
- 门店下钻与总体对账；库存证据只允许形成相关结论，无实验时不得输出因果。

**场景 B：退款增长**

- 退款金额按退款原因做加法贡献；
- 当前与基线均包含撤销退款的统一过滤；
- 一个品类贡献主要增长，另一个品类抵消部分增长；
- 缺少客服记录时输出 `partial`，并把记录列为待补充数据。

## 16. 需求追踪

| 能力 | 需求 | 主要测试 |
|---|---|---|
| State/恢复 | FR-01～04 | U01、集成 2/4/6 |
| 问题与澄清 | FR-05～08 | U02、US-02/06 |
| 计划与质量 | FR-09～12 | U03、US-03 |
| 归因算法 | FR-13～19 | U04～U07、场景 A/B |
| 证据与分级 | FR-20～24 | U08、US-07 |
| 循环与输出 | FR-25～30 | U09、US-04/05/08 |
| 事件与审计 | FR-31～33 | U10、集成 5 |

## 17. 发布与回滚

1. 在 Feature Flag `attribution_agent_v1` 下发布，仅对测试租户开放。
2. 使用固定 Golden Dataset 做影子运行，不向用户展示结论。
3. 对比人工标准的指标、基线、贡献、证据引用和结论等级。
4. 通过 F007 Gate 后灰度 5%/20%/50%/100%，每阶段观察至少一个完整业务周期。
5. 任一阻断条件触发则关闭 Flag，旧的问数功能继续可用；已生成结果保留算法与 Schema 版本以供审计。

回滚阈值至少包括：权限越界事件大于 0、危险 SQL 放行大于 0、数字/贡献对账失败大于 0、Schema 失败率大于 0.1%、任务非终止率大于 0。

## 18. 风险与待决策

| ID | 风险/决策 | 处理 |
|---|---|---|
| R1 | 指标树不完整导致只能做维度观察 | 优先补齐核心指标；结果降级并披露 |
| R2 | 当前期数据尚未闭合 | 质量 gate 阻断或使用对齐进度基线 |
| R3 | 多维度重叠导致重复解释 | 独立 `analysis_view`，禁止跨视图相加 |
| R4 | 模型倾向使用因果措辞 | 契约等级 + 规则校验 + 红队集 |
| R5 | Shapley 多因子成本高 | 8 因子以内精确，以上固定种子采样 |
| R6 | 证据评分权重缺少业务标定 | 初值仅为开发默认；用 Golden Dataset 校准并版本化 |
| D1 | 是否需要人工审核高影响结论 | 产品/治理评审决定阈值；接口预留 `review_status` 在 F006 落地 |

## 19. Definition of Done

- [ ] 前置 Gate 全部有可复核证据。
- [ ] State/Result 两份 Draft 2020-12 Schema 可加载，正常和反例 fixture 均通过预期断言。
- [ ] FR-01～FR-33 均映射到测试且全部通过。
- [ ] 正常、澄清、质量阻断、无异常、部分结果、取消、恢复和失败路径全部终止。
- [ ] 加法、两因子 Shapley、零基线、比率零分母和跨维度防重测试通过。
- [ ] 无证据数字、无引用结论和无设计因果陈述均被拒绝。
- [ ] 工具权限、超时、重试、幂等、取消、脱敏和审计通过安全评审。
- [ ] 两个业务场景可使用固定 Stub 数据完整演示，并保存 State、事件、证据和结果。
- [ ] 运行手册、仪表盘、Feature Flag 和回滚步骤可用。
- [ ] Spec 评审通过并将状态更新为 `Approved` 后方可进入正式实现。
