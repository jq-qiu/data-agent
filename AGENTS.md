# Coding Agent 工作契约

## 1. 适用范围

本文件适用于本仓库内所有后续 Coding Agent 任务。每个任务只能实现一个明确 Feature。没有用户明确授权时，不得自动进入下一 Feature。

## 2. Source of Truth

读取优先级如下：

1. 用户当前明确要求；
2. 当前 Feature Spec；
3. `IMPLEMENTATION_PLAN.md`；
4. `docs/01_product_scope.md` 至 `docs/06_evaluation.md`；
5. 本文件；
6. `README.md`；
7. 现有代码行为。

`attribution-analysis-agent-spec/` 为旧版设计参考，不是 V1 事实源。若旧文档与根目录文档冲突，以根目录文档为准。

发现事实源之间存在冲突时，应停止相关实现并报告冲突，不能自行创造指标口径、表结构或业务规则。

## 3. 固定工作流

每一个 Feature 严格执行：

```text
Read
→ Inspect Repository
→ Local Plan
→ Implement Current Feature Only
→ Test
→ Diff Review
→ Completion Report
→ Stop
```

开始前必须：

- 完整读取本文件；
- 读取当前 Feature Spec；
- 读取 Spec 指向的直接事实源；
- 检查仓库、测试和未提交变更；
- 列出本轮 In Scope、Out of Scope、允许修改文件和验证命令。

## 4. Scope Control

- 一个任务只能对应一个逻辑 Feature；
- 不得“顺便”实现下游模块；
- 不得为了让检查全绿而无关重构旧代码；
- 不得覆盖或删除无法确认归属的用户修改；
- 前置 Gate 未通过时不得继续下游 Feature；
- 设计文档写着“未来支持”的能力不能当成当前已实现能力。

## 5. Architecture Invariants

1. Client 只管理外部连接与生命周期。
2. Repository 只负责数据访问，不调用 LLM。
3. Agent State 只保存当前请求的可序列化动态状态。
4. Client、Repository、LLM 和 Registry 放在 Agent Context 或依赖容器中。
5. 表、字段、枚举值和 JOIN 关系不能由 LLM 虚构。
6. 指标公式只能来自 Metric Registry。
7. 开放式问数允许使用 LLM NL2SQL；标准诊断方法优先使用结构化 AnalysisTask 和 Controlled Query Builder。
8. SQL 必须通过安全、Schema、只读和粒度校验后才能执行。
9. 数学计算由确定性 Analyzer 完成，LLM 不直接计算贡献率。
10. 没有 Evidence 数据时不得输出对应业务原因。
11. 没有实验或准实验设计时不得输出“导致、造成、证明”等确定因果表述。
12. 每个数字和关键结论必须回溯到 Query Result 或 Analyzer Result。
13. Report Generator 只能消费 Validated Evidence，不得直接消费原始查询结果。
14. `dws_sales_region_daily` 承担整体 Order Count 和 AOV 拆解。
15. `dws_sales_category_daily.category_order_count` 禁止跨品类聚合后解释为整体订单量。
16. 比率指标必须由可加总分子和分母运行时计算，不能直接累加日比例。

## 6. V1 产品边界

V1 支持：

- 单轮自然语言问数；
- 聚合、时间、TopN、多表和对比查询；
- GMV 异常确认；
- `GMV = Order Count × AOV` 两因素拆解；
- 地区与品类变化贡献；
- Traffic、Promotion、Inventory 候选因素验证；
- 证据化诊断报告；
- 数据不足时自动降级。

V1 不支持：

- 省略式多轮追问；
- 严格因果推断；
- 自动补货、调价或营销执行；
- 任意命令执行；
- 完整登录、权限、附件和企业任务平台；
- 无上限自主循环。

## 7. 数据与指标约束

- Olist 原始数据与 Synthetic 数据必须分层保存；
- Synthetic Generator 必须使用固定 Seed 和版本号；
- Ground Truth Event 必须先定义 Evidence 变化，再沿指标链生成结果变化；
- `GMV = SUM(item_sales_amount)`，运费默认不计入 V1 GMV；
- `AOV = GMV / COUNT(DISTINCT order_id)`；
- 整体指标必须使用整体粒度数据计算；
- Olist 地域保留巴西州级语义，不得伪装成国内地区。

## 8. 测试约束

默认验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
```

若存在旧错误：

- 记录真实数量与类别；
- 当前 Feature 不得增加同类错误；
- 未经授权不得扩大范围修复存量错误；
- 任何失败都必须在完成报告中披露。

外部模型、MySQL、Qdrant 和 Elasticsearch 在普通单元测试中应使用 Stub、Mock 或受控 Fixture。真实服务集成测试单独运行并明确标识。

## 9. 安全约束

- 禁止提交或输出 API Key、密码、Token、Cookie 和完整连接串；
- `conf/app_config.yaml` 保持本地忽略；
- 敏感信息扫描只能报告文件路径和问题类型；
- 禁止执行写库、DDL、多语句、系统表访问和文件导出 SQL；
- 不得将用户数据、真实凭据或生产查询结果写入 Golden Dataset。

## 10. 完成报告格式

每个 Feature 完成后必须输出：

```text
Feature
Changed Files
Added Dependencies
Commands Executed
Test Results
Lint Results
Type Check Results
Evaluation Results
Acceptance Criteria
Known Issues
Diff Review Summary
```

没有真实执行评测时必须写“未评测”，不能用设计目标代替实测结果。报告完成后停止。

