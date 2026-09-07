# COMMENT-001 中文代码讲解注释

## 1. Feature

为后端 `app/**/*.py` 与前端 `frontend/src/**/*.js`、`frontend/src/App.vue` 补充面向开发人员的中文讲解注释，使读者能够理解模块职责、关键输入输出、边界、不变量和重要设计原因。此 Feature 只新增注释或 docstring，不改变任何运行逻辑、代码结构、配置、数据、测试或外部行为。

## 2. Source of Truth

1. 用户当前关于中文代码讲解注释的明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md` 至 `docs/06_evaluation.md`；
5. `AGENTS.md`；
6. 当前源码、测试与构建配置。

旧版 `attribution-analysis-agent-spec/` 不作为本 Feature 的注释事实源。若设计文档与当前代码的实现状态不同，注释必须同时遵守当前代码事实和文档明确的状态边界，不得把规划能力写成已接入能力。

## 3. Prerequisite Findings

- 开始 Inspect 时 Git 工作树干净，没有需要避让的未提交用户修改；
- 目标后端范围共 112 个 Python 文件、约 18,405 行，目标前端范围共 4 个文件、约 964 行；
- 当前关键链路的注释覆盖不均衡，`query_service.py`、`semantics.py`、`trace.js`、`sse.js` 和 `App.vue` 等关键文件缺少面向模块职责的中文讲解；
- 开放式问数使用既有 NL2SQL 链路；诊断运行时使用确定性 Parser、Capability、Planner、Controlled Query、Analyzer、Evidence 和 Report；`SEM-002` 与 `PLAN-LLM-001` 的部分组件可独立调用，但受限 LLM Planner 尚未接入生产 Graph/API；
- 前端由 `sse.js` 增量解析事件，由 `classifyTerminal` 分类终态，由 `trace.js` 按白名单构造 Trace 卡片，`App.vue` 负责请求状态与展示；
- Python 验证入口为 pytest、Ruff、mypy，前端验证入口为 Node test 与 Vite build；
- `frontend/node_modules`、`frontend/dist`、lockfile、`conf/app_config.yaml` 和数据文件不属于目标范围。

## 4. In Scope

- 为每个 `app/**/*.py` 文件新增简短中文模块 docstring，说明它在系统中的角色；
- 为关键类、协议、数据模型和关键函数补充中文 docstring，说明输入、输出、错误/降级边界和必须保持的不变量；
- 在 NL2SQL 链路、诊断链路、语义绑定、Registry、Planner、Validator、受控 SQL、Analyzer、Evidence、Report、API/Query Service 和 client managers 的关键分支补充“为什么这样设计”的中文注释；
- 为 `frontend/src/lib/sse.js`、`frontend/src/lib/trace.js`、`frontend/src/main.js` 和 `frontend/src/App.vue` 新增适量中文模块说明、JSDoc 或局部注释，重点解释 SSE 分块解析、进度去重、终态分类、安全 Trace 白名单和 Vue 响应式状态；
- 只新增注释/docstring，保留全部既有注释，不删除、不改写既有源码行；
- 新增本 Spec，并在实现完成后新增 `COMMENT-001_COMPLETION.md` 记录真实验证结果和 Diff Review；
- 在注释中明确真实/合成数据边界、确定性计算边界、SQL 安全边界、Evidence 可追溯边界和非因果语言边界，但不复制大段设计文档或写死易过期统计数字。

## 5. Out of Scope

- 不修改运行逻辑、变量名、函数/类签名、类型、导入、控制流、异常、返回值、SQL、Prompt、API/SSE 契约、前端行为、测试行为或代码结构；
- 不重构、不格式化、不排序导入，不修复当前 Feature 之外的问题；
- 不修改或删除任何已有注释、docstring、断言或测试数据；
- 本轮不修改 `test/**/*.py` 与 `frontend/test/**`；测试意图注释是用户允许的可选项，但不纳入本次冻结范围；
- 不修改 README、实施计划、实施状态或既有 Feature/Completion 文档；
- 不新增依赖，不改数据库、索引、数据、配置或生成内容；
- 不读取、输出或提交 API Key、密码、Token、Cookie、完整连接串；
- 不包含 `node_modules`、`dist`、lockfile、`conf/app_config.yaml`、数据文件、缓存和评测运行产物；
- 不提交、不推送；完成后先向用户展示改动清单和代表性注释，等待后续决定。

## 6. Allowed Files

- `specs/COMMENT-001_chinese_code_explanation.md`
- `app/**/*.py`
- `frontend/src/**/*.js`
- `frontend/src/App.vue`
- `COMMENT-001_COMPLETION.md`

除以上路径外，不允许修改其他文件。验证命令产生的忽略文件不得进入 Diff。

## 7. Comment Style and Truthfulness Rules

1. 模块顶部使用一至数句中文说明整体职责；Python 使用 docstring，JavaScript/Vue 使用对应语言的模块注释；
2. 类和关键函数只解释调用方真正需要知道的输入、输出、失败边界与不变量；
3. 局部注释优先解释设计原因和安全边界，不逐行复述自明代码；
4. 注释使用当前代码中的规范名称，涉及公式、粒度、数据来源和能力状态时以事实源为准；
5. 明确区分“当前运行时已接入”“独立组件已实现”和“未来规划”，不得将 Stub 评测或设计目标写成生产能力；
6. 不在注释中出现秘密值、完整连接信息、真实生产数据或 Ground Truth 原因泄漏；
7. 后端和前端源码 Diff 只能增加注释/docstring，源码删除行数必须为 0。
8. 对首次阅读不直观的关键操作增加块级或关键行注释，明确该行正在读取什么、转换什么、校验什么，以及结果下一步交给谁；不能只停留在模块和函数概述。

## 8. Local Plan

1. 按文件逐一读取后再注释，先处理 NL2SQL、Graph、API/Query Service 与 client managers；
2. 处理诊断语义绑定、Registry、Capability、Planner/Validator、Controlled Query 和 Runtime；
3. 处理 Analyzer、Evidence、Report，以及 metadata、repository、data foundation、synthetic、evaluation 和 scripts；
4. 处理前端 SSE、终态分类、Trace 白名单和 `App.vue` 展示状态；
5. 检查所有目标文件均有模块说明，并人工审查关键注释与真实实现一致；
6. 运行全量后端与前端验证，检查源码 Diff 只有新增注释/docstring且没有删除行；
7. 新增完成报告，向用户展示改动清单和代表性示例，不提交、不推送并停止。

## 9. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
npm test --prefix frontend
npm run build --prefix frontend
git diff --check
git diff --numstat -- app frontend/src
git status --short --branch
```

