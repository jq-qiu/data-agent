# 接口与实时通信详细设计

## 1 设计目标

接口同时服务浏览器工作台和自动化测试，遵循资源归属校验、幂等写入、稳定错误码和可恢复实时通信四项原则。HTTP 用于认证、资源管理、附件传输、任务快照和结果读取；WebSocket 用于提交本轮消息、接收分析增量、工具过程和最终状态。

接口前缀为 `/api`，示例使用 JSON；除上传和下载外，请求与响应 `Content-Type` 为 `application/json; charset=utf-8`。时间使用 RFC 3339 UTC，例如 `2026-09-04T08:30:15.123Z`。

## 2 通用协议

### 2.1 认证与授权

- 浏览器通过认证中心完成 OAuth 2.0 Authorization Code + PKCE 登录。
- 后端优先使用 `HttpOnly; Secure; SameSite=Lax` 会话 Cookie；若部署约束要求 Bearer Token，令牌不得存入 `localStorage`。
- 每个资源接口都执行对象级授权：管理员权限不能替代资源归属过滤，除非调用的是明确的管理员接口并产生审计记录。
- WebSocket 不在 URL 中携带长期访问令牌，只使用 `/api/chat/ws-token` 签发的短时单次令牌。

### 2.2 请求追踪与幂等

- 客户端可传 `X-Request-ID`，服务端不接受非法格式；未传则生成。
- 所有会产生重复副作用的 POST 请求必须传 `Idempotency-Key`，建议为 UUID。
- 相同用户、相同幂等键、相同规范化请求体返回第一次响应；相同键但不同请求体返回 `409 IDEMPOTENCY_KEY_REUSED`。
- 响应头返回 `X-Request-ID`，日志通过该值关联。

### 2.3 成功与错误结构

普通成功响应直接返回业务对象。错误统一为：

```json
{
  "error": {
    "code": "CONVERSATION_BUSY",
    "message": "当前会话已有分析任务正在执行",
    "request_id": "01991...",
    "details": {
      "active_task_id": "01991..."
    }
  }
}
```

稳定错误码包括：

| HTTP | 错误码 | 场景 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 字段、格式或状态非法 |
| 401 | `UNAUTHENTICATED` | 未登录或会话失效 |
| 403 | `FORBIDDEN` | 角色不足或资源不属于当前用户 |
| 404 | `RESOURCE_NOT_FOUND` | 不泄露他人资源是否存在 |
| 409 | `CONVERSATION_BUSY` | 同会话已有活动任务 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 幂等键对应不同请求体 |
| 409 | `STATE_CONFLICT` | 乐观锁或任务终态冲突 |
| 413 | `FILE_TOO_LARGE` | 超过上传限制 |
| 415 | `UNSUPPORTED_FILE_TYPE` | MIME 或魔数不允许 |
| 422 | `ATTACHMENT_NOT_READY` | 附件尚未解析完成 |
| 429 | `RATE_LIMITED` | 用户或组织限流 |
| 503 | `DEPENDENCY_UNAVAILABLE` | 数据源、模型或队列不可用 |

## 3 认证接口

### 3.1 GET /auth/login

生成 `state`、PKCE verifier/challenge 并跳转认证中心。`return_to` 只允许站内相对路径，防止开放重定向。

### 3.2 GET /auth/callback

校验 `state` 和授权码，服务端换取令牌，以认证中心 `sub` 映射 `users.external_user_id`，建立登录态后 302 跳转工作台。错误只展示稳定错误码，不把上游令牌或响应原文返回浏览器。

## 4 会话和消息接口

### 4.1 POST /api/chat/create

请求：

```json
{"title": "华南销售下降分析"}
```

响应 `201`：

```json
{
  "conversation_id": "01991...",
  "title": "华南销售下降分析",
  "status": "active",
  "created_at": "2026-09-04T08:30:15.123Z"
}
```

标题为空时可生成“新分析会话”，但自动标题生成失败不能阻塞会话创建。

### 4.2 POST /api/chat/update

请求包含 `conversation_id`、`title`、可选 `version`。只允许 `active/archived` 会话改名；返回更新后的对象。版本冲突返回 `409 STATE_CONFLICT`。

### 4.3 POST /api/chat/delete

请求：`{"conversation_ids":["01991..."]}`。批量上限建议 50；逐项返回 `deleted/not_found/conflict`。存在活动任务的会话返回冲突，调用者应先取消任务。删除流程和补偿策略见数据模型文档。

### 4.4 GET /api/chat/ls

查询参数：`status=active|archived`、`cursor`、`limit`，`limit` 默认 20、最大 100。按 `last_message_at DESC, id DESC` 游标分页。

### 4.5 GET /api/chat/ls/{conversation_id}

返回会话信息和消息分页：

