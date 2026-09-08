# Feature 完成报告索引

本目录保存各 Feature 的完成证据、验证命令、评测结果、已知问题和 Diff Review。
报告记录的是对应 Feature 完成时的真实状态，因此历史测试数量和静态检查基线可能
不同；当前整体状态以仓库根目录的 [`IMPLEMENTATION_STATUS.md`](../../IMPLEMENTATION_STATUS.md)
为准。

## 工程与文档

- [ENG-001 Engineering Baseline](ENG-001_BASELINE.md)
- [ENG-002 Lint and Type Cleanup](ENG-002_COMPLETION.md)
- [DOC-001 Specification Cleanup](DOC-001_COMPLETION.md)
- [DOC-002 Status and Capability Truth Sync](DOC-002_COMPLETION.md)
- [COMMENT-001 Chinese Code Explanation](COMMENT-001_COMPLETION.md)
- [INTERVIEW-001 Architecture Narrative（演示脚本仅本地保留）](INTERVIEW-001_COMPLETION.md)
- [SHOWCASE-001 Public Repository Presentation](SHOWCASE-001_COMPLETION.md)

## 数据基础

- [DATA-001 Olist Import](DATA-001_COMPLETION.md)
- [DATA-002 DWD and Diagnosis DWS](DATA-002_COMPLETION.md)
- [DATA-003 Synthetic Evidence and Ground Truth](DATA-003_COMPLETION.md)

## Metadata、NL2SQL 与路由

- [META-001 Metadata Adaptation](META-001_COMPLETION.md)
- [SQL-001 NL2SQL Adaptation](SQL-001_COMPLETION.md)
- [SQL-002 NL2SQL Evaluation](SQL-002_COMPLETION.md)
- [ROUTE-001 Hybrid Intent Router](ROUTE-001_COMPLETION.md)
- [SQL-003 Grouped TopN Query Support](SQL-003_COMPLETION.md)
- [SQL-004 Deterministic SchemaLinkingPlan](SQL-004_COMPLETION.md)
- [SQL-005 SchemaLinkingPlan Rerun](SQL-005_COMPLETION.md)
- [SQL-006 Metric and Calendar Enforcement](SQL-006_COMPLETION.md)
- [SQL-007 Live/Replay Evaluation](SQL-007_COMPLETION.md)
- [SQL-008 Metric/Calendar Real-Model Rerun](SQL-008_COMPLETION.md)
- [SQL-009 Query Semantics Remediation](SQL-009_COMPLETION.md)
- [EVAL-002 NL2SQL Evaluation Integrity](EVAL-002_COMPLETION.md)
- [SQL-010 Post-SQL-009 Real-model Rerun](SQL-010_COMPLETION.md)
- [EVAL-003 Primary Failure Classification Completeness](EVAL-003_COMPLETION.md)
- [SQL-011 Calendar Literal Repair Normalization](SQL-011_COMPLETION.md)
- [SQL-012 Required Metric Subquery Flattening](SQL-012_COMPLETION.md)
- [SQL-013 Structured Plan Repair Constraints](SQL-013_COMPLETION.md)
- [SQL-014 Post-repair Real-model Rerun](SQL-014_COMPLETION.md)
- [SQL-015 Unqualified Derived-column and Date ID Repair](SQL-015_COMPLETION.md)
- [SQL-016 Post-SQL-015 Real-model Rerun](SQL-016_COMPLETION.md)
- [SQL-017 Overall DWS Required Columns](SQL-017_COMPLETION.md)

## 诊断分析与评测

- [ANA-001 Intent Router](ANA-001_COMPLETION.md)
- [ANA-002 Analysis Question Parser](ANA-002_COMPLETION.md)
- [ANA-003 Capability Assessment](ANA-003_COMPLETION.md)
- [ANA-004 Analysis Planner](ANA-004_COMPLETION.md)
- [ANA-005 Controlled Query Builder](ANA-005_COMPLETION.md)
- [ANA-006 Deterministic Analyzer](ANA-006_COMPLETION.md)
- [ANA-007 Evidence Report](ANA-007_COMPLETION.md)
- [EVAL-001 Diagnosis Regression](EVAL-001_COMPLETION.md)
- [FIX-001 Gate 5 Remediation](FIX-001_COMPLETION.md)
- [REPORT-001 Localized Evidence Limitations](REPORT-001_COMPLETION.md)
- [REPORT-002 Candidate Section Readability](REPORT-002_COMPLETION.md)

## 语义、澄清与规划

- [SEM-001 Analysis Semantic Context Design](SEM-001_COMPLETION.md)
- [SEM-002 Semantic Registry and Context Builder](SEM-002_COMPLETION.md)
- [CLARIFY-001 Clarification Response Integration](CLARIFY-001_COMPLETION.md)
- [PLAN-LLM-001 Bounded Planner Validator and Policy](PLAN-LLM-001_COMPLETION.md)
- [PLAN-UI-001 Analysis Plan Trace](PLAN-UI-001_COMPLETION.md)

## API、前端、演示与运行

- [API-001 Minimal Demo API](API-001_COMPLETION.md)
- [FRONT-001 MVP Frontend](FRONT-001_COMPLETION.md)
- [FRONT-002 SSE Progress Render](FRONT-002_COMPLETION.md)
- [DEPLOY-001 Single-process Runtime](DEPLOY-001_COMPLETION.md)
- [DEMO-001 Synthetic Diagnosis Demo](DEMO-001_COMPLETION.md)

## 阅读建议

首次了解项目时无需逐份阅读全部报告，建议依次查看：

1. [DATA-002](DATA-002_COMPLETION.md)：理解 DWD/DWS 粒度与指标对账；
2. [SQL-002](SQL-002_COMPLETION.md)：理解 NL2SQL 首次真实基线和错误分类；
3. [ROUTE-001](ROUTE-001_COMPLETION.md)：理解混合意图路由；
4. [SQL-004](SQL-004_COMPLETION.md)：理解 SQL 生成前的确定性 Schema 方案；
5. [ANA-005](ANA-005_COMPLETION.md) 至 [ANA-007](ANA-007_COMPLETION.md)：理解受控查询、
   确定性分析、Evidence 与报告；
6. [FIX-001](FIX-001_COMPLETION.md)：理解冻结 Synthetic 诊断回归结果；
7. [API-001](API-001_COMPLETION.md) 与 [FRONT-001](FRONT-001_COMPLETION.md)：理解端到端
   SSE 演示。
