# ENG-002 Lint and Type Cleanup

## 1. Feature

清理仓库既有 23 项 Ruff 与 36 项 mypy 存量诊断，使 `ruff check .` 与 `mypy app` 全绿。所有修复只调整代码格式、导入、类型标注或 None 防护，不改变任何运行行为、指标口径、数据访问、LangGraph 拓扑或产品逻辑。

## 2. Source of Truth

1. 用户当前明确授权：先 Ruff 自动修复，再 mypy 分批，每批全量回归；
2. 本 Spec；
3. `AGENTS.md`（单 Feature、Scope Control、测试与安全约束）；
4. `IMPLEMENTATION_PLAN.md`、`IMPLEMENTATION_STATUS.md`；
5. `pyproject.toml`（Ruff/mypy 配置）；
6. 当前代码行为与既有测试。

## 3. Prerequisite Findings

- 工作区干净，`main` 领先 `origin/main` 一个 CLARIFY-001 提交（推送曾因网络连接重置失败）；
- Ruff 23 项：8×`I001` import 排序、6×`UP045` Optional 写法、4×`F401` 未使用 import、3×`F541` 空 f-string、1×`DTZ002`、1×`TRY004`；其中 21 项可自动修复；
- mypy 36 项分布在 11 个文件：client manager 初始化 Optional/None 传播、mappers 将 `str | None`/`dict | list | None` 传入非空 dataclass、Qdrant payload 解包、配置对象赋值、旧元数据服务列表/迭代类型；
- 现有测试没有依赖 `expand_recall_keywords` 的 `ValueError`，也没有断言 `add_extra_context` 的日期时区；mappers 通过 `test_runtime_adaptation.py` 用非 None 值覆盖 `to_model`；
- 没有任何测试直接写入或读取 client manager 的 `.client` 属性。

## 4. In Scope

- 用 `ruff check . --fix` 修复全部可自动修复项，再手工修复 `DTZ002` 与 `TRY004`；
- mypy 分批修复（每批后全量回归）：
  - 批次 M1：client managers 初始化和脚本使用（Optional/None）；
  - 批次 M2：mappers 的 None/JSON 类型收窄；
  - 批次 M3：Qdrant payload、DW repository、LLM api_key；
  - 批次 M4：配置加载与旧元数据服务类型；
- 保留 `datetime.today()` 的本地日期语义，改用带本地时区等价写法，不改变输出日期/星期/季度；
- 将 `expand_recall_keywords` 中“结果必须是 JSON 对象”的异常从 `ValueError` 改为 `TypeError`；
- 客户端属性在未初始化时给出明确 `RuntimeError`，替代原先的隐式 None 传播；
- 每批修改后运行全量 pytest；全部完成后运行 Ruff、mypy、前端测试与构建；
- 更新直接相关文档、状态与完成报告。

## 5. Out of Scope

- 不修改任何业务规则、指标公式、AOV/GMV/Order Count、NL2SQL、Controlled Query、Analyzer、Evidence、Report、Parser、Capability、Planner 或诊断 Graph；
- 不改变数据库 Schema、索引、数据或外部服务配置；
- 不新增类型检查开关绕过（例如把 `disallow_untyped_defs` 等默认关闭项打开后掩盖问题）；
- 不使用 `--ignore-errors` 或全局 `# type: ignore` 来掩盖；
- 不进入 `PLAN-LLM-001` 或其他后续 Feature。

## 6. Allowed Files

以下文件因包含既有 Ruff/mypy 诊断或直接阻塞修复而允许修改：

- `specs/ENG-002_lint_type_cleanup.md`
- `app/agent/llm.py`
- `app/agent/nodes/add_extra_context.py`
- `app/agent/nodes/expand_recall_keywords.py`
- `app/agent/nodes/extract_keywords.py`
- `app/clients/embedding_client_manager.py`
- `app/clients/es_client_manager.py`
- `app/clients/mysql_client_manager.py`
- `app/clients/qdrant_client_manager.py`
- `app/conf/app_config.py`
- `app/conf/meta_config.py`
- `app/core/context.py`
- `app/core/log.py`
- `app/diagnosis/runtime.py`
- `app/mappers/column_info_mapper.py`
- `app/mappers/metric_info_mapper.py`
- `app/mappers/table_info_mapper.py`
- `app/models/base.py`
- `app/models/column_info_mysql.py`
- `app/models/metric_info_mysql.py`
- `app/repositories/mysql/dw/dw_mysql_repository.py`
- `app/repositories/qdrant/column_qdrant_repository.py`
- `app/repositories/qdrant/metric_qdrant_repository.py`
- `app/scripts/build_meta_knowledge.py`
- `app/scripts/evaluate_diagnosis_v1.py`（直接阻塞项：M1 使 client 类型具体化后暴露 1 个候选因素类型错误）
- `app/scripts/evaluate_nl2sql_v1.py`（直接阻塞项：M1 使 client 类型具体化后暴露 3 个流 chunk 类型错误）
- `app/services/meta_knowledge_service.py`
- `test/test_documentation_contract.py`（若既有文档状态断言需同步）
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/ENG-002_COMPLETION.md`

任何新增文件必须是本 Feature 的直接阻塞项并记录原因。

## 7. Local Plan

1. Batch R：`ruff check . --fix` 后人工修复 DTZ002/TRY004，运行全量 pytest；
2. Batch M1：统一 client manager 初始化访问模式，修复 `build_meta_knowledge.py`，运行全量 pytest；
3. Batch M2：修复三个 mapper 的 None/JSON 类型，运行全量 pytest；
4. Batch M3：修复 Qdrant payload、DW repository、`llm.py`，运行全量 pytest；
5. Batch M4：修复配置加载与 `meta_knowledge_service.py`，运行全量 pytest；
6. 全量验证 Ruff/mypy/pytest/前端，Diff Review；
7. 更新文档、状态、完成报告，独立提交后尝试推送，若网络阻塞则如实报告。

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
npm test --prefix frontend
npm run build --prefix frontend
git diff --check
git status --short --branch
```

## 9. Acceptance Criteria

1. `ruff check .` 返回 0 项；
2. `mypy app` 返回 0 项 error；
3. 每批 mypy 修复后全量 pytest 通过，最终 317+ 全量通过；
4. 前端测试与生产构建通过；
5. 除明确的类型/初始化防护外，运行行为与输出不变；
6. 修复不改变日期语义、异常链可恢复性之外的公共错误类型；
7. 不包含秘密、凭据、连接信息或业务因果越界；
8. Diff 仅限允许文件，且不混入其他 Feature。

## 10. Completion Boundary

完成全量验证、Diff Review、Completion Report、独立提交并尝试推送后停止。若推送网络失败，在报告中如实记录本地提交 ID。
