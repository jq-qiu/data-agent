# MVP V1 实施计划

## 1. 实施原则

项目采用 Spec-driven、Gate-driven 和 Evaluation-driven 的开发方式。每次只实现一个 Feature；每个 Feature 必须形成可运行、可测试、可审查的闭环。

## 2. 总体顺序

```text
ENG-001 Engineering Baseline
        ↓ Gate -1
DOC-001 Spec Cleanup
        ↓ Gate 0
DATA-001 Olist Import
        ↓
DATA-002 DWD and Diagnosis DWS
        ↓
DATA-003 Synthetic Evidence and Ground Truth
        ↓ Gate 1
META-001 Metadata Adaptation
        ↓ Gate 2
SQL-001 NL2SQL Adaptation
        ↓
SQL-002 NL2SQL Evaluation
        ↓ Gate 3
ANA-001 Intent Router
        ↓
ANA-002 Analysis Question Parser
        ↓
ANA-003 Capability Assessment
        ↓
ANA-004 Analysis Planner
        ↓
ANA-005 Analysis Task Executor
        ↓
ANA-006 Deterministic Analyzer
        ↓
ANA-007 Evidence Report
        ↓ Gate 4
EVAL-001 Diagnosis Regression
        ↓ Gate 5
API-001 Minimal Demo
```

## 3. Feature 与验收摘要

实时执行状态见 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)。已完成的首个 Feature Spec 为 [ENG-001 Engineering Baseline](specs/ENG-001_engineering_baseline.md)。后续 Feature 必须在进入对应阶段时单独建立 Spec，不得提前批量实现，也不得把“未来支持”的计划项描述为当前已实现能力。

| Feature | 目标 | 主要产物 | Gate 证据 |
|---|---|---|---|
| ENG-001 | 建立 Git、测试和静态检查基线 | 配置、工具链、Baseline 报告 | 三项命令可执行并记录真实结果 |
| ENG-002 | 清理存量 Ruff/mypy 诊断 | 全部静态检查清零 | Ruff 0 项、mypy 0 项、每批全量回归 |
| DOC-001 | 冻结唯一事实源 | README、AGENTS、实施计划、6 份设计文档 | 引用有效、口径无冲突 |
| DATA-001 | 导入 Olist | Raw 表、导入脚本、行数报告 | 原始文件与导入行数一致 |
| DATA-002 | 建立 DWD 和两张 DWS | DDL、ETL、对账 SQL | 粒度、PK/FK、GMV、Order Count 对账 |
| DATA-003 | 构造三类已知异常 | Generator、Ground Truth Registry | 固定 Seed 可复现、指标链一致 |
| META-001 | 适配新 Schema | Metadata、Metric Registry、索引 | 10～15 条召回样本通过 |
| SQL-001 | 复用并适配现有 NL2SQL | 新 Schema 支持、粒度防护 | 无无关重写、受控只读执行 |
| SQL-002 | 建立 NL2SQL 基线 | 30 条 Golden Dataset、报告 | Execution Accuracy 等真实指标 |
| ANA-001 | 区分 QUERY 与 DIAGNOSIS | 路由 Schema 和节点 | 固定改写一致、模糊问题可降级 |
| ANA-002 | 提取诊断结构 | Metric、时间、基线、Scope | 结构化输出和错误路径 |
| ANA-003 | 判断数据能力 | Supported/Unsupported Methods | 无数据不开放方法、无实验不开放因果 |
| ANA-004 | 生成最多四类任务 | AnalysisPlan | 只能选择 Supported Methods |
| ANA-005 | 执行受控分析查询 | Query Builder、执行轨迹 | 禁止任意 SQL、每项可回溯 |
| ANA-006 | 确定性分析 | Shapley、Dimension Contribution | 数学对账与边界测试 |
| ANA-007 | 校验证据并生成报告 | Validated Evidence、Report | 报告只读已验证证据 |
| EVAL-001 | 诊断回归 | 10 条案例和 Error Analysis | 数字一致、无无证据断言 |
| API-001 | 最小演示 | 单轮 Query API 与 Trace 展示 | 固定 Demo 全链路通过 |

## 4. Gate 定义

### Gate -1：Engineering Baseline

- Git 根目录明确；
- 本地敏感配置未纳入版本控制；
- pytest、Ruff、mypy 可以执行；
- 存量问题形成真实 Baseline；
- 没有修改业务逻辑。

### Gate 0：Specification Freeze

- README 不引用不存在文件；
- 事实源优先级明确；
- GMV、AOV、Order Count 口径唯一；
- 每张事实表与 DWS 粒度明确；
- Synthetic 与原始数据边界明确；
- V1 单轮、非因果边界明确；
- 诊断 SQL 采用 Controlled Query。

### Gate 1：Data Foundation

- Olist Raw、DWD、DWS 行数和金额可对账；
- 一对多 JOIN 不造成 GMV 膨胀；
- 整体订单量不从品类订单量相加获得；
- 比率由分子、分母聚合后计算；
- 三类 Synthetic Event 固定 Seed 可复现；
- Ground Truth、Evidence 与结果变化一致。

### Gate 2：Metadata

- 10～15 条固定样本覆盖表、字段、指标、JOIN 和枚举值；
- Metric Hit@1、Table/Column Recall@K 和 Join-key Recall 有真实记录；
- 检索上下文不存在明显粒度误导。