```json
{
  "conversation": {"conversation_id":"01991...","title":"...","status":"active"},
  "messages": [
    {
      "message_id":"01992...",
      "role":"user",
      "message_type":"text",
      "content":"为什么本月华南销售额下降？",
      "seq_no":17,
      "attachments":[],
      "created_at":"2026-09-04T08:31:00.000Z"
    }
  ],
  "next_cursor": null
}
```

历史回放以 `seq_no` 排序。工具原始输出不会直接回放，只返回脱敏摘要和结果引用。

## 5 附件接口

### 5.1 POST /api/attachment/upload

使用 `multipart/form-data`，字段包括 `conversation_id`、`file`。上传流程为临时区流式写入、大小限制、MIME 与魔数校验、恶意内容扫描、计算 SHA-256、原子移动、创建记录、异步解析。

响应 `202`：

```json
{
  "attachment_id":"01993...",
  "file_name":"库存明细.xlsx",
  "file_path":"uploads/{user}/{conversation}/{attachment}.xlsx",
  "parse_status":"uploaded"
}
```

`file_path` 是逻辑对象键，不是宿主机绝对路径，不应由客户端拼接或回传修改。

### 5.2 POST /api/attachment/delete

请求 `{"attachment_id":"01993..."}`。删除为幂等操作；附件已被运行中任务固定引用时返回 `409 STATE_CONFLICT`，任务结束后可删。

### 5.3 GET /api/attachment/get?attachment_id=...

验证所有权后以受控下载响应返回，设置 `Content-Disposition: attachment`、`X-Content-Type-Options: nosniff`。对象存储场景可返回分钟级签名地址，但地址不得写日志。

## 6 任务与结果接口

### 6.1 POST /api/tasks/{task_id}/cancel

补充的取消接口。无需请求体，必须带 `Idempotency-Key`。响应 `202`：

```json
{
  "task_id":"01994...",
  "task_status":"running",
  "cancel_requested":true
}
```

对终态任务重复调用返回 `200` 和当前终态。取消是协作式的，不保证在响应返回时所有外部调用已经退出；客户端继续等待 `task_status=cancelled` 和 `done`。

### 6.2 GET /api/tasks/{task_id}

```json
{
  "task_id":"01994...",
  "task_status":"running",
  "current_step":"dimension_drilldown",
  "started_at":"2026-09-04T08:31:02.000Z",
  "finished_at":null,
  "error_message":null,
  "config_version":12
}
```

此接口是 WebSocket 断线后的权威快照来源。

### 6.3 GET /api/results/{task_id}

仅当结果存在时返回 `200`；尚未生成返回 `404 RESULT_NOT_READY`。响应包含：

```json
{
  "result_id":"01995...",
  "problem_definition":"...",
  "key_metrics":[
    {"metric_name":"GMV","metric_value":920000,"metric_unit":"元","metric_period":"2026-08"}
  ],
  "evidence_list":[
    {
      "source_type":"database",
      "source_name":"dws_store_sales_day",
      "evidence_text":"A、B 门店合计贡献下降额的 61%",
      "related_metric":"GMV",
      "confidence":0.91,
      "source_ref":"tool-call:01996..."
    }
  ],
  "conclusion_text":"...",
  "missing_data_text":"缺少促销变更记录",
  "next_action_text":["核对 A、B 门店补货记录","补充促销计划后复算"],
  "result_markdown":"...",
  "result_file": {"attachment_id":null,"download_url":"/api/results/01994.../download"}
}
```

建议补充 `GET /api/results/{task_id}/download`，由后端鉴权后流式返回导出文件。

## 7 配置热更新接口

### POST /api/admin/reload

仅 `admin` 可调用。请求可包含 `expected_version` 和 `dry_run`：

```json
{"expected_version":12,"dry_run":false}
```

处理顺序：读取候选配置 → Schema 校验 → 跨字段校验 → 依赖连通性检查 → 计算脱敏差异 → 原子替换配置快照 → 记录管理员、版本与结果。

成功响应：

```json
{
  "status":"reloaded",
  "message":"配置已通过校验并生效",
  "previous_version":12,
  "current_version":13,
  "changed_keys":["agent.max_iterations","tool.sql.timeout_seconds"]
}
```

失败时旧配置继续生效。密钥、数据库密码和 OAuth client secret 不允许通过该接口修改，只能由密钥管理系统轮换。运行中的任务继续使用原 `config_version`。

## 8 WebSocket 建连

### 8.1 签发临时令牌

`POST /api/chat/ws-token` 请求：

```json
{"conversation_id":"01991..."}
```

响应：

```json
{"websocket_token":"raw-once-token","expires_in":60}
```

服务端校验会话所有权，保存令牌摘要。令牌只能消费一次，过期、重复使用或绑定会话不一致均以策略关闭连接。

### 8.2 握手

连接地址：

```text
WS /api/chat/ws/chat?websocket_token=...&conversation_id=...
```

浏览器 WebSocket API 难以自定义握手头，因此允许短时令牌作为查询参数；反向代理访问日志必须对其脱敏。成功后服务端首先发送 `connection_ready` 可选控制帧；业务事件必须符合 `contracts/realtime-event.schema.json`。

