# ANA-005 Analysis Task Executor and Controlled Query Builder

## 1. Feature

把 ANA-004 已验收的有限 `AnalysisPlan` 转换为确定性的参数化只读查询，通过 SQL-001 的统一 Validator 和隔离 DW Repository 顺序执行，并返回不含原始 SQL 与绑定值的结构化 Query Result/Trace。ANA-005 只取得 ANA-006 所需的可加总基础量，不执行 Shapley、变化贡献或候选因素数学计算。

## 2. Prerequisites and Source of Truth

1. 用户当前明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md`；
5. `docs/02_data_and_metric_design.md`；
6. `docs/03_metadata_and_nl2sql.md`；
7. `docs/04_analysis_methodology.md`；
8. `docs/05_agent_workflow.md`；
9. `docs/06_evaluation.md`；
10. `conf/meta_config.yaml` 的 metadata-v1 Table、Column、Metric 与 Relationship Registry；
11. `conf/sql_policy.yaml` 与 SQL-001 已验收的统一 Validator/Executor 边界；
12. `specs/ANA-004_analysis_planner.md` 与已验收的 AnalysisPlan/AnalysisTask；
13. `AGENTS.md`、`README.md` 和现有代码行为。

Prerequisite Gate：ANA-004 已在 `origin/main` 完成；全量 pytest 144 passed，Ruff/mypy 为 31/36 的已接受基线。

## 3. Inputs

- 严格的 `AnalysisPlan`；
- 注入的只读 `MetadataCatalog`、`SQLValidator` 与 DW Repository；
- 注入的 Query Context：`warehouse`，或带 `D01` 至 `D10` Case ID 的 `synthetic_case`；
- AnalysisTask 中已验证的 Metric、期间、Scope、维度、因素和依赖。

## 4. Outputs

- 每个物理查询一个连续 `Q001` 起始的 Query ID；
- Task ID、任务方法和稳定 Query Role；
- SQL SHA-256 指纹，不返回原始 SQL；
- Catalog/Metric/SQL Policy 版本；
- Validator 确认的表、字段、JOIN 与粒度警告；
- 结构化结果行；
- Node 只写入可 JSON 序列化的 `query_results`。

## 5. In Scope

- 固定 `warehouse` 与 `synthetic_case` 的受控表/字段布局，并在构造时逐项验证其存在于 Metadata Catalog；
- Period Comparison 查询两期 GMV 可加总基础量；
- Metric Decomposition 查询两期 GMV 与 Order Count 基础量；整体/地区使用地区表，单一 Category Scope 才允许使用品类表的 Category Order Count；
- Dimension Contribution 每个请求维度生成一个受控查询，按期间与该维度返回 GMV；地区与品类分解保持独立；
- Candidate Validation 把请求因素所需的 Visitors、Order Count、Promotion 与 Inventory 分子/分母聚合在一个查询中；比率留给 ANA-006 运行时计算；
- 所有日期、Region、Category 和 Synthetic Case 都使用命名绑定参数，不拼接到 SQL；
- 一个完整四任务 Plan 最多生成五个物理查询（T3 的 Region 与 Category 各一个）；
- 每个查询必须先通过统一 SQLValidator 和 Repository EXPLAIN，再由同一 Repository 只读执行；
- Repository 现有执行方法向后兼容地接受可选绑定参数；
- 验证返回列形状，失败时不把未验证结果写入 State；
- 固定 Query Builder/Executor 样本与真实隔离 `data_agent_v1_dw` 只读 Smoke，保存不含原始值和凭据的真实结果摘要。

## 6. Out of Scope

- 不计算 current/baseline delta、change rate、AOV、Conversion、Coverage、Fill Rate、Shapley 或维度贡献率；
- 不判断异常是否存在，不排序原因，不创建 Evidence 或报告；
- 不允许 LLM、任意 SQL、动态表名/字段名、自由 JOIN、写库、DDL、多语句、文件导出或系统表；
- 不修改 Metric/Metadata/SQL Policy 配置、数据生成、DWS 数据或原始 `dw`；
- 不修改现有 NL2SQL Graph、诊断 Graph、Agent State、API 或外部服务配置；
- 不进入 ANA-006。

## 7. Frozen Query Contract

物理 Query Role 固定为：

```text
period_comparison
metric_decomposition
dimension_contribution:region
dimension_contribution:category
candidate_validation
```

完整计划至多产生以上五项。每项 SQL 使用 `UNION ALL` 返回 `baseline`、`current` 两期；维度查询在每一期内按唯一维度键分组。绑定参数固定为对应期间的整数 `YYYYMMDD` 日期键，以及存在时的 `region`、`category`、`case_id`。

表选择固定为：

| Source/Scope | Period/Decomposition/Candidate | Region Dimension | Category Dimension |
|---|---|---|---|
| warehouse overall/region | `dws_sales_region_daily` | `dws_sales_region_daily` | `dws_sales_category_daily` |
| warehouse category | `dws_sales_category_daily` | `dws_sales_category_daily` | `dws_sales_category_daily` |
| synthetic overall/region | `analysis_sales_region_daily` | `analysis_sales_region_daily` | `analysis_sales_category_daily` |
| synthetic category | `analysis_sales_category_daily` | `analysis_sales_category_daily` | `analysis_sales_category_daily` |

Query Result 示例：

```json
{
  "query_id": "Q001",
  "task_id": "T1",
  "method": "period_comparison",
  "query_role": "period_comparison",
  "sql_fingerprint": "64 lowercase hex characters",
  "catalog_version": "metadata-v1",
  "metric_versions": [{"metric_id": "gmv", "version": "metadata-v1"}],
  "validation": {
    "tables": ["dws_sales_region_daily"],
    "columns": ["dws_sales_region_daily.date_id", "dws_sales_region_daily.gmv"],
    "join_relations": [],
    "grain_warnings": [],
    "policy_version": "sql-policy-v1",
    "max_rows": 500,
    "timeout_seconds": 10.0
  },
  "rows": [{"period_role": "baseline", "gmv": "100.00"}]
}
```

State/Trace 禁止包含原始 SQL、绑定参数、数据库凭据或完整连接串。

## 8. Allowed Files

- `specs/ANA-005_controlled_query_builder.md`；
- `app/diagnosis/__init__.py`；
- `app/diagnosis/query.py`；
- `app/nl2sql/validator.py`（仅修正布尔连接 AST 被误判为函数的问题，不改变安全白名单）；
- `app/repositories/mysql/dw/dw_mysql_repository.py`；
- `app/scripts/evaluate_analysis_task_executor_v1.py`；
- `data/evaluation/analysis_task_executor_golden_v1.json`；
- `data/reports/ANA-005_analysis_task_executor_evaluation.json`；
- `test/diagnosis/test_analysis_task_executor.py`；
- `ANA-005_COMPLETION.md`；
- `IMPLEMENTATION_STATUS.md`。

## 9. Local Plan

1. 定义 Query Context、受控 Built Query、Metric Lineage、Validation Trace 与 Query Result Schema；
2. 从 Catalog 验证固定 Source Layout，并实现四类任务到至多五个参数化查询的确定性路由；
3. 实现 Validate → EXPLAIN → Execute 顺序、行形状检查、指纹和连续 Query ID；
4. 向后兼容地为 DW Repository 增加绑定参数；
5. 固定完整/降级/Scope/Source 样本并运行隔离 DW 只读 Smoke；
6. 执行专项/全量 pytest、Ruff、mypy、敏感信息与 Diff Review；
7. 完成报告、独立提交并推送后停止 ANA-005。

## 10. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_analysis_task_executor.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_analysis_task_executor_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

真实 Smoke 只允许连接配置已锁定的 `data_agent_v1_dw`，所有查询先通过 Validator 与 EXPLAIN；输出只记录 Query Role、行数、指纹与通过状态。

## 11. Acceptance Criteria

- 固定 Layout 中每张表、字段和每个 Metric ID/Version 均来自注入 Registry，缺项立即拒绝构造；
- 完整计划恰好构建五个查询，顺序与 Query Role 固定且不超过硬上限；
- 日期与 Scope/Case 值只存在于绑定参数，不进入 SQL 文本；
- 每个 SQL 通过 SQL-001 的只读、Schema、函数、粒度、行上限和数据库策略校验；
- 任一 SQL Validation 或 EXPLAIN 失败时不得执行该 SQL；
- 每个结果有连续 Query ID、SQL 指纹、Catalog/Metric/Policy 版本和结构化行；
- 输出列与固定查询契约不一致时拒绝结果；
- 整体/地区 Order Count 不读取或汇总 Category Order Count；Category Order Count 只在单一 Category Scope 使用；
- 比率只查询可加总分子/分母，不在 SQL 内累加日比例；
- Synthetic Case 强制 `case_id` 参数，Warehouse 禁止 Case ID；
- Node 输出无 SQL、参数、客户端、Repository 或 Registry；
- 真实隔离 DW Smoke 只读通过，原 `dw` 与已验收数据不修改；
- 全量 pytest 不回退，Ruff/mypy 不超过 ANA-004 基线 31/36。

## 12. Tests

- Schema 与 Query Context 边界；
- 四类任务、两类 Source、Region/Category Scope 表字段选择；
- 完整 Plan 五查询上限与固定顺序；
- 参数绑定与注入防护；
- Registry 缺字段/指标拒绝；
- Validator 拒绝时 Repository 零调用；
- EXPLAIN 先于 Execute；
- 返回列形状与 Trace/指纹；
- 空计划、Node 序列化和无 SQL/参数检查；
- 真实隔离 DW 只读 Smoke。

## 13. Completion Boundary

完成 ANA-005 报告、独立提交并推送后停止，不得在本 Feature 中实现 ANA-006 Deterministic Analyzer。
