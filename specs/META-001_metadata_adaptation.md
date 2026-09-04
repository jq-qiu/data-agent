# META-001 Metadata Adaptation

## 1. Feature

将元数据知识库适配到 DATA-002 与 DATA-003 已验收的 Olist V1 Schema，建立规范化的表、字段、指标、关系和值注册表，并以 12 条固定样本完成 Gate 2 检索评测。

## 2. Source of Truth

1. 用户当前明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/02_data_and_metric_design.md`；
5. `docs/03_metadata_and_nl2sql.md`；
6. `docs/06_evaluation.md`；
7. `AGENTS.md`；
8. `README.md`；
9. DATA-002 与 DATA-003 已验收的真实 Schema。

## 3. In Scope

- 用配置文件定义实际 V1 表、字段、指标与允许的 JOIN 关系；
- 固化 `GMV = SUM(fact_order_item.price)` 与 `AOV = GMV / COUNT(DISTINCT order_id)`；
- 标注表粒度、时间列、主键、敏感字段和值索引开关；
- 明确地区、品类、订单、支付、合成 Evidence 及一对多关系的粒度警告；
- 校验配置中的表、字段、指标依赖和 JOIN 键都真实存在于隔离 DW；
- 在 MySQL 元数据库创建并同步 Feature 独占的 `meta_v1_*` 规范化表；
- 在 Qdrant 创建确定性、可重复构建的 `data-agent-metadata-v1` 语义索引；
- 在 Elasticsearch 创建 `data-agent-value-v1`，将别名映射到真实列与规范值；
- 固定 12 条 Metadata Golden Dataset，并真实记录 Gate 2 指标；
- 增加单元测试、评测报告、完成报告与实施状态更新。

## 4. Out of Scope

- 不修改 NL2SQL 生成、修复、校验或执行逻辑；
- 不修改 LangGraph、Agent State、Agent Context 或 API；
- 不实现 AOV 拆解、异常诊断、Shapley 或诊断报告；
- 不修改 DATA-001/002/003 的 ODS、DWD、DWS、Synthetic 或 Ground Truth 数据；
- 不删除或覆盖旧 `table_info`、`column_info`、`metric_info`、`column_metric`；
- 不进入 SQL-001 或任何后续 Feature。

## 5. Isolation and Safety

- 只读取 `data_agent_v1_dw`，不得连接或修改原始 `dw`；
- 新元数据使用独立 `meta_v1_*` 表，旧元数据表保持不变；
- Qdrant 与 Elasticsearch 使用 `-v1` 独立集合/索引；
- 构建只允许对本 Feature 独占目标执行可重复的全量同步；
- 日志、报告、测试输出和 Git 中禁止出现 API Key、密码、Token、Cookie 或完整连接串；
- 原始 Olist 文件继续保持 Git 忽略。

## 6. Allowed Files

- `specs/META-001_metadata_adaptation.md`；
- `conf/meta_config.yaml`；
- `app/metadata/**`；
- `app/scripts/build_meta_knowledge_v1.py`；
- `app/entities/value_info.py`；
- `app/repositories/es/value_es_repository.py`；
- `test/metadata/**`；
- `data/evaluation/metadata_golden_v1.json`；
- `data/reports/META-001_metadata_evaluation.json`；
- `META-001_COMPLETION.md`；
- `IMPLEMENTATION_STATUS.md`。

若实现过程中必须修改其他文件，先确认其属于本 Feature 且在 Diff Review 中披露；不得借机重构下游模块。

## 7. Local Plan

1. 将旧演示配置替换为实际 Olist V1 Metadata、Metric Registry 与 Relationship Registry；
2. 实现配置加载、确定性 ID、Schema/指标/关系/粒度校验；
3. 实现独立 MySQL、Qdrant 与 Elasticsearch 构建器及幂等同步；
4. 实现离线可测的检索上下文拼装，并用真实外部服务运行固定评测；
5. 运行定向测试、全量 pytest、Ruff、mypy、敏感信息检查和 Git Diff Review；
6. 仅在 Gate 2 通过后更新状态、完成报告、独立提交并推送，然后停止本 Feature。

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/metadata
.\.venv\Scripts\python.exe -m app.scripts.build_meta_knowledge_v1 --evaluate
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## 9. Acceptance Criteria

- 配置不再包含中国省份、大区、品牌或不存在的 Olist 字段；
- 每个注册表对象字段满足 `docs/03_metadata_and_nl2sql.md`；
- 所有注册表表/字段/JOIN 键均通过真实隔离 DW Schema 校验；
- 指标公式只来自 Metric Registry，GMV 不含运费；
- `dws_sales_region_daily` 明确承担整体 Order Count 与 AOV；
- `dws_sales_category_daily.category_order_count` 明确禁止跨品类相加解释整体订单量；
- 一对多关系包含指标膨胀警告；
- 巴西州保留州代码、葡萄牙语/英语名称及中文检索别名，并映射到真实 `state_code`；
- MySQL、Qdrant、Elasticsearch 构建可重复执行且结果稳定；
- 12 条固定样本覆盖指标、表、字段、JOIN、枚举、粒度警告与无关噪声；
- Metric Hit@1、Table/Column Recall@K、Join-key Recall、Value Grounding Accuracy、MRR、Context Precision/Recall 与 Context Token Count 有真实记录；
- 检索上下文没有明显粒度误导，Gate 2 通过；
- 全量 pytest 不回退，Ruff 与 mypy 不增加相对 ENG-001 的存量问题。

## 10. Completion Boundary

完成 META-001 报告、独立提交并推送后停止，不得在同一 Feature 中进入 SQL-001。
