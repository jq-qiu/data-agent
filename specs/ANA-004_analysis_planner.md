# ANA-004 Analysis Planner

## 1. Feature

把 ANA-002 的结构化诊断问题与 ANA-003 的能力评估确定性地转换为最多四个有序 `AnalysisTask`。Planner 只描述分析意图、参数和依赖，不生成 SQL、不执行查询，也不开放能力评估未支持的方法。

## 2. Source of Truth

1. 用户当前明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md`；
5. `docs/04_analysis_methodology.md`；
6. `docs/05_agent_workflow.md`；
7. `docs/06_evaluation.md`；
8. `specs/ANA-002_analysis_question_parser.md` 与已验收的 Parsed Question Schema；
9. `specs/ANA-003_capability_assessment.md` 与已验收的 Capability Assessment Schema；
10. `AGENTS.md`、`README.md` 和现有代码行为。

## 3. In Scope

- 定义严格、不可变、可 JSON 序列化的 `AnalysisTask` 与 `AnalysisPlan` Schema；
- 固定四类任务：`period_comparison`、`metric_decomposition`、`dimension_contribution`、`candidate_validation`；
- 每类任务最多出现一次，任务总数最多为四个，ID 按 `T1` 至 `T4` 连续分配；
- `period_comparison` 是所有下游任务的 Gate 和直接依赖；
- 维度任务把本次请求且能力可用的维度聚合在一个任务中；
- 候选因素任务把本次请求且对应 Validation 能力可用的因素聚合在一个任务中；
- 能力不支持某方法时只省略对应任务，保留其他可执行任务与 `missing_evidence`；
- Period Comparison 不可用时返回空计划，并根据数据质量状态给出稳定停止原因；
- Planner Node 只从 State 读取可序列化的 `parsed_question` 和 `capability`，只写入可序列化的 `analysis_plan`；
- 使用固定样本验证完整计划、局部降级、Gate 停止、顺序、依赖、上限和无 SQL 边界，并保存真实评测结果。

## 4. Out of Scope

- 不生成 SQL、Query Spec、Query Builder 输入或数据库方言；
- 不连接或查询 MySQL、Qdrant、Elasticsearch；
- 不执行 AnalysisTask，不计算 GMV、AOV、贡献率或候选因素统计量；
- 不验证 Evidence、不生成诊断结论或报告；
- 不修改 DATA、Metadata、NL2SQL、SQL Policy、Query Graph、Agent State 或 API；
- 不开放严格因果推断，不新增四类任务以外的方法；
- 不进入 ANA-005。

## 5. Frozen Planning Contract

完整能力下的计划固定为四个任务：

```json
{
  "plan_version": "analysis-plan-v1",
  "tasks": [
    {
      "task_id": "T1",
      "method": "period_comparison",
      "metric": "gmv",
      "current_period": {"start": "2018-05-01", "end": "2018-05-31"},
      "baseline_period": {"start": "2018-04-01", "end": "2018-04-30"},
      "scope": {"region": null, "category": null},
      "dimensions": [],
      "factors": [],
      "depends_on": []
    },
    {
      "task_id": "T2",
      "method": "metric_decomposition",
      "metric": "gmv",
      "current_period": {"start": "2018-05-01", "end": "2018-05-31"},
      "baseline_period": {"start": "2018-04-01", "end": "2018-04-30"},
      "scope": {"region": null, "category": null},
      "dimensions": [],
      "factors": [],
      "depends_on": ["T1"]
    },
    {
      "task_id": "T3",
      "method": "dimension_contribution",
      "metric": "gmv",
      "current_period": {"start": "2018-05-01", "end": "2018-05-31"},
      "baseline_period": {"start": "2018-04-01", "end": "2018-04-30"},
      "scope": {"region": null, "category": null},
      "dimensions": ["region", "category"],
      "factors": [],
      "depends_on": ["T1"]
    },
    {
      "task_id": "T4",
      "method": "candidate_validation",
      "metric": "gmv",
      "current_period": {"start": "2018-05-01", "end": "2018-05-31"},
      "baseline_period": {"start": "2018-04-01", "end": "2018-04-30"},
      "scope": {"region": null, "category": null},
      "dimensions": [],
      "factors": ["traffic", "promotion", "inventory"],
      "depends_on": ["T1"]
    }
  ],
  "stop_reason": null,
  "missing_evidence": []
}
```

`AnalysisTask` 直接携带 ANA-002 已冻结的 DatePeriod 与 Scope，不改写时间或范围。仅维度任务允许非空 `dimensions`，仅候选因素任务允许非空 `factors`。任何未知字段（包括 `sql`）均拒绝。下游任务只能依赖更早的 `T1`。

`stop_reason` 只允许：

- `null`：至少存在 Period Comparison 任务；
- `INSUFFICIENT_DATA`：Period Comparison 不受支持且数据质量未失败；
- `DATA_QUALITY_FAILED`：Capability 的数据质量为失败。

## 6. Allowed Files

- `specs/ANA-004_analysis_planner.md`；
- `app/diagnosis/__init__.py`；
- `app/diagnosis/planner.py`；
- `app/scripts/evaluate_analysis_planner_v1.py`；
- `data/evaluation/analysis_planner_golden_v1.json`；
- `data/reports/ANA-004_analysis_planner_evaluation.json`；
- `test/diagnosis/test_analysis_planner.py`；
- `docs/reports/ANA-004_COMPLETION.md`；
- `IMPLEMENTATION_STATUS.md`。

## 7. Local Plan

1. 定义任务方法、停止原因、严格 Task 与 Plan Schema；
2. 实现能力白名单、Period Gate、维度/因素交集与固定任务排序；
3. 实现无运行时依赖的 Planner Node；
4. 固定完整与降级样本并生成版本化评测报告；
5. 执行专项/全量 pytest、Ruff、mypy、敏感信息与 Diff Review；
6. 完成报告、独立提交并推送后停止 ANA-004。

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_analysis_planner.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_analysis_planner_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## 9. Acceptance Criteria

- Schema 拒绝未知字段、超过四个任务、重复方法、非连续 ID、前向/未知依赖和与任务类型不符的维度或因素；
- 完整问题与能力输出恰好四个任务，顺序固定且后续任务只依赖 `T1`；
- 任务直接复用已解析 Metric、Period 与 Scope，不发明或改写业务参数；
- 请求的多个维度聚合为一个任务，且只保留 Capability 可用的维度；
- 请求的多个候选因素聚合为一个任务，且只保留对应受支持 Validation 方法的因素；
- Capability 不支持的方法不进入 Plan，Causal 永不进入 Plan；
- Period Comparison 不可用或数据质量失败时返回带稳定停止原因的空计划；
- Plan 与 Node 输出中不存在 SQL、凭据、连接串或运行时依赖；
- 固定样本全部保存真实逐例结果和错误明细；
- 现有 Parser、Capability、Query Graph、SQL、Metadata、数据、数据库和 API 未修改；
- 全量 pytest 不回退，Ruff/mypy 不超过 ANA-003 基线 31/36。

## 10. Completion Boundary

完成 ANA-004 报告、独立提交并推送后停止，不得在本 Feature 中实现 ANA-005 Controlled Query Builder。
