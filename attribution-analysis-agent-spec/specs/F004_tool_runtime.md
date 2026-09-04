# F004 Tool Runtime

## 1 Feature 状态

- 建议初始状态：`ready`
- 前置依赖：F003 accepted
- 后续消费者：F005 至 F007

## 2 目标

提供一组模型无关、确定性、受策略控制、可取消、可审计的分析工具。每个工具可在独立测试 CLI 或集成测试中直接调用；F004 完成前不允许 Agent 使用任意 SQL、路径或命令。

## 3 In Scope

- 统一 Tool 定义、注册、授权、执行、超时、取消、重试、审计和错误模型。
- 统一 `ToolExecutionContext`，包含当前用户、会话、任务、配置版本、权限、预算和取消令牌。
- 指标查询和受控只读 SQL 工具。
- 会话附件读取、结构化文件解析结果读取、文本检索和导出文件工具。
- 可选的命令沙箱适配器，默认关闭。
- 工具结果到 Evidence Candidate 的转换，不负责最终归因结论。
- 工具级资源配额、指标、日志和安全红队测试。

## 4 Out of Scope

- 由 LLM 自主规划工具调用；本 Feature 只提供可调用能力。
- 指标和 JOIN 定义本身，沿用 F003 目录。
- 最终证据接受、归因算法和报告发布。
- 任意终端、任意 Python、宿主机文件浏览和写数据库。

## 5 统一工具合同

### 5.1 ToolDefinition

```json
{
  "tool_name":"metric_query",
  "version":"1.0",
  "description":"按已登记指标、时期、范围和粒度查询",
  "input_schema":{},
  "output_schema":{},
  "required_permissions":["datasource:sales:read"],
  "default_timeout_seconds":30,
  "max_output_bytes":1048576,
  "retry_policy":"safe_transient_only",
  "enabled":true
}
```

### 5.2 ToolExecutionContext

```text
user_id conversation_id task_id tool_call_id trace_id
config_version metric_catalog_version
authorization_scope data_source_scope
workspace_root export_root
deadline cancellation_token
remaining_tool_calls remaining_bytes remaining_cost
```

这些运行时能力放 Agent Context，不进入可持久化 Agent State。工具自行重新校验权限，不信任模型声称的权限或路径。

### 5.3 ToolResult

```json
{
  "tool_call_id":"uuid",
  "tool_name":"metric_query",
  "status":"succeeded",
  "summary":"华南 8 月 GMV 为 92 万元，较 7 月下降 8%",
  "data":{"columns":[],"rows":[]},
  "evidence_candidates":[
    {
      "source_type":"database",
      "source_ref":"query-run:uuid",
      "related_metric":"sales.gmv",
      "period":"2026-08",
      "content_hash":"sha256..."
    }
  ],
  "artifacts":[],
  "metrics":{"duration_ms":320,"rows_returned":2,"bytes":280},
  "error":null
}
```

状态只能是 `succeeded/failed/cancelled/denied`。安全拒绝使用 `denied`，不会伪装成工具故障。

## 6 策略网关

调用顺序固定为：

```text
Schema validate
→ feature enabled
→ identity and ownership
→ permission and data scope
→ task status and cancellation
→ quota and deadline
→ tool-specific policy
→ audit tool_start
→ execute in isolation
→ sanitize and size-limit result
→ audit tool_finish
```

策略网关不调用 LLM。任何异常均返回稳定错误码，例如 `TOOL_INPUT_INVALID`、`TOOL_DENIED`、`TOOL_TIMEOUT`、`TOOL_CANCELLED`、`TOOL_DEPENDENCY_ERROR`、`TOOL_OUTPUT_TOO_LARGE`。

## 7 SQL 和指标查询工具

### 7.1 首选 metric_query

输入使用业务对象而非自由 SQL：

```json
{
  "metric_id":"sales.gmv",
  "current_period":{"start":"2026-08-01","end":"2026-08-31"},
  "baseline_period":{"start":"2026-07-01","end":"2026-07-31"},
  "filters":[{"dimension_id":"region.name","operator":"eq","value_ref":"value:uuid"}],
  "group_by":["store.id"],
  "order_by":[{"field":"delta_value","direction":"asc"}],
  "limit":20
}
```

服务端根据版本化指标公式和 Join Graph 编译参数化 SQL。优先使用该工具可降低模型直接写 SQL 的错误面。

### 7.2 nl2sql_query

仅在 metric_query 无法表达的已批准分析中启用。处理流水线：

1. 单语句 SQL 解析为 AST，解析失败拒绝。
2. 只允许 SELECT/CTE SELECT；拒绝 DML、DDL、事务、存储过程、系统库、文件和网络函数、多语句。
3. 验证所有表列函数在 F003 授权语义层中。
4. 所有用户值转绑定参数；标识符必须来自元数据 ID。
5. 验证 JOIN 路径和基数，标记可能重复聚合。
6. 注入强制权限与时间/组织过滤条件。
7. 强制 LIMIT 或外层限制；执行 EXPLAIN，检查估算扫描量和笛卡尔积。
8. 使用数据库只读账号、只读事务、语句超时和并发限制执行。
9. 规范化、脱敏和截断结果，生成查询运行 ID 与哈希。

禁止仅用正则表达式筛 SQL。禁止把数据库报错原文和连接信息返回模型或前端。

### 7.3 数据质量和贡献工具

提供高层确定性工具：

- `data_quality_check`：完整性、及时性、重复、NULL、状态分布和对账。
- `compare_period`：当前期、基准期、变化值、变化率，处理基准为零。
- `dimension_drilldown`：按单一或批准的组合维度聚合。
- `contribution_analysis`：在互斥同粒度分组内计算变化贡献和对账误差。