此外执行人工 Diff Review：确认目标源码只有新增注释/docstring、删除行数为 0，未修改既有注释，未出现秘密、SQL/Prompt/配置/数据或其他行为改动；确认构建生成内容未进入 Git Diff。

## 10. Acceptance Criteria

1. 所有 `app/**/*.py` 和指定前端源文件都有简短、真实的中文模块职责说明；
2. 重点链路的关键类/函数与非显然设计决策得到适量讲解，简单代码不过度注释；
3. 注释准确说明 LLM 与确定性模块、开放 NL2SQL 与受控诊断查询、State 与 Context、Evidence 与 Report 的职责边界；
4. 注释不虚构生产接入、实测结果、指标口径、表字段、JOIN 或因果结论；
5. 所有既有源码和既有注释保持原样，目标源码 Diff 删除行数为 0；
6. pytest、Ruff、mypy、前端测试和生产构建均通过；如存在基线失败，记录真实数量与类别且本 Feature 不新增失败；
7. Diff 仅限 Allowed Files，不包含秘密、配置、依赖、数据或生成内容；
8. 完成后提供改动清单和代表性注释示例，不自动提交或推送。

## 11. Confirmation Gate and Completion Boundary

本 Spec 写入并完成 Read/Inspect 后冻结范围。在用户明确确认前，不修改任何目标源码。

用户确认后才进入 Implement。完成 Test、Diff Review、Completion Report 和用户预览后停止，等待用户决定是否需要后续提交或推送。
