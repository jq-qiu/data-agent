# PLAN-UI-001 Analysis Plan Trace

## 1. Feature

把诊断结果中已有的安全 Trace 明细在 Vue 前端展开为可读的分析轨迹卡片：规范问题、语义绑定状态、能力范围、分析计划（T1–T4）、受控查询、确定性计算、Evidence 与报告状态。只改变前端展示，不修改后端 API、Trace 内容或业务逻辑。

## 2. Source of Truth

1. 用户当前明确授权实现 PLAN-UI-001；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`、`IMPLEMENTATION_STATUS.md`；
4. `docs/05_agent_workflow.md`、`docs/06_evaluation.md`；
5. `specs/API-001_minimal_demo.md`、`specs/FRONT-001_mvp_frontend.md`、`specs/CLARIFY-001_clarification_response_integration.md`；
6. `AGENTS.md`、`README.md` 与当前前端/API 行为。

## 3. Prerequisite Findings

- `_diagnosis_result` 的 `analysis_trace` 已包含 `intent_router`、`semantic_grounding`、`analysis_question_parser`、`capability_assessment`、`analysis_planner`、`analysis_task_executor`、`deterministic_analyzer`、`evidence_checker`、`report_generator` 等阶段的字段化明细；
- API 测试 `test_diagnosis_graph_runs_seven_stages_and_public_trace_is_safe` 保证 Trace 不含 SQL、参数、行、指纹、连接、凭据或 Ground Truth；
- 当前前端 Trace 只显示阶段名称与状态，忽略各阶段已安全暴露的明细字段；
- 前端使用 `v-for` 文本插值，不使用 `v-html`，本 Feature 延续该安全约束。

## 4. In Scope

- 新增纯函数 `frontend/src/lib/trace.js`，把 Trace 数组转换为阶段卡片（名称、状态、安全 label/value 行）；
- 按阶段提取并中文展示：意图、语义绑定状态/原因/缺失歧义字段、规范问题（指标/当前期/基期/范围/请求维度/因素）、能力（支持方法/可用维度/缺失证据/数据质量）、计划任务与停止原因、查询与计算摘要、Evidence 摘要和报告状态；
- 未知阶段只显示名称与状态，不 dump 原始对象；
- `App.vue` 用 `<details>` 展开卡片列表，保留语义标签和键盘可用性；
- 增加 `frontend/test/trace.test.js` 冻结提取行为与安全边界；
- 更新 README/状态/实施计划/完成报告。

## 5. Out of Scope

- 不修改后端 Python、API Schema、SSE 事件、Trace 内容、LangGraph、Planner、Evidence、Report 或业务逻辑；
- 不新增 v-html、内联脚本、客户端业务计算或本地持久化；
- 不改变 QUERY、澄清、不支持、错误与报告正文渲染；
- 不接入 PLAN-LLM 的 BoundedPlannerPolicy 回退信息（未接生产，不虚构展示）；
- 不进入 INTERVIEW-001 或其他后续 Feature。

## 6. Allowed Files

- `specs/PLAN-UI-001_analysis_plan_trace.md`
- `frontend/src/lib/trace.js`
- `frontend/src/App.vue`
- `frontend/src/style.css`
- `frontend/test/trace.test.js`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `PLAN-UI-001_COMPLETION.md`

## 7. Local Plan

1. 先用 `trace.test.js` 冻结各阶段提取规则；
2. 实现 `trace.js` 纯函数；
3. 更新 `App.vue` 与样式，将阶段列表替换为卡片明细；
4. 运行前端测试与生产构建、后端全量回归和静态检查；
5. Diff Review、完成报告、独立提交并推送后停止。

## 8. Verification Commands

```powershell
npm test --prefix frontend
npm run build --prefix frontend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

## 9. Acceptance Criteria

1. 诊断 Trace 按阶段展示规范问题、能力、计划、任务、Evidence 与报告状态；
2. 每阶段只显示白名单 label/value，未知字段不输出；
3. QUERY/澄清/不支持/错误/普通报告展示不变；
4. 不使用 v-html、localStorage、cookie 或 API Key；
5. 前端测试与构建通过，后端回归不回退；
6. Diff 仅限允许文件。

## 10. Completion Boundary

完成测试、Diff Review、Completion Report、独立提交并推送后停止。
