# ANA-001 Intent Router

## 1. Feature

为单轮请求提供可校验、可审计的 `QUERY | DIAGNOSIS | UNSUPPORTED` 意图 Schema 与独立路由节点，在不接入尚未实现的诊断下游前提下冻结 V1 路由边界。

## 2. Source of Truth

1. 用户当前明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md`；
5. `docs/04_analysis_methodology.md`；
6. `docs/05_agent_workflow.md`；
7. `docs/06_evaluation.md`；
8. `AGENTS.md`；
9. `README.md`；
10. 已验收的 SQL-001/SQL-002 Query 路径与 Gate 3 基线。

## 3. In Scope

- 定义严格的 Intent 枚举与 `intent/confidence/reason` 输出 Schema；
- 实现无外部依赖的确定性单轮 Intent Router 与 LangGraph 兼容节点；
- 明确问数、聚合、排名、趋势、对比和“变化多少”路由为 QUERY；
- 明确 GMV 原因、驱动、拆解、维度贡献以及 Traffic/Promotion/Inventory 候选因素验证路由为 DIAGNOSIS；
- 将预测、自动调价/补货/投放、严格因果证明、非 GMV 原因诊断、省略式多轮追问、空白和无法判定问题降级为 UNSUPPORTED；
- 低置信度不得进入 DIAGNOSIS；
- 固定等价改写、边界和降级样本，真实报告路由准确率、各类召回、诊断误放行和降级结果；
- 提供后续 Graph 使用的稳定分支名，但不连接尚未实现的 ANA-002 节点。

## 4. Out of Scope

- 不解析目标指标、当前期、基期、Scope、维度或候选因素结构；
- 不实现 Capability Assessment、Analysis Planner、Task Executor、Analyzer、Evidence 或 Report；
- 不修改或接管现有 NL2SQL Graph；
- 不调用 LLM、MySQL、Qdrant 或 Elasticsearch；
- 不修改 SQL Policy、Prompt、数据、Metadata、API 请求/响应或 SSE 行为；
- 不进入 ANA-002。

## 5. Routing Policy

优先级固定为：

1. 空白、省略式追问、外部执行、预测和严格因果请求 → UNSUPPORTED；
2. 明确原因/驱动/拆解/贡献/候选因素请求且目标为 GMV → DIAGNOSIS；
3. 明确查数、聚合、排名、趋势、列举、对比或数值变化请求 → QUERY；
4. 其他不完整或歧义输入 → UNSUPPORTED。

`reason` 使用稳定原因代码，不输出凭据、SQL 或自由生成业务结论。`confidence < 0.70` 的结果只能是 UNSUPPORTED。

## 6. Allowed Files

- `specs/ANA-001_intent_router.md`；
- `app/diagnosis/__init__.py`；
- `app/diagnosis/intent.py`；
- `app/scripts/evaluate_intent_router_v1.py`；
- `data/evaluation/intent_router_golden_v1.json`；
- `data/reports/ANA-001_intent_router_evaluation.json`；
- `test/diagnosis/test_intent_router.py`；
- `ANA-001_COMPLETION.md`；
- `IMPLEMENTATION_STATUS.md`。

## 7. Local Plan

1. 定义 Intent Schema、规范化与固定优先级规则；
2. 实现纯函数路由、兼容节点和稳定分支映射；
3. 固定 QUERY、DIAGNOSIS、UNSUPPORTED 等价改写和边界数据集；
4. 执行确定性评测并保存版本化报告；
5. 执行专项/全量测试、Ruff、mypy、敏感信息与 Diff Review；
6. 完成报告、独立提交并推送后停止 ANA-001。

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_intent_router.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_intent_router_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## 9. Acceptance Criteria

- Schema 只接受三个冻结 Intent，confidence 限制在 0～1；
- 固定改写得到一致路由；
- 明确 QUERY 不被错误送入 DIAGNOSIS；
- 明确 GMV 诊断进入 DIAGNOSIS；
- 低置信度、非 V1、严格因果、省略追问和不完整输入正确降级；
- 所有固定样本有真实结果和错误明细；
- 节点输出仅含可序列化动态状态，路由器无外部 Client/Repository；
- 现有 Query 路径与 API 未修改；
- 全量 pytest 不回退，Ruff/mypy 不超过 SQL-002 基线 31/36。

## 10. Completion Boundary

完成 ANA-001 报告、独立提交并推送后停止，不得在本 Feature 中进入 ANA-002。
