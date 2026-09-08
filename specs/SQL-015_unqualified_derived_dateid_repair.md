# SQL-015 Unqualified Derived-column and Date ID Repair

针对 SQL-014 T03 的完整确定性假设：一次 LLM 修复仍保留冗余派生表，并使用无表名前缀
的派生列与 ISO 日期格式的 `dim_date.date_id` 字符串，导致扁平化与日历归一均未触发。
在两个现有窄修复函数上补齐边界，不新增修复轮数。

## In Scope

- 安全扁平化同时接受外层 `t.order_count` 和无表名前缀 `order_count` 两种派生列引用。
- 在 Calendar Table 为 `dim_date` 时，把 `date_id` 的 `YYYY-MM-DD` 字符串转换为
  `YYYYMMDD` 整数 Literal；仅限与 date_id 比较/IN 的场景。
- T03 实际修复输出经归一与扁平后必须通过原 Validator 与原 Plan。
- 单元测试、设计文档、状态和独立 Completion Report。

## Out of Scope

- 不处理 C05 条件聚合、J02 Group 偏差、N04 指标漂移或 A02 数据库连接问题。
- 不放宽 Validator、不增加修复次数、不修改 Prompt/Metadata/Policy/Golden。
- 不修改 SQL-014 或更早历史评测产物，不运行真实模型复测。
- 对非 dim_date Calendar、Month/Date、其他表或非规范字符串不做转换。

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

- 派生外层别名列和无前缀列均映射回物理列，未使用投影被丢弃。
- `date_id = '2018-05-01'`、反向比较和 IN 列表可转换为整数 `YYYYMMDD`。
- `dim_date.date`/`month`、其他表字段、非规范字符串保持不变。
- T03 实际形状经归一与扁平后通过原 Validator 与 Plan。
- 任何复杂/越界形状继续安全保持原 SQL。
- SQL-014 与历史评测产物未修改；全量 pytest、Ruff、mypy、`git diff --check` 通过。
