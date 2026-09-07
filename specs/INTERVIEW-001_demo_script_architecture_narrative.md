# INTERVIEW-001 Demo Script and Architecture Narrative

## 1. Feature

固化一份可用于面试讲解的演示脚本与架构叙事，清晰说明 LLM 与确定性模块的职责边界、当前真实能力与后续演进。本 Feature 只产文档与契约测试，不修改运行时代码。

## 2. Source of Truth

1. 用户当前明确授权实现 INTERVIEW-001；
2. 本 Spec；
3. `README.md`、`IMPLEMENTATION_PLAN.md`、`IMPLEMENTATION_STATUS.md`；
4. `docs/01_product_scope.md` 至 `docs/06_evaluation.md`；
5. 已完成 Feature Spec/Completion（API、DEMO、SEM、CLARIFY、PLAN-LLM、PLAN-UI）；
6. `AGENTS.md` 与当前代码/测试行为。

## 3. Prerequisite Findings

- 仓库提供六个固定 API 演示问题与 D01/D03/D05 Synthetic 演示入口；
- 真实 Olist DWS 缺 Traffic/Promotion/Inventory Evidence，演示会降级；Synthetic 数据可展示完整证据链；
- LLM 当前只在开放 NL2SQL 与低置信度意图分类兜底中使用；诊断规划阶段模型调用为 0；
- PLAN-LLM-001 组件未接入生产，叙事必须诚实区分“已实现组件”与“生产运行时”；
- 全量 pytest 338、前端 11、Ruff/mypy 0/0 可作为项目健康度证据。

## 4. In Scope

- 编写约 8–10 分钟演示脚本（准备清单、场景顺序、操作、讲稿、截图位、演示常见问题）；
- 编写架构讲解，覆盖职责分层、语义层、LLM 何时调用/不调用、安全与可审计、评测与降级、当前限制与演进；
- 所有描述与仓库事实一致，禁止把未接入/未评测能力写成已运行；
- README 导航与开发顺序同步；
- 新增文档契约测试，确保面试文档存在且生产边界表述不被回退。

## 5. Out of Scope

- 不修改 Python/TypeScript/SQL/Prompt/Graph/API/前端运行时代码；
- 不新增真实模型评测、截图或录屏；
- 不伪造成功率、效果数据或因果能力；
- 不进入新的产品 Feature。

## 6. Allowed Files

- `specs/INTERVIEW-001_demo_script_architecture_narrative.md`
- `INTERVIEW-001_DEMO_SCRIPT.md`
- `INTERVIEW-001_ARCHITECTURE_NARRATIVE.md`
- `test/test_documentation_contract.py`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `INTERVIEW-001_COMPLETION.md`

## 7. Local Plan

1. 编写演示脚本；
2. 编写架构讲解与 Q&A；
3. 更新 README/实施计划/状态；
4. 增加文档契约断言；
5. 运行文档契约、全量 pytest、Ruff、mypy、前端测试与构建、Diff Review；
6. 完成报告、独立提交并推送后停止。

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/test_documentation_contract.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
npm test --prefix frontend
npm run build --prefix frontend
git diff --check
git status --short --branch
```

## 9. Acceptance Criteria

1. 演示脚本可独立照着讲，时间、操作与讲稿清晰；
2. 架构叙事覆盖语义层、受控查询、确定性分析、Evidence、LLM 边界、模型调用预算、回退与评测；
3. 文档不宣称生产已使用 LLM 规划、真实语义检索或真实模型规划已评测；
4. 与 README/状态/完成 Feature 事实一致；
5. 文档链接有效，测试/静态检查不回退。

## 10. Completion Boundary

完成文档契约、回归、Diff Review、Completion Report、独立提交并推送后停止。
