# PLAN-LLM-001 Completion Report

## Feature

Bounded LLM Planner and Plan Validator：实现确定性优先的受限规划策略与计划校验器。`AnalysisPlanValidator` 校验任何计划不得越出解析问题与运行时能力边界；`BoundedPlannerPolicy` 只有在存在多条合法计划时才通过 `PlanSelector` 最多调用一次模型，选择无效、超时、模型不可用或选择器缺失时立即确定性回退且不重试。

## Changed Files

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

## Added Dependencies

无。

## Commands Executed

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

## Test Results

- PLAN-LLM-001 targeted tests：20 passed；
- Full pytest regression：337 passed（此前 317 + 新增 20）；
- Frontend Node tests：5 passed；Vite production build passed。

## Lint Results

`ruff check .` 0 项。

## Type Check Results

`mypy app` `Success: no issues found`，0 error。

## Evaluation Results

- Validator 接受全部现有确定性计划；
- Validator 拒绝时间/基期/Scope 变更、未请求/不可用维度与因素、能力外方法、不一致停止原因；指标为固定 `gmv` Literal，Schema 层即拒绝变更；
- 唯一合法计划返回 `DETERMINISTIC`，`model_calls=0`；
- Stub 多合法计划场景：接受 LLM 选择 `model_calls=1`；未知/空/选择器异常均回退默认计划且 `model_calls<=1`、不重试；
- 序列化结果不含 SQL、password、join 等物理线索；
- 真实模型规划：未评测；生产 Graph/API 未接入。

## Acceptance Criteria

1. Validator 拒绝上下文越界并接受确定性计划；2. 唯一路径 `DETERMINISTIC` 且 0 调用；3. 多路径最多一次选择；4. 失败均确定性回退不重试；5. Stub 多路径明确标记为架构验证；6. 序列化无物理 Schema/凭据/自由任务；7. 生产计划输出不变；8. Ruff/mypy 0/0；9. 文档更新为“已实现组件、未接入生产”。

## Known Issues

- V1 当前问题只有唯一合法计划，LLM 分支在生产不会被触发；该限制是有意保留的产品事实，不是缺陷；
- 真实 LangChain 模型适配器与 Prompt 留到生产 Graph 接入 Feature；
- 未执行真实模型规划评测。

## Diff Review Summary

新增 `plan_validator.py`（纯上下文校验）与 `planner_policy.py`（确定性优先、最多一次选择、回退），仅导出不改变现有 Graph/API/诊断行为。`AnalysisPlanner`、Capability、Parser、Grounding、Query、Analyzer、Evidence、Report 均未修改。Stub 多路径测试只在测试文件内构造，不进入 V1 合法计划提供器。未包含秘密、物理 Schema、SQL 或因果越界。
