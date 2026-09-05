# ANA-002 Analysis Question Parser

## 1. Feature

将已由 ANA-001 判定为 `DIAGNOSIS` 的单轮问题解析为严格、可序列化的诊断结构：目标指标、当前期、基期、比较类型、Scope、请求维度与候选因素；无法安全解析时返回固定错误，不猜测未知指标、时间或 Scope。

## 2. Source of Truth

1. 用户当前明确要求；
2. 本 Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md`；
5. `docs/02_data_and_metric_design.md`；
6. `docs/04_analysis_methodology.md`；
7. `docs/05_agent_workflow.md`；
8. `docs/06_evaluation.md`；
9. `conf/meta_config.yaml` 中已验收的 Metric、Region 与 Category 注册信息；
10. `specs/ANA-001_intent_router.md` 与已验收的 Intent Schema；
11. `AGENTS.md`、`README.md` 和现有代码行为。

## 3. In Scope

- 定义严格的日期区间、Scope、Parsed Question、解析错误和解析结果 Schema；
- 只为 V1 `gmv` 诊断生成成功结果；Metric 名称与别名必须来自注入的 Metadata Catalog；
- 解析 `YYYY年M月` 与 `YYYY-MM` 自然月，生成闭区间起止日期；
- 单一明确当前月在没有冲突表达时安全推导紧邻的前一自然月为基期；
- 显式给出两个相邻自然月时按较晚月份作为当前期、较早月份作为基期；
- 出现“相比/相对/基期”等显式比较表达但基期不完整时返回 `MISSING_BASELINE`；
- 缺失、非法、非相邻或多于两个期间时返回 `INVALID_TIME_RANGE`；
- 从注入的 Metadata Catalog 规范化单一 Region/Category Scope，不把别名或自由文本直接作为规范值；
- 解析请求的 `region | category` 维度与 `traffic | promotion | inventory` 候选因素；
- 对固定的 V1 全因素问题，可依据已确认 `DIAGNOSIS` 意图将目标安全限定为 `gmv`；
- 对一般 GMV 原因问题默认请求未被 Scope 固定的 V1 维度和三个候选因素；对拆解/贡献问题只保留明确请求；
- 提供依赖注入式、LangGraph 兼容的节点封装，节点只写入可序列化动态 State；
- 使用固定功能集记录结构、时间、Scope、因素与错误路径的真实结果。

## 4. Out of Scope

- 不调用 LLM，不增加 Prompt 或自由文本修复；
- 不访问 MySQL、Qdrant、Elasticsearch，不检查数据可用区间或 Evidence 是否存在；
- 不实现 Capability Assessment、Supported Methods、Analysis Plan 或任务上限；
- 不生成 SQL，不执行查询，不计算期间变化、Shapley、维度贡献或候选因素分数；
- 不校验 Evidence、不生成诊断报告；
- 不修改现有 Query Graph、NL2SQL、SQL Policy、Metadata 配置、数据、数据库或 API；
- 不支持省略式多轮、季度/周/任意日期区间、非相邻月比较、非 GMV 诊断或严格因果请求；
- 不进入 ANA-003。

## 5. Frozen Output Contract

成功结果中的 `parsed_question` 固定包含：

```json
{
  "target_metric": "gmv",
  "current_period": {"start": "2018-05-01", "end": "2018-05-31"},
  "baseline_period": {"start": "2018-04-01", "end": "2018-04-30"},
  "comparison_type": "previous_period",
  "scope": {"region": null, "category": null},
  "requested_dimensions": ["region", "category"],
  "requested_factors": ["traffic", "promotion", "inventory"]
}
```

失败结果必须是 `parsed_question = null` 加一个固定结构错误。Parser 使用现有工作流错误代码中的 `UNSUPPORTED_INTENT`、`UNKNOWN_METRIC`、`INVALID_TIME_RANGE` 与 `MISSING_BASELINE`，并提供稳定的 `field` 和 `reason` 代码。成功和失败不能同时出现。

## 6. Allowed Files

- `specs/ANA-002_analysis_question_parser.md`；
- `app/diagnosis/__init__.py`；
- `app/diagnosis/question.py`；
- `app/scripts/evaluate_analysis_question_parser_v1.py`；
- `data/evaluation/analysis_question_parser_golden_v1.json`；
- `data/reports/ANA-002_analysis_question_parser_evaluation.json`；
- `test/diagnosis/test_analysis_question_parser.py`；
- `ANA-002_COMPLETION.md`；
- `IMPLEMENTATION_STATUS.md`。

## 7. Local Plan

1. 定义严格 Schema、Catalog Vocabulary 与确定性自然月解析；
2. 实现 Metric、Scope、维度、因素解析及固定错误路径；
3. 实现注入 Parser 的异步节点封装，不连接生产 Graph；
4. 固定成功、等价改写和失败样本，生成版本化评测报告；
5. 执行专项/全量 pytest、Ruff、mypy、敏感信息与 Diff Review；
6. 完成报告、独立提交并推送后停止 ANA-002。

## 8. Verification Commands

```powershell
.\.venv\Scripts\python.exe -m pytest test/diagnosis/test_analysis_question_parser.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_analysis_question_parser_v1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

## 9. Acceptance Criteria

- Schema 严格拒绝未知字段、非法枚举、反向期间和成功/失败混合状态；
- Metric 与 Scope 规范值来自 Metadata Catalog，不接受未注册别名；
- 固定 GMV 诊断问题完整提取 Metric、当前期、基期、Scope、维度和因素；
- 月份边界正确处理月长和跨年；
- 单月安全推导前月，两个相邻月正确排序，非相邻或不完整比较正确失败；
- 未知/非 GMV 指标、非 DIAGNOSIS 输入、多个 Scope 值和缺失时间均输出结构化错误；
- 一般原因、维度贡献、指标拆解和候选因素请求不会互相增加未请求的方法语义；
- 节点输出 JSON 可序列化，State 中不出现 Client、Repository、LLM 或 Registry；
- 固定样本全部保存真实逐例结果和错误明细；
- 现有 Query Graph、SQL、Metadata、数据、数据库和 API 未修改；
- 全量 pytest 不回退，Ruff/mypy 不超过 ANA-001 基线 31/36。

## 10. Completion Boundary

完成 ANA-002 报告、独立提交并推送后停止，不得在本 Feature 中实现 ANA-003 Capability Assessment。
