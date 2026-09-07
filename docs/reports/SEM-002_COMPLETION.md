# SEM-002 Completion Report

## Feature

SEM-002 Semantic Registry and Context Builder。

实现了可独立调用的归因语义绑定、Qdrant/Elasticsearch 候选检索适配器、Analysis Semantic Registry 和 `PlannerSemanticContext` Builder。完整规范问题仍优先走现有确定性 Parser；只有未绑定指标、Scope 或显式维度时才尝试受控检索。本 Feature 未接入 LLM Planner、生产 Graph、API 或前端。

## Changed Files

- `specs/SEM-002_semantic_registry_context_builder.md`
- `app/diagnosis/grounding.py`
- `app/diagnosis/semantics.py`
- `app/diagnosis/__init__.py`
- `app/scripts/evaluate_semantic_grounding_v1.py`
- `data/evaluation/semantic_grounding_golden_v1.json`
- `data/reports/SEM-002_semantic_grounding_evaluation.json`
- `test/diagnosis/test_semantic_grounding.py`
- `test/diagnosis/test_planner_semantic_context.py`
- `test/test_documentation_contract.py`
- `docs/03_metadata_and_nl2sql.md`
- `docs/04_analysis_methodology.md`
- `docs/05_agent_workflow.md`
- `docs/06_evaluation.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `SEM-002_COMPLETION.md`

## Added Dependencies

无。

## Commands Executed

```powershell
git status --short --branch
git log -5 --oneline
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_analysis_question_parser.py test/diagnosis/test_capability_assessment.py test/diagnosis/test_analysis_planner.py -q
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_semantic_grounding.py test/diagnosis/test_planner_semantic_context.py -q
.\.venv\Scripts\python.exe -m app.scripts.evaluate_semantic_grounding_v1
.\.venv\Scripts\python.exe -m pytest test/test_documentation_contract.py test/diagnosis/test_analysis_question_parser.py test/diagnosis/test_capability_assessment.py test/diagnosis/test_analysis_planner.py test/diagnosis/test_semantic_grounding.py test/diagnosis/test_planner_semantic_context.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
```

另外对本 Feature 文件执行只报告路径和问题类型的敏感模式扫描。

## Test Results

- 修改前 Parser/Capability/Planner 基线：59 passed；
- SEM-002 新增专项测试：18 passed；
- 相关文档与诊断回归：99 passed；
- 全量 pytest：312 passed。

## Lint Results

- 本 Feature 所有新增/修改 Python 文件的定向 Ruff 检查通过；
- 仓库全量 Ruff 报告 23 个既有诊断，与 SEM-001 基线相同；
- 本 Feature 未扩大范围修改存量问题。

## Type Check Results

- 本 Feature 四个 `app` Python 文件的定向 mypy 检查通过；
- 仓库 mypy 检查 110 个源文件，报告 36 个既有错误，分布在 11 个文件；
- 错误数量与 SEM-001 基线相同。

## Evaluation Results

固定 12 条 Stubbed Qdrant/Elasticsearch 契约样本：

- Exact Match：12/12；
- Binding Status Accuracy：12/12；
- READY Exact：5/5；
- Clarification Exact：4/4；
- Unsupported Exact：3/3；
- Retrieval Policy Match：12/12；
- Physical Schema Leakage Count：0；
- LLM Call Count：0。

真实外部 Qdrant/Elasticsearch 检索未评测。上述结果验证组件契约，不代表真实召回准确率。

## Acceptance Criteria

- 通过：完整规范问题不调用外部检索即可返回 `READY`；
- 通过：缺少指标、时间、基期或存在歧义时返回结构化补充请求；
- 通过：非诊断意图、明确不支持指标和非相邻期间返回 `UNSUPPORTED`；
- 通过：Qdrant 物理字段命中只投影为 Registry 允许的逻辑维度；
- 通过：Elasticsearch 命中只接受允许的地区/品类规范值列；
- 通过：低分候选由适配器过滤，候选分差不足、多 Scope 值和检索故障均失败关闭；
- 通过：检索后仍复用现有 Parser 生成规范 `ParsedAnalysisQuestion`；
- 通过：Analysis Semantic Registry 的指标、维度物理映射和因素指标引用全部通过 Catalog 校验；
- 通过：Context Builder 只输出请求与 Capability 的交集；
- 通过：Capability 的物理缺失字段转换为逻辑限制码，未进入 Planner 上下文；
- 通过：现有 Parser、Capability、Planner 和全量回归通过；
- 通过：未修改数据、数据库、索引、API、前端、NL2SQL、Analyzer、Evidence 或 Report。

## Known Issues

- 新组件尚未接入生产 Graph、Query Service、API 或前端；用户目前看不到 `CLARIFICATION_REQUIRED` 的补充提示；
- 真实 Qdrant/Elasticsearch/Embedding 召回准确率未在本 Feature 中实测；
- LLM Planner 和 `AnalysisPlanValidator` 尚未实现；
- V1 仍不支持省略式多轮补槽；
- 仓库保留 23 个 Ruff 诊断和 36 个 mypy 错误，均为本 Feature 之外的存量问题。

## Diff Review Summary

- 变更只涉及 SEM-002 Spec 允许的语义组件、测试、固定评测、直接文档和完成报告；
- Qdrant/ES 适配器只读现有 `data-agent-metadata-v1` 与 `data-agent-value-v1` 检索函数，不创建、更新或删除索引；
- Parser、Capability、Planner 原文件未修改；生产 Graph、API 和前端未接线；
- `PlannerSemanticContext` 不包含物理表、字段、JOIN、SQL、原始行或 Ground Truth；
- 未修改 GMV、Order Count、AOV 公式和 DWS 粒度约束；
- 未增加 LLM 调用或因果语言能力。

本 Feature 到此停止。`CLARIFY-001` 或 `PLAN-LLM-001` 需要用户明确授权后单独执行。
