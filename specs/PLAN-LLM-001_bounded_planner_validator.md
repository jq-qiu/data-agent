# PLAN-LLM-001 Bounded LLM Planner and Plan Validator

## 1. Feature

实现确定性优先的受限规划策略与计划校验器：`AnalysisPlanValidator` 校验任何计划不得越出问题范围与能力边界；`BoundedPlannerPolicy` 只在存在多条合法计划时通过注入的 `PlanSelector` 最多调用一次模型，输出无效、超时或模型不可用时立即确定性回退。V1 当前问题只有唯一合法计划，因此生产黄金问题规划阶段模型调用仍为 0。

## 2. Source of Truth

1. 用户当前明确授权按“Validator + 确定性优先策略 + Stub 演示 LLM/回退闭环，不接生产 Graph/API”的范围实现；
2. 本 Spec；
3. `specs/SEM-001_analysis_semantic_context_design.md`；
4. `docs/05_agent_workflow.md`、`docs/06_evaluation.md`；
5. `specs/ANA-004_analysis_planner.md`；
6. `IMPLEMENTATION_PLAN.md`、`IMPLEMENTATION_STATUS.md`；
7. `AGENTS.md`、`README.md` 与当前代码行为。

若事实源冲突，停止相关实现，不创造业务规则、指标口径、分析路径或模型调用策略。

## 3. Prerequisite Findings

- 现有 `AnalysisPlanner` 对每个合法 Parser/Capability 组合输出唯一的确定性最大计划：T1 期间对比固定，T2 拆解在能力支持时固定加入，T3 聚合所有请求且可用的维度，T4 聚合所有请求且对应能力可用的因素；
- Parser 对一般归因问题默认请求全部可用维度与全部候选因素，因此当前产品语义下不存在“同一问题多条合法计划”；
- `AnalysisPlan`/`AnalysisTask` Pydantic 已强制结构契约（ID 连续、方法唯一有序、依赖只允许 T1、禁止 SQL/未知字段），但仍缺少对 `question`/`capability` 上下文的校验；
- `AnalysisPlannerNode` 在诊断 Graph 中仍为确定性节点，本 Feature 不修改 Graph；
- 文档契约测试断言 README 中“LLM Planner 尚未实现”，需在实现后同步为“可独立调用但未接入生产 Graph/API”。

## 4. In Scope

- 实现 `AnalysisPlanValidator`：基于 `ParsedAnalysisQuestion` 与 `CapabilityAssessment` 校验计划是否改变指标/时间/基期/Scope、使用未请求或不可用维度/因素、选择能力外方法、空计划停止原因与数据质量是否一致；
- 实现通用合法计划选项契约与 V1 默认提供器（只返回确定性计划）；
- 实现 `BoundedPlannerPolicy`：
  - 唯一合法计划：确定性结果，模型调用 0；
  - 多条合法计划且 `PlanSelector` 可用：最多调用一次并校验选择；
  - 选择无效、超时、模型不可用或选择器缺失：不重试模型，回退确定性计划；
  - 输出含稳定 `source`、`model_calls`、`decision_reason` 与 `validator_issues`；
- `PlanSelector` 只接收 `PlannerSemanticContext` 与安全计划选项摘要，选择结果只能返回合法 `variant_id` 或空（回退），不接收物理 Schema、SQL、连接、Ground Truth 或密钥；
- 使用 Stub `PlanSelector` 和测试专用多选项提供器证明 LLM 选择、Validator 拒绝与确定性回退闭环，并明确标注为架构验证而非 V1 产品多路径；
- 保留现有确定性 Planner 与生产 Graph 行为完全不变；
- 更新文档契约测试、状态与完成报告，禁止宣称生产运行时已使用 LLM 规划。

## 5. Out of Scope