### Gate 3：NL2SQL

- 30 条固定样本完成全量执行；
- 报告 SQL Executability、Execution Accuracy、Metric、Table、Column 和 JOIN Accuracy；
- 危险 SQL 放行次数为 0；
- 所有失败有错误分类。

### Gate 4：Diagnosis Agent

- 单轮 GMV 下降问题能生成结构化计划；
- 任务数和分析轮次有硬上限；
- Shapley 拆解严格对账；
- 维度贡献正确处理反向抵消和总变化接近 0；
- 缺失证据时正确降级；
- 报告无越级因果语言。

### Gate 5：Diagnosis Evaluation

- 10 条首版功能回归集全部运行；
- Numeric Consistency 必须逐项通过；
- Unsupported Claim 为 0；
- 数据不足案例能够正确降级；
- Hit@1、Recall@3 和 Evidence Precision 报告真实结果，不虚构提升比例。

## 5. 固定 Demo

V1 固定演示以下完整问题，不使用省略式多轮追问：

1. `2018 年 5 月 GMV 是多少？`
2. `2018 年 5 月 GMV 相比 4 月变化了多少？`
3. `为什么 2018 年 5 月 GMV 下降？`
4. `2018 年 5 月哪些品类和州对 GMV 下降贡献最大？`
5. `2018 年 5 月流量、促销和库存分别发生了什么变化？`
6. `进一步分析 2018 年 5 月圣保罗州 GMV 下降的原因。`

## 6. 版本边界

V1.1 才考虑：

- `conversation_id`；
- LangGraph Checkpointer；
- 省略式连续追问；
- 价格、退款和配送候选因素；
- 更复杂的动态下钻。

严格因果推断只有在引入处理组、对照组、实验或准实验设计以后才能立项，不属于当前路线的默认升级。

## 7. MVP 后的归因规划演进

以下路线服务于项目面试展示和企业级可扩展性，但仍遵守“一个任务只实现一个 Feature”。除已完成项外，均不得描述为当前运行时能力：

```text
SEM-001 Analysis Semantic Context Design
        ↓
SEM-002 Semantic Registry and Context Builder
        ↓
CLARIFY-001 Clarification Response Integration
        ↓
PLAN-LLM-001 Bounded LLM Planner and Plan Validator
        ↓
PLAN-UI-001 Analysis Plan Trace
        ↓
INTERVIEW-001 Demo Script and Architecture Narrative
```

| Feature | 目标 | 改善内容 | 状态边界 |
|---|---|---|---|
| SEM-001 | 冻结语义绑定、分析语义和规划上下文 | 回答字段、指标、字段取值和当前能力如何进入归因规划 | 只做设计与契约测试 |
| SEM-002 | 实现 Registry 投影、受控语义绑定与 `PlannerSemanticContext` Builder | 统一归因语义来源，使用 Qdrant/ES 候选兜底且不把全量 Schema 交给模型 | 绑定能力经 CLARIFY-001 接入生产单轮 API；规划上下文 Builder 仍未接生产规划路径 |
| CLARIFY-001 | 将绑定状态接入单轮 API 与前端 | 缺少或歧义信息时展示具体补充项、候选和推荐完整问题 | 已完成，仅剩真实外部检索准确率未评测 |
| PLAN-LLM-001 | 实现确定性优先、最多一次模型规划、Validator 与回退 | 让复杂问题能在有限合法路径中动态取舍，同时保持可控和可审计 | 组件已完成，未接入生产 Graph/API |
| PLAN-UI-001 | 展示规范问题、能力、计划、回退与 Evidence Trace | 让演示和问题定位更直观 | 已完成，纯前端展示 |
| INTERVIEW-001 | 固化演示脚本和架构讲解 | 清晰说明 LLM 与确定性模块的职责边界 | 已完成，文档产物 |

`AnalysisTask` 继续作为类型化工具调用；后续不另建一套重复的通用 ToolCall。PLAN-LLM-001 组件已可独立调用，接入生产 Graph/API 与真实模型适配器需在新的 Feature 中单独实施。

## 8. MVP 可靠性加固路线

SQL-009 后按以下顺序继续，每项仍须建立独立 Spec、完成验证并在报告后停止；表中“计划”
不表示已实现能力：

```text
DOC-002 Status and Capability Truth Sync
        ↓
EVAL-002 NL2SQL Evaluation Integrity
        ↓
SQL-010 Post-SQL-009 Real-model Rerun
        ↓
根据真实失败决定后续 Runtime Remediation
```

| Feature | 目标 | 状态边界 |
|---|---|---|
| DOC-002 | 同步当前状态、能力边界和恢复指引 | 当前文档一致性 Feature |
| EVAL-002 | 修复结果列语义、Grain、Correction 和 Replay 身份等评测可信度问题 | 已完成；未运行真实模型，不更新运行时准确率 |
| SQL-010 | 在可信评测器上执行 SQL-009 后 Live/Replay 真实复测 | 计划，未开始；不得预先声明提升 |

SQL-010 完成前不根据 SQL-008 的旧失败继续叠加 Runtime 规则。真实复测后若仍有失败，
每个后续 Feature 只处理一个主要失败假设，并保持历史评测产物不可变。
