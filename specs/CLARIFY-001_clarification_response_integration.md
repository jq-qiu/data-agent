# CLARIFY-001 Clarification Response Integration

## 1. Feature

将 `SEM-002` 已实现的三种语义绑定结果接入单轮生产 API 和前端：完整且可绑定的问题继续进入现有确定性诊断链；信息缺失或存在歧义的问题返回可操作的补充项、逻辑候选和推荐完整问题；超出 V1 边界的问题返回安全的不支持说明。

## 2. Source of Truth

1. 用户当前明确授权继续实现不完整问题处理；
2. 本 Spec；
3. `specs/SEM-002_semantic_registry_context_builder.md`；
4. `specs/API-001_minimal_demo.md` 与 `specs/FRONT-001_mvp_frontend.md`；
5. `IMPLEMENTATION_PLAN.md`；
6. `docs/01_product_scope.md`、`docs/05_agent_workflow.md`、`docs/06_evaluation.md`；
7. `AGENTS.md`、`README.md`、`IMPLEMENTATION_STATUS.md` 和当前代码行为。

若事实源冲突，停止相关实现，不创造指标口径、物理字段、维度值、分析方法或因果规则。

## 3. Prerequisite Findings

- `SEM-002` 已提供 `READY`、`CLARIFICATION_REQUIRED`、`UNSUPPORTED` 三态绑定和受控 Qdrant/Elasticsearch 候选召回，但尚未接入 API 或前端；
- 当前 API 在 DIAGNOSIS 分支先读取运行时数据能力，再进入 Parser；因此不完整问题可能产生安全错误，且会进行不必要的数据访问；
- 当前 Intent Router 会把含诊断意图但未出现固定 GMV 词的请求标为 `non_gmv_diagnosis_unsupported`。该类请求既可能缺少指标，也可能使用需要语义召回的 GMV 别名，因此允许先进入受控语义绑定；
- 现有诊断 Graph 不接收预绑定对象。为保持 Graph 拓扑不变，检索完成的 `READY` 结果通过等价的规范化单轮问题交给现有 Parser；
- 前端目前把所有非 QUERY 结果都当作诊断报告，无法区分澄清、不支持和已完成诊断。

## 4. In Scope

- 在生产 DIAGNOSIS 数据访问之前运行 `SemanticGrounder`；
- 将 `non_gmv_diagnosis_unsupported` 作为受控诊断候选交给 Grounder，其他 UNSUPPORTED 路由保持现状；
- `READY` 才加载运行时能力并进入现有诊断 Graph；
- 对检索补全后的 `READY` 结果生成等价规范问题，复用现有 Parser、Capability、Planner 和执行链；
- 在最终诊断结果中公开 `binding_status=READY` 和安全的语义绑定 Trace；
- 将 `CLARIFICATION_REQUIRED` 返回为正常 SSE `result`，包含稳定原因、缺失字段、歧义字段、逻辑候选、推荐完整问题和逻辑限制；
- 将 Grounder 的 `UNSUPPORTED` 返回为正常 SSE `result`，包含稳定边界说明；
- 候选只公开逻辑指标 ID、逻辑维度和规范维度值，不公开检索分数、物理表列、SQL、连接或原始行；
- 前端区分 query、diagnosis、clarification、unsupported、error，并显示澄清卡片；
- 推荐问题按钮只填入输入框，由用户决定是否重新发送，不建立会话记忆；
- 使用 Stub/Mock 覆盖三态、无数据访问、候选安全和现有分支回归；
- 更新直接相关文档、状态与完成记录。

## 5. Out of Scope

- 不实现多轮补槽、历史消息、`conversation_id`、Checkpointer 或自动续跑；
- 不实现或调用 LLM Planner，不改变模型调用预算；
- 不修改 Intent Router 规则、NL2SQL Graph、Diagnosis LangGraph 拓扑或诊断节点；
- 不修改 AOV、GMV、Order Count、Controlled Query、Analyzer、Evidence 或 Report 业务逻辑；
- 不修改数据库、Synthetic 数据、Qdrant/Elasticsearch 索引或 Metadata Catalog；
- 不开放 GMV 之外的归因指标、价格/退款/配送因素或严格因果推断；
- 不进入 `PLAN-LLM-001` 或其他后续 Feature。

## 6. API Contract

完整诊断的终态结果在现有字段上增加：

```json
{
  "type": "result",
  "intent": "DIAGNOSIS",
  "binding_status": "READY",
  "answer": "...",
  "report_status": "COMPLETE | DEGRADED | NO_DECLINE",
  "analysis_trace": [],
  "evidence": [],
  "limitations": []
}
```

需要补充信息时返回：

