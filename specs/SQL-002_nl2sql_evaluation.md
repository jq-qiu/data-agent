# SQL-002 NL2SQL Evaluation

## 1. Feature

为已验收的 SQL-001 单轮 NL2SQL 链路建立固定 30 条 Golden Dataset、确定性结果比对与版本化真实基线报告，完成 Gate 3 证据闭环。

## 2. Source of Truth

1. 用户当前明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md`；
5. `docs/02_data_and_metric_design.md`；
6. `docs/03_metadata_and_nl2sql.md`；
7. `docs/06_evaluation.md`；
8. `AGENTS.md`；
9. SQL-001 已验收的运行时、SQL Policy 和完成报告；
10. `README.md`。

## 3. In Scope

- 固定 30 条 NL2SQL Golden，简单查询、聚合、时间、多表 JOIN、TopN、期间对比各 5 条；
- 每条包含问题、预期指标/表/字段/JOIN、参考 SQL、参考结果校验值、风险标签和结果顺序语义；
- 参考 SQL 和候选 SQL 均经过 SQL-001 Validator、`EXPLAIN` 和受控只读执行；
- 使用列别名无关、数值/日期规范化、可配置顺序敏感的结果集校验值；
- 报告 SQL Validity、Executability、Execution Accuracy、Metric Accuracy、Table/Column Precision 与 Recall、JOIN Accuracy、Grain Safety 和 Correction Success；
- 对固定危险 SQL 探针执行 Validator，记录危险 SQL 放行次数；
- 所有失败映射到 `docs/06_evaluation.md` 的固定错误分类并生成错误分析；
- 保存可复现的 JSON 汇总、逐案 CSV 和错误分析 Markdown，记录代码、数据集、Metadata、Policy、模型/参数、Prompt 摘要、延迟和 Token 可用性；
- 真实运行全部 30 条并冻结首次 Baseline；首次 Baseline 后只记录指标，不反向调整 SQL-001 逻辑。

## 4. Out of Scope

- 不修改 SQL-001 Prompt、召回 TopK、Schema Linking、Validator、纠错或执行行为来追逐分数；
- 不设置没有首次实测依据的准确率发布阈值；
- 不实现 QUERY/DIAGNOSIS 路由、AnalysisTask、Controlled Diagnosis Query Builder、Analyzer 或 Evidence Report；
- 不修改 Olist/Synthetic 数据、DWS、Metadata Registry 或索引；
- 不进入 ANA-001、EVAL-001 或 API-001。

## 5. Gate 3 Definition

Gate 3 通过条件仅使用已冻结事实源中的确定条件：

- 30 条固定样本全部产生最终记录；
- 六个类型各 5 条；
- 九类 NL2SQL 指标和 Table/Column Precision/Recall 均有真实值或明确的零分母说明；
- 参考 SQL 30/30 通过安全校验、EXPLAIN 和执行，固定结果校验值与数据集一致；
- 危险 SQL 放行次数为 0；
- 每个失败样本都有一个固定错误分类；
- 运行产物记录复现信息且不包含凭据或完整连接串。

首次 Baseline 的准确率只作为后续同版本对比起点，不作为本 Feature 自创的 Gate 阈值。

## 6. Allowed Files

- `specs/SQL-002_nl2sql_evaluation.md`；
- `app/nl2sql/evaluation.py`；
- `app/scripts/evaluate_nl2sql_v1.py`；
- `data/evaluation/nl2sql_golden_v1.json`；
- `data/reports/SQL-002_nl2sql_evaluation.json`；
- `eval_runs/sql-002-baseline-v1/**`；
- `test/nl2sql/test_evaluation.py`；
- `SQL-002_COMPLETION.md`；
- `IMPLEMENTATION_STATUS.md`。

不得修改 SQL-001 运行逻辑或任何诊断、AOV 拆解和 API 业务逻辑。

## 7. Local Plan

1. 定义版本化 Golden Schema、结果规范化、校验值和逐层指标；
2. 固定 30 条覆盖六类能力与关键粒度风险的样本；
3. 实现使用现有 LangGraph 和依赖容器的只读评测入口；
4. 单元测试数据集契约、结果比对、指标和错误分类；
5. 真实执行 30 条，保存完整复现信息、逐案结果和错误分析；
6. 执行全量测试与静态基线，审查差异和敏感信息；
7. 完成报告、独立提交并推送后停止 SQL-002。

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/nl2sql/test_evaluation.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_nl2sql_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

真实评测只连接配置明确为 `data_agent_v1_dw` 的隔离数据库；外部凭据、Token、Cookie 和完整连接串不得进入输出或 Git。

## 9. Acceptance Criteria

- Golden 恰好 30 条且六类各 5 条；
- 每条参考 SQL 能由 SQL-001 Validator 接受并在隔离 DW 返回冻结结果；
- 结果比较不受 SQL 文本、列顺序、列别名、Decimal 或日期表示差异影响，同时 TopN 保留顺序语义；
- 真实 LangGraph 候选全量运行且逐案记录最终状态；
- Gate 3 所需指标全部真实报告；
- 危险 SQL 放行 0 条；
- 失败样本均有固定错误分类和可审查详情；
- 运行产物可复现且无敏感信息；
- 全量 pytest 不回退，Ruff/mypy 不超过 SQL-001 基线 31/36；
- 未修改下游诊断与 API 逻辑。

## 10. Completion Boundary

完成 SQL-002 报告、独立提交并推送后停止，不得在本 Feature 中进入 ANA-001。
