# INTERVIEW-001 Architecture Narrative

## 1. 一句话定位

> 基于 LangGraph 与 NL2SQL 的经营指标异动诊断 Agent：开放问数交给受控 NL2SQL，GMV 下降诊断交给“语义绑定 + 能力评估 + 确定性计划 + 受控 SQL + 确定性分析 + Evidence”的可解释管线，LLM 只在必要位置承担受限任务。

## 2. 要解决的问题

业务用户会问两类问题：

```text
2018 年 5 月 GMV 是多少？        → 开放问数
2018 年 5 月 GMV 为什么下降？     → 归因诊断
```

诊断不能像闲聊一样“听起来合理”，必须回答：

- GMV 的口径是什么（哪个字段、哪个过滤条件）？
- 下降来自 Order Count 还是 AOV？
- 地区、品类的贡献是多少？
- 流量/促销/库存是否有同向证据？
- 没有数据时，为什么不能下结论？

## 3. 分层架构（当前生产）

```text
User Question
      │
      ▼
Intent Router（规则优先 + 受限语义兜底）
      │
      ├── QUERY ──► NL2SQL Graph ──► QueryAnswer
      │
      └── DIAGNOSIS
              ▼
   Semantic Grounding（CLARIFY-001 已接入）
              ▼
   Analysis Question Parser
              ▼
   Capability Assessment（真实数据 vs Synthetic）
              ▼
   Analysis Planner（当前确定性）
              ▼
   AnalysisTask T1–T4
              ▼
   Controlled Query Builder → SQL Validator → Executor
              ▼
   Deterministic Analyzer（拆解、贡献率、候选因素）
              ▼
   Evidence Validation
              ▼
   Report Generator（只读 Validated Evidence）
```

## 4. 分层职责

| 层/组件 | 职责 | 不做什么 |
|---|---|---|
| 语义层（Grounding/Registry/Context） | 把用户表达绑定为规范指标/维度/时间/Scope，提供逻辑规划知识 | 不给模型全量 Schema |
| Intent Router | 路由 QUERY/DIAGNOSIS/UNSUPPORTED | 不把强边界请求交给模型覆盖 |
| NL2SQL | 开放问数自然语言 → 受控 SQL | 指标公式与表 JOIN 不能虚构 |
| Analysis Planner | 生成 T1–T4 类型化任务 | 不写 SQL、不算贡献率 |
| Query Builder/Validator/Executor | 构造并执行只读参数化 SQL | 不允许任意命令/写库 |
| Deterministic Analyzer | 数学计算与对账 | 不使用 LLM 计算 |
| Evidence Checker | 校验来源、口径、声明强度 | 不纵容无证据断言 |
| Report Generator | 只消费 Validated Evidence | 不直接读原始行自由发挥 |

## 5. 为什么不让 LLM 直接“分析数据”

直接把表结构丢给 LLM 的 ChatBI 会退化成不稳定系统：模型不知道 GMV 的正式口径、不知道哪些维度可下钻、哪些证据能证明什么。

本项目拆成三层：

```text
问题解析（确定哪些对象）
        ↓
业务语义层（指标定义、维度、方法、限制）
        ↓
LLM/Planner 只在受限范围内选择路径
```

更准确地说：

- **开放问数**：LLM 负责自然语言 → SQL，但召回、Schema 白名单、函数白名单、粒度防护都在模型外；
- **归因诊断**：默认确定性；LLM Planner 只有在“多条合法路径”时最多调用一次，输出还要过 Validator，失败立即确定性回退；
- **计算和结论**：LLM 不直接计算贡献率，也不生成最终业务结论。

## 6. LLM 调用边界与预算

当前真实运行：

```text
开放 QUERY        ：LLM 生成 SQL（受控）
意图低置信度兜底  ：LLM 分类器，最多一次
标准诊断规划      ：0 次（确定性 Planner）
```

已实现但未接入生产：

```text
PLAN-LLM-001：BoundedPlannerPolicy + AnalysisPlanValidator
   唯一合法计划 → DETERMINISTIC，0 次调用
   多条合法计划 → 最多 1 次选择；无效/超时/不可用 → 不重试，确定性回退
```

设计预算（来自 `docs/06_evaluation.md`）：

```text
Planner Model Calls <= 1
Total Attribution Model Calls <= 2
```

## 7. 安全与可审计

- SQL：只读库 `data_agent_v1_dw`；Validator 校验注册表/列/JOIN、函数白名单、TopN 粒度；禁止多语句/系统表/文件导出；
- Schema：表名、列名、JOIN 不能由 LLM 虚构，全部来自 Catalog/Metric Registry；
- Trace：API Trace 不含 SQL、参数、原始行、指纹、凭据；前端“分析轨迹”只按白名单字段展示；
- 秘密：`conf/app_config.yaml` 本地忽略，禁止提交 API Key/密码/Token；
- 报告：只能消费 Validated Evidence，因果措辞被禁止；
- Ground Truth：Synthetic 标签只用于评测，运行时不读取。

## 8. 评测与工程健康度

固定评测层次：

```text
NL2SQL Golden（30 条）
Diagnosis Golden（D01–D10）
Semantic Grounding（12 条固定样本）
Grouped TopN（4 条）
前端 SSE/Trace 单元测试
```

当前工程健康度：

```text
全量 pytest：338 passed
前端 Node：11 passed，Vite build passed
Ruff：0
mypy：0
```

诚实边界：

- 真实 Olist 没有 Traffic/Promotion/Inventory 数据 → 运行时能力降级；
- Qdrant/ES 真实召回准确率未评测，当前只用 Stub 验证契约；
- LLM 规划组件已实现但未接生产，真实模型规划未评测。

## 9. 总结

> 这个项目证明的不是“GPT 能分析数据”，而是“如何把一个会生成内容的大模型，装进一个会算账、会校验、会拒绝的确定性系统里”。
