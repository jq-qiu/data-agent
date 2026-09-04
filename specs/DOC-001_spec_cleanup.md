# DOC-001 Specification Freeze

## Goal

冻结 MVP V1 的唯一事实源，清理过时的执行状态引用，并建立可自动验证、可持续恢复的文档与进度基线。本 Feature 只修改文档、进度记录和文档契约测试，不实现任何数据或业务能力。

## Prerequisites

- ENG-001 Engineering Baseline 已完成；
- Gate -1 已通过；
- ENG-001 完成提交已推送到 `origin/main`；
- 根目录 `AGENTS.md` 定义的事实源优先级继续生效。

## Inputs

- `AGENTS.md`；
- `README.md`；
- `IMPLEMENTATION_PLAN.md`；
- `ENG-001_BASELINE.md`；
- `docs/01_product_scope.md` 至 `docs/06_evaluation.md`；
- `specs/ENG-001_engineering_baseline.md`；
- 当前 Git 状态与仓库文件。

## Outputs

- 更新后的 `README.md` 和 `IMPLEMENTATION_PLAN.md`；
- `IMPLEMENTATION_STATUS.md`；
- 可重复运行的文档契约测试；
- `DOC-001_COMPLETION.md`；
- 独立 DOC-001 Commit 和成功 Push。

## In Scope

1. 校验根目录长期事实源及其本地 Markdown 引用；
2. 消除把 ENG-001 描述为当前待执行 Feature 的过时导航；
3. 冻结并交叉检查以下 Gate 0 事实：
   - Source of Truth 优先级；
   - GMV、AOV、Order Count 唯一口径；
   - DWD 与两张诊断 DWS 的粒度；
   - Olist 与 Synthetic 数据边界；
   - V1 单轮、关联诊断、非因果边界；
   - 标准诊断使用 Controlled Query；
4. 建立 `IMPLEMENTATION_STATUS.md` 作为跨执行窗口的恢复入口；
5. 新增文档契约测试，验证关键文件、引用和冻结事实；
6. 运行专项测试、全量回归和工程基线对比；
7. 生成完成报告、独立提交并推送。

## Out of Scope

- DATA-001 或后续 Feature 的数据、代码和测试实现；
- Olist 下载、导入、DDL、ETL、DWS 或 Synthetic 生成；
- AOV、Metric Registry、Metadata、NL2SQL、LangGraph、API 或诊断业务逻辑修改；
- 清理 `attribution-analysis-agent-spec/` 旧设计包；
- 修复 ENG-001 记录的 Ruff 或 mypy 存量问题。

## Acceptance Criteria

- [ ] README 中所有本地 Markdown 引用有效；
- [ ] README 和实施计划不再把 ENG-001 写成当前待执行 Feature；
- [ ] Source of Truth 优先级明确且无冲突；
- [ ] GMV、AOV、Order Count 口径唯一；
- [ ] DWD 与两张诊断 DWS 粒度明确；
- [ ] Olist 与 Synthetic 数据边界明确；
- [ ] V1 单轮和非因果边界明确；
- [ ] 标准诊断 SQL 明确使用 Controlled Query；
- [ ] `IMPLEMENTATION_STATUS.md` 可用于无聊天上下文恢复；
- [ ] DOC-001 专项测试通过；
- [ ] 全量 pytest 不新增失败；
- [ ] Ruff 不超过 51 项存量诊断；
- [ ] mypy 不超过 40 个存量错误；
- [ ] 未修改业务代码；
- [ ] DOC-001 独立提交并推送；
- [ ] 未提前实现 DATA-001。

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest test/test_documentation_contract.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

另执行：

- 本地 Markdown 引用解析；
- 暂存文件范围检查；
- `git diff --cached --stat`；
- `git diff --cached --check`；
- 仅报告路径和问题类型的敏感信息检查。

## Completion Rule

Gate 0 的所有事实经人工审计和自动化契约测试验证，工程基线未恶化，完成报告、独立 Commit 与 Push 均成功后，DOC-001 才算完成。随后才允许为 DATA-001 建立 Mini Spec。