### 8.3 客户端消息

客户端发送消息也采用带版本的信封：

```json
{
  "type":"user_message",
  "client_message_id":"01997...",
  "idempotency_key":"01998...",
  "conversation_id":"01991...",
  "content":"为什么本月华南销售额下降？",
  "attachment_ids":["01993..."]
}
```

服务端在一个事务中写用户消息并创建任务。若会话已有活动任务，返回控制错误 `CONVERSATION_BUSY`，不得写入一条没有任务的孤立用户消息。

客户端还可发送：

- `{"type":"ping","nonce":"..."}`：服务端回 `pong`。
- `{"type":"resume","task_id":"...","after_event_seq":18}`：请求缺失事件；无法完整重放时返回 `snapshot_required`，客户端改用 HTTP 快照。
- `{"type":"cancel_task","task_id":"...","idempotency_key":"..."}`：与 HTTP 取消语义相同。

## 9 服务端实时事件

所有事件共享以下字段：

```json
{
  "schema_version":"1.0",
  "event_id":"01999...",
  "event_type":"task_status",
  "conversation_id":"01991...",
  "task_id":"01994...",
  "event_seq":3,
  "emitted_at":"2026-09-04T08:31:03.000Z",
  "trace_id":"3f6...",
  "payload":{}
}
```

必需业务事件如下：

| 事件 | payload 关键字段 | 发送时机 |
|---|---|---|
| `message_start` | `message_id`、`input_message_id`、`config_version` | 本轮助手输出开始 |
| `message_delta` | `message_id`、`delta_text` | 增量文本；不得携带隐藏思维链 |
| `tool_start` | `tool_call_id`、`tool_name`、`safe_input_summary` | 工具通过授权并开始执行 |
| `tool_finish` | `tool_call_id`、`tool_name`、`tool_status`、`tool_result_summary`、`duration_ms` | 工具结束；结果必须脱敏 |
| `task_status` | `task_status`、`current_step` | 状态或阶段发生变化 |
| `result_ready` | `result_id`、`result_version` | 结构化结果事务提交完成 |
| `error` | `error_code`、`error_message`、`retryable` | 本轮失败或可恢复异常 |
| `done` | `finished_at`、`final_status` | 本轮最后一个事件 |

`message_delta` 是面向用户的阶段性说明或报告正文，不输出模型内部推理、系统 Prompt、数据库凭据和原始敏感行。

## 10 顺序 重放与去重

- `event_seq` 在单个任务内从 1 严格递增，由持久化事件记录或事务序列分配；不同任务之间不承诺全局顺序。
- 交付语义为至少一次。客户端按 `event_id` 去重，按 `(task_id,event_seq)` 排序；发现缺口应发起 `resume`。
- 服务端必须先持久化关键状态，再发布事件，避免界面显示成功而数据库仍未提交。
- `result_ready` 只能在结果提交后发送；`done` 必须是任务最后一条事件，且其 `final_status` 与任务快照一致。
- `failed` 正常序列为 `task_status(running)` → `error` → `task_status(failed)` → `done(failed)`。
- `cancelled` 正常序列为取消确认 → 工具结束或被终止 → `task_status(cancelled)` → `done(cancelled)`，不得发送 `result_ready`。
- 重连保留窗口建议 24 小时。超出窗口或消息增量未持久化时，服务端返回快照要求；客户端通过 `GET /api/tasks/{id}`、历史消息和结果接口恢复。

## 11 心跳 背压与连接关闭

- 服务端每 25 秒发送 ping，连续两个周期无响应关闭连接。
- 每个连接设置有界发送队列。队列接近上限时合并相邻 `message_delta`；状态、错误、工具完成、结果和 `done` 不得丢弃。
- 单个用户限制连接数和每分钟消息数，超限返回 `RATE_LIMITED`。
- 关闭码建议：`4401` 未认证、`4403` 无权限、`4408` 令牌过期、`4429` 限流、`1012` 服务重启。
- 服务滚动发布前停止接收新任务，发送重连提示，等待或取消本实例拥有的工具调用，再关闭连接。

## 12 API 与实时协议验收

1. 两个并发请求向同一会话发消息，只能创建一个活动任务；失败请求不产生孤立消息。
2. 客户端超时后复用幂等键，得到相同 `message_id` 和 `task_id`。
3. WebSocket 断线重连后可从 `after_event_seq` 补齐或通过快照恢复，且不会重复渲染。
4. 取消 `queued` 和 `running` 任务均最终进入 `cancelled`，之后无 `result_ready`。
5. 配置重载失败时旧快照仍可用；成功后新任务使用新版本，运行中任务保持旧版本。
6. 所有事件通过 JSON Schema 合同测试，事件顺序满足本章规则。
7. 普通用户用自己的凭据读取他人会话、任务、附件、结果时统一得到 404，不泄露资源存在性。