- 不将 `BoundedPlannerPolicy` 接入生产 `AnalysisPlannerNode`、API、前端或诊断 Graph；
- 不修改 Parser、Grounder、Capability Assessor、`AnalysisPlanner`、Query Builder、Analyzer、Evidence 或 Report 业务逻辑；
- 不新增真实 LangChain 模型适配器、Prompt 或模型配置（生产适配器留到接入 Graph 的后续 Feature）；
- 不创建当前产品不存在的多路径规则；V1 合法计划提供器始终唯一；
- 不修改 AOV、GMV、Order Count、NL2SQL、SQL Policy、Metadata、数据或数据库；
- 不进入 PLAN-UI-001、INTERVIEW-001 或其他后续 Feature。

## 6. Frozen Contracts

### 6.1 Validation issues

校验结果返回稳定代码，例如：

```text
metric_mutation
current_period_mutation
baseline_period_mutation
scope_mutation
unsupported_method
unrequested_dimension
dimension_not_available
unrequested_factor
factor_validation_unavailable
empty_plan_without_stop_reason
inconsistent_stop_reason
duplicate_validator_issue
```

### 6.2 Bounded plan result

```json
{
  "plan": {},
  "source": "DETERMINISTIC | LLM | FALLBACK",
  "model_calls": 0,
  "decision_reason": "unique_legal_plan",
  "validator_issues": []
}
```

`model_calls` 只在真正发起一次选择时记为 1；未发起模型调用为 0。失败回退不重试。

### 6.3 Plan selector

输入只有 `PlannerSemanticContext`（如可用）与 `LegalPlanOption` 的逻辑摘要；输出只能是 `variant_id` 或 `None`。禁止输出任务字段、SQL、表名、列名、JOIN、连接、Ground Truth 或密钥。

## 7. Allowed Files

- `specs/PLAN-LLM-001_bounded_planner_validator.md`
- `app/diagnosis/plan_validator.py`
- `app/diagnosis/planner_policy.py`
- `app/diagnosis/__init__.py`
- `test/diagnosis/test_plan_validator.py`
- `test/diagnosis/test_planner_policy.py`
- `test/test_documentation_contract.py`
- `docs/05_agent_workflow.md`
- `docs/06_evaluation.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `PLAN-LLM-001_COMPLETION.md`

任何新增文件必须是本 Feature 的直接阻塞项并记录原因。

## 8. Local Plan

1. 冻结本 Spec；
2. 实现 `AnalysisPlanValidator` 与测试；
3. 实现合法计划选项契约、V1 提供器与 `BoundedPlannerPolicy`，用 Stub 选择器覆盖唯一/多路径/无效/缺失/异常回退；
4. 更新文档契约、架构与状态文档；
5. 执行定向与全量 pytest、Ruff、mypy、前端回归、Diff Review；
6. 独立提交并推送后停止。

## 9. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_plan_validator.py test/diagnosis/test_planner_policy.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
npm test --prefix frontend
npm run build --prefix frontend
git diff --check
git status --short --branch
```

## 10. Acceptance Criteria

1. Validator 拒绝指标/时间/基期/Scope 变更、未请求或不可用维度/因素、能力外方法与不一致停止计划；
2. Validator 接受所有现有确定性计划；
3. 唯一合法计划返回 `DETERMINISTIC` 且 `model_calls=0`；
4. 多合法计划时最多一次选择，成功返回 `LLM`；
5. 选择无效、选择器缺失、异常或超时均回退确定性计划且不重试；
6. 失败回退保留稳定 `decision_reason` 与 `validator_issues`；
7. Stub 多路径测试明确标记为架构验证，不进入 V1 产品提供器；
8. 结果序列化不含物理 Schema、SQL、凭据、Ground Truth 或模型自由文本任务；
9. 生产 Graph/API 计划输出不变，全量 pytest 不回退；
10. Ruff/mypy 保持 0/0；文档不再宣称“尚未实现”但明确“未接入生产 Graph/API”。

## 11. Completion Boundary

完成测试、全量回归、Diff Review、Completion Report、独立提交并推送后停止，不进入 PLAN-UI-001 或 INTERVIEW-001。