贡献工具不跨门店、品类、渠道三套非互斥分解直接求和。输入总体变化与分项结果，输出未解释残差和容差判断。

## 8 文件和文本工具

### 8.1 高层工具

```text
list_conversation_attachments
read_attachment_text
read_tabular_attachment
search_attachment_text
write_report_artifact
get_artifact_metadata
```

工具参数使用 attachment_id/artifact_id，不接受任意宿主机路径。Repository 根据当前用户与会话解析对象键。

### 8.2 安全要求

- 路径规范化后必须位于本会话逻辑根；拒绝绝对路径、`..`、符号链接、reparse point 和设备路径。
- 文件类型由 MIME/魔数确定，Office 禁用宏和外部链接，解析进程无网络并有 CPU/内存/页数/时间限制。
- 表格限制 sheet、行、列和单元格长度；公式默认按文本或缓存值读取，不执行宏。
- 搜索结果包含 attachment_id、页/工作表/行号、片段和内容哈希。
- 不可信附件指令不能改变工具权限或系统策略。

### 8.3 导出

`write_report_artifact` 只写 `exports/{user}/{conversation}`，对象名由系统生成。先写临时对象，完成后校验、计算哈希并原子发布。CSV 防公式注入，HTML/Markdown 清洗脚本和危险 URL。

## 9 命令沙箱

命令工具默认 `enabled=false`。如启用，仅注册高层工具：

```json
{
  "tool_name":"render_report",
  "executable":"固定镜像内二进制",
  "argument_schema":{"type":"object"},
  "network":"none",
  "read_roots":["workspace/current-task"],
  "write_roots":["exports/current-conversation"],
  "timeout_seconds":60
}
```

- 使用 argv 数组与 `shell=false`，禁止管道、重定向、变量展开和命令替换。
- 容器非 root、只读根、最小环境、无宿主挂载、无秘密、进程数和输出受限。
- 取消时终止整个进程树。
- 模型只能选择已注册 tool_name 和符合 Schema 的参数，不能指定 executable。

## 10 重试 超时与取消

- 输入非法、安全拒绝、权限错误和业务无数据不重试。
- 只读、幂等且明确为瞬时的网络错误可按指数退避重试，最大次数由工具定义。
- 每个工具 deadline 不得超过任务剩余 deadline；重试也计入预算。
- SQL 超时调用驱动 cancel；文件解析终止隔离进程；命令终止进程树。
- 收到取消后丢弃迟到结果，不生成 evidence candidate。
- `tool_finish(cancelled)` 后才能将任务转 cancelled，确保 UI 和实际进程一致。

## 11 审计与可观测性

每次调用记录：

```text
tool_call_id task_id user_id_hash tool_name version
config_version policy_decision denial_reason
safe_input_summary started_at finished_at duration
status error_code rows bytes artifacts_hash
```

禁止记录完整 SQL 结果、附件正文、访问令牌和密钥。实时 `tool_start/tool_finish` 使用相同 tool_call_id，结果摘要长度受限。

## 12 验收场景

### AC1 只读 SQL

Given 包含 `DROP`、`INTO OUTFILE`、多语句、系统表或 `FOR UPDATE` 的候选，When 调用 nl2sql_query，Then在连接数据库前返回 denied 并记录稳定原因。

### AC2 粒度保护

Given 订单与一对多明细 JOIN 后直接 SUM 金额，When 策略检查，Then检测粒度放大并拒绝或要求先聚合，不能执行后返回错误金额。

### AC3 路径隔离

Given attachment_id 属于其他会话或对象键含越界路径，When 读取，Then返回 not found/denied，沙箱外文件未被打开。

### AC4 命令注入

Given 参数含 `;`、管道、重定向、`$()` 或额外 executable，When 调用已注册命令工具，Then Schema 或参数映射拒绝，永不启动 shell。

### AC5 取消

Given 慢 SQL、解析器和命令各在运行，When取消任务，Then在规定上限内停止，连接/进程被回收，无迟到证据和产物发布。

### AC6 贡献对账

Given 门店互斥分项和总体变化，When计算贡献，Then返回分项、残差和误差；输入跨维度混合分项时拒绝对账。

## 13 测试要求

- Unit：工具 Schema、策略顺序、错误映射、SQL AST、权限注入、JOIN 基数、路径安全、参数到 argv、贡献公式。
- Integration：真实测试 MySQL 只读账号、EXPLAIN 和 cancel；对象存储原子发布；解析进程限制；可选沙箱。
- Fault Injection：数据库超时、连接断开、对象存储失败、进程卡死、取消通知丢失。
- Security Red Team：SQL 绕过语料、路径穿越、符号链接、压缩炸弹、宏、命令元字符、Prompt 注入。
- Contract：每个 ToolDefinition 输入输出均通过 JSON Schema，WebSocket 工具事件通过实时合同。
- Performance：并发和资源上限下无连接泄漏、孤儿进程和无界内存。

## 14 Gate

- SQL 写入、DDL、多语句、系统库和权限绕过放行数为 0。
- 路径/符号链接逃逸和未登记命令执行成功数为 0。
- 所有工具成功、失败、拒绝、超时、取消均有确定状态和审计。
- 取消测试无孤儿 SQL、解析或命令进程，无迟到 evidence candidate。
- 贡献计算对账误差在规定容差内，跨维度错误使用被拒绝。
- 日志与事件安全扫描无秘密、完整 PII、原始大结果和宿主绝对路径。
- 不包含 Agent 自主循环与最终报告生成。

## 15 完成报告附加项

按工具列出版本、启用状态、权限、超时、输出上限、集成测试依赖和安全红队数量；命令功能若关闭，明确说明而不是用 Mock 宣称生产可用。