```json
{
  "type": "result",
  "intent": "DIAGNOSIS",
  "binding_status": "CLARIFICATION_REQUIRED",
  "answer": "请补充分析时间。",
  "report_status": "CLARIFICATION_REQUIRED",
  "clarification": {
    "reason": "missing_current_period",
    "missing_fields": ["time"],
    "ambiguous_fields": [],
    "candidates": {
      "metrics": ["gmv"],
      "dimensions": ["region"],
      "values": [{"dimension": "region", "value": "PR"}]
    },
    "suggested_question": "为什么 2018 年 5 月 GMV 相比 2018 年 4 月下降？"
  },
  "analysis_trace": [],
  "evidence": [],
  "limitations": []
}
```

语义绑定确认超出能力时结构相同，但 `intent` 和 `binding_status` 为 `UNSUPPORTED`，`clarification` 仅保留稳定 `reason` 和安全候选/建议。API 不返回检索分数和 `retrieval_used`。

## 7. Runtime and Safety Contract

- 执行顺序固定为 `Intent Router -> Semantic Grounding -> Runtime Capability -> Existing Diagnosis Graph`；
- 非 `READY` 结果不得调用运行时 Capability Provider、数据库诊断、Planner 或报告生成；
- 完整的确定性问题不得调用 Qdrant、Elasticsearch 或 Embedding；
- 只有 Parser 无法安全完成指标、Scope 或显式维度绑定时，才按 SEM-002 策略调用受控检索；
- 检索失败必须返回澄清，不暴露异常信息；
- 规范问题仅由已校验的 `ParsedAnalysisQuestion` 构造，不接受模型生成的字段、值或方法；
- 所有结论仍使用关联/候选因素表述，禁止输出“导致、造成、证明”。

## 8. Allowed Files

- `specs/CLARIFY-001_clarification_response_integration.md`
- `app/api/dependencies.py`
- `app/services/query_service.py`
- `test/api/test_query_api.py`
- `test/test_documentation_contract.py` (直接阻塞项：CLARIFY-001 改变“尚未接入生产 Graph/API/前端”的文档事实，原契约测试需同步为新边界)
- `frontend/src/App.vue`
- `frontend/src/lib/sse.js`
- `frontend/src/style.css`
- `frontend/test/sse.test.js`
- `docs/05_agent_workflow.md`
- `docs/06_evaluation.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `CLARIFY-001_COMPLETION.md`

任何新增文件必须是本 Feature 的直接阻塞项并记录原因。

## 9. Local Plan

1. 先用后端与前端测试冻结三态响应、无数据访问和 UI 分类；
2. 在依赖容器中装配 Analysis Semantic Registry、受控 Retriever 和 Grounder；
3. 在 Query Service 中接入绑定 Gate、安全响应映射和规范问题交接；
4. 在前端增加澄清/不支持终态分类、补充项、候选和推荐问题交互；
5. 运行目标测试、前端构建、全量回归、静态检查和 Diff Review；
6. 更新文档、状态、完成报告，创建一个独立提交并推送后停止。

## 10. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/api/test_query_api.py test/diagnosis/test_semantic_grounding.py
npm test --prefix frontend
npm run build --prefix frontend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short --branch
```

普通测试中的 Embedding、Qdrant、Elasticsearch 和数据库访问均使用 Stub/Mock。真实外部检索未执行时必须写“未评测”。

## 11. Acceptance Criteria

1. 完整规范诊断返回 `READY` 并继续现有确定性诊断链，且不调用外部语义检索；
2. 缺少时间、指标、基期或歧义 Scope 返回 `CLARIFICATION_REQUIRED`；
3. 非 READY 绑定在读取运行时数据能力之前终止，不访问诊断数据库；
4. 明确不支持指标和非法期间返回 `UNSUPPORTED`；
5. `non_gmv_diagnosis_unsupported` 可进入受控 Grounder，其他原有 UNSUPPORTED 路由结果不变；
6. 检索补全后的 READY 问题能够通过现有 Parser，不修改 Graph 或诊断算法；
7. API 候选只包含逻辑对象，不含分数、物理 Schema、SQL、连接、凭据、原始行或 Ground Truth；
8. 前端清晰展示缺失项、歧义项、候选和推荐问题；推荐按钮只填入输入框；
9. QUERY、synthetic demo、已完成 DIAGNOSIS 和原 UNSUPPORTED 展示均保持兼容；
10. SSE 仍只产生一个终态结果或错误；
11. 固定 Stub 评测如实报告，真实外部检索没有运行时不得宣称准确率；
12. 全量 pytest 与前端测试/构建通过，Ruff/mypy 不超过既有 23/36 基线；
13. Diff 仅限允许文件，不包含秘密、因果越界表述或下一个 Feature。

## 12. Completion Boundary

完成测试、Diff Review、Completion Report、独立提交和推送后停止。未经用户再次明确授权，不进入 `PLAN-LLM-001`。
