# SQL-011 Calendar Literal Repair Normalization

针对 SQL-010 C02 的一个明确失败假设：LLM 首次修复后仍可能把 `dim_date.year`、
`quarter` 或 `date_id` 生成为字符串字面量，导致最后一次 Validator 拒绝。修复输出在重新
进入 Validator 前执行一次受 Plan 限定的确定性字面量规范化。

## In Scope

- 仅当 `SchemaLinkingPlan.calendar_table == dim_date` 时启用规范化。
- 将 `dim_date.year` 的四位数字字符串、`quarter` 的 1-4 字符串和 `date_id` 的八位数字
  字符串改为整数 Literal。
- 支持表名、表 Alias、比较两侧和 `IN` 列表。
- 保持 `dim_date.month/date` 的字符串格式，以及非 `dim_date` 字段和值不变。
- LLM 修复输出先规范化，再重新进入现有 Validator；Validator 规则本身不放宽。
- 单元测试、设计文档、状态和独立 Completion Report。

## Out of Scope

- 不处理 T03 必需指标列、C05 GROUP BY 或 J02 结果差异。
- 不增加修复轮数，不放宽只读、Schema、Metric、Join、Grain 或 Plan 校验。
- 不修改 Prompt、Golden、Metadata、Metric Registry、Policy 或历史评测产物。
- 不运行真实模型复测；真实收益必须由后续独立 Rerun 验证。

## Allowed Files

- `app/nl2sql/repair.py`
- `app/agent/nodes/correct_sql.py`
- `test/nl2sql/test_sql_repair.py`
- `docs/03_metadata_and_nl2sql.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/reports/README.md`
- `test/test_documentation_contract.py`
- 本 Spec 与 Completion Report

## Acceptance

- Plan 内 `dim_date.year = '2018'`、Alias/反向比较、Quarter/Date ID `IN` 可确定性转为整数。
- `dim_date.month = '2018-05'`、`date = '2018-05-01'` 和其他表字符串不变。
- 无 Plan、非 `dim_date` Calendar、非规范数字或 SQL 解析失败时安全保持原 SQL。
- 修复节点仍只调用一次 LLM，并把规范化结果送回同一 Validator。
- SQL-010 与历史评测产物未修改。
- 全量 pytest、Ruff、mypy 和 `git diff --check` 通过。
