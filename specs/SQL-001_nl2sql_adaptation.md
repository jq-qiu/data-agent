# SQL-001 NL2SQL Adaptation

## 1. Feature

复用现有单轮 LangGraph NL2SQL 链路，将其适配到 `metadata-v1` 与 Olist V1 Schema，并在执行前强制实施只读、Schema、JOIN 和粒度安全校验。

## 2. Source of Truth

1. 用户当前明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md`；
5. `docs/02_data_and_metric_design.md`；
6. `docs/03_metadata_and_nl2sql.md`；
7. `docs/06_evaluation.md`；
8. `AGENTS.md`；
9. `README.md`；
10. META-001 已验收的 `metadata-v1` 注册表和索引。

## 3. In Scope

- 让字段、指标和值召回读取 META-001 的 Qdrant/Elasticsearch/MySQL V1 目标；
- 将表粒度、指标公式、状态过滤、允许维度、白名单 JOIN 与粒度警告注入 SQL 生成上下文；
- 更新过时的国内数据 Prompt 示例，删除“指标缺失时使用通用常识”的规则；
- 实现单条只读 `SELECT`/CTE 的 AST 静态校验；
- 强制表、字段、函数、系统 Schema、JOIN 键、敏感字段和危险构造白名单；
- 阻止订单项与支付明细直接连接导致的金额膨胀；
- 阻止跨品类汇总 `category_order_count` 冒充整体订单量；
- 对 GMV 的 DWD SQL 强制使用注册表状态排除，并禁止运费或支付金额替代 GMV；
- 统一添加/收紧结果行上限，并对数据库校验和执行设置超时；
- 纠错最多一次，纠错结果必须重新通过同一安全校验后才能执行；
- 为适配、静态安全、粒度防护、纠错上限和受控执行增加单元测试；
- 运行少量真实只读 Smoke SQL，证明隔离 DW 上的受控执行可用。

## 4. Out of Scope

- 不建立或运行 30 条 NL2SQL Golden Dataset，不报告 Gate 3 Execution Accuracy；
- 不实现 QUERY/DIAGNOSIS 路由、AnalysisTask、Controlled Diagnosis Query Builder 或 Analyzer；
- 不实现 AOV/Shapley 拆解、维度贡献或 Evidence 报告；
- 不改变 DATA-001/002/003 或 META-001 数据与索引内容；
- 不新增多轮、登录、权限、附件或企业任务平台；
- 不进入 SQL-002 或 ANA-001。

## 5. Safety Policy

- 只允许单条 `SELECT` 或只读 CTE；
- 禁止 DDL、DML、事务、多语句、注释、系统表、文件读写和高风险函数；
- SQL 中每张表、每个真实字段和每条 JOIN 必须来自 `metadata-v1`；
- 禁止 `SELECT *`，禁止返回标记为敏感的客户标识；
- 结果集最多 500 行，数据库校验与执行默认 10 秒超时；
- 只允许读取配置已锁定的 `data_agent_v1_dw`；
- 失败 SQL 不执行，纠错后必须再次校验；
- 不输出或提交凭据、Token、Cookie 或完整连接串。

## 6. Allowed Files

- `specs/SQL-001_nl2sql_adaptation.md`；
- `pyproject.toml`、`uv.lock`（仅用于 SQL AST 解析依赖）；
- `conf/sql_policy.yaml`；
- `app/nl2sql/**`；
- `app/entities/{table_info,column_info,metric_info,value_info}.py`；
- `app/mappers/{table_info_mapper,column_info_mapper,metric_info_mapper}.py`（保持旧构建入口兼容）；
- `app/repositories/mysql/{dw,dw_mysql_repository.py,meta/meta_mysql_repository.py}`；
- `app/repositories/qdrant/{column_qdrant_repository.py,metric_qdrant_repository.py}`；
- `app/repositories/es/value_es_repository.py`；
- `app/agent/state.py`、`app/agent/context.py`、`app/agent/graph.py`；
- `app/agent/nodes/{recall_column,recall_metric,recall_value,merge_retrieved_info,filter_table,filter_metric,generate_sql,validate_sql,correct_sql,execute_sql}.py`；
- `app/api/dependencies.py`、`app/services/query_service.py`；
- `prompts/{expand_recall_keywords,filter_table_info,filter_metric_info,generate_sql,correct_sql}.prompt`；
- `test/nl2sql/**`；
- `docs/reports/SQL-001_COMPLETION.md`；
- `IMPLEMENTATION_STATUS.md`。

不得修改诊断模块；若实现必须触及其他文件，应先确认与本 Feature 的直接关系并在 Diff Review 披露。

## 7. Local Plan

1. 新增版本化 SQL Policy、V1 元数据读取与 Schema Linking DTO；
2. 使用 AST 实现确定性 SQL 安全、Schema、JOIN、指标和粒度校验；
3. 将现有召回/合并/生成/纠错/执行节点最小化接入 V1 Repository 与 Validator；
4. 修正“纠错后直接执行”为“最多一次纠错并重新校验”；
5. 使用 Stub/Mock 覆盖普通单元测试，另行运行真实隔离 MySQL 只读 Smoke；
6. 执行全量 pytest、Ruff、mypy、敏感信息检查和 staged Diff Review；
7. 完成报告、独立提交并推送后停止 SQL-001。

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/nl2sql
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

真实 Smoke 只执行已通过 Validator 的只读查询，并核对 `data_agent_v1_dw`。

## 9. Acceptance Criteria

- 运行时召回不再依赖旧国内演示 metadata；
- V1 表、字段、指标、规范值、关系和粒度警告进入结构化上下文；
- Prompt 不允许脱离 Metric Registry 自创指标公式或 JOIN；
- 危险 SQL、系统表、未登记表/字段/JOIN、敏感字段与多语句全部被拒绝；
- GMV、AOV、整体 Order Count、品类 Order Count 和一对多 JOIN 规则被确定性校验；
- 纠错最多一次，纠错 SQL 未重新验证时不可能执行；
- 每次执行最多返回 500 行并受超时保护；
- 真实隔离 DW Smoke SQL 校验、`EXPLAIN` 和执行成功；
- 全量 pytest 不回退，Ruff/mypy 不增加 ENG-001 存量问题；
- SQL-002 的 30 条评测未被提前实现。

## 10. Completion Boundary

完成 SQL-001 报告、独立提交并推送后停止，不得在本 Feature 中进入 SQL-002 或诊断链路。
