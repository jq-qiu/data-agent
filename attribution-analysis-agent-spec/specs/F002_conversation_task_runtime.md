# F002 Conversation and Task Runtime

## 1 Feature 状态

- 建议初始状态：`ready`
- 前置依赖：F001 accepted
- 后续消费者：F003 至 F007

## 2 目标

在不依赖真实大模型的前提下，实现登录后的会话管理、消息顺序、附件生命周期、每消息一个任务、同会话单活动任务、取消、状态日志和可恢复 WebSocket。使用确定性 Fake Worker 即可演示完整实时链路。

## 3 In Scope

- `conversations/messages/attachments/analysis_tasks/websocket_tokens/task_logs` 的迁移、领域模型、Repository 和 Service。
- 会话创建、列表、改名、删除、历史消息。
- 附件流式上传、记录、解析状态、删除和下载；实际复杂内容解析留给 F004。
- 用户消息与任务创建的原子事务和幂等。
- 任务领取、状态机、活动任务唯一、取消和丢失任务处理。
- WebSocket token、连接鉴权、事件信封、顺序、重放或快照降级。
- 前端会话列表、聊天区、附件侧栏、实时任务区的最小状态管理。

## 4 Out of Scope

- 指标、元数据、RAG、上下文压缩算法。
- SQL、文件正文解析、命令执行和真实 LLM。
- 归因工作流和最终六部分报告。
- 复杂消息编辑、公开分享和多人共同编辑同一会话。

## 5 必须保持的不变量

1. 普通用户所有资源查询都包含当前 `user_id`，他人资源统一视为不存在。
2. 同一 `conversation_id` 最多一个 `queued/running` 任务，依赖数据库唯一约束而非进程锁。
3. 一条用户消息最多一个任务；创建两者在同一事务中。
4. `seq_no` 通过锁定 conversation 的 `next_seq_no` 分配，不能用 `MAX+1`。
5. 终态不可逆，`done` 是任务最后一个实时事件。
6. 重试必须复用幂等键；相同键不同正文拒绝。
7. WebSocket token 短时、单次、绑定用户与会话，数据库只存摘要。
8. 取消后不得生成成功结果；工具或 Fake Worker 在安全检查点观察取消。

## 6 数据和状态

字段与索引以 `../docs/06_data_model.md` 为准。任务状态机：

```text
queued ──▶ running ──▶ success
  │            ├────▶ failed
  └────────────└────▶ cancelled
```

所有转换使用条件更新：

```sql
UPDATE analysis_tasks
SET task_status = :next, version = version + 1, updated_at = NOW(3)
WHERE id = :id AND task_status = :expected AND version = :version;
```

受影响行数不是 1 时重新读取状态并返回幂等结果或冲突，不能盲目覆盖。

## 7 核心流程

### 7.1 创建和管理会话

- 创建请求带 `Idempotency-Key`，返回稳定 conversation ID。
- 列表按 `last_message_at DESC,id DESC` 游标分页。
- 改名使用版本字段或条件更新。
- 删除前检测活动任务；有活动任务返回 409。用户取消并进入终态后才能删除。
- 删除状态先置 `deleted`，安全清理三个目录后硬删除数据库父记录，失败由补偿任务重试。

### 7.2 上传附件

1. 鉴权和会话状态检查。
2. 流式写临时对象，同时计算大小与 SHA-256。
3. 校验文件名、扩展名、MIME/魔数和基础配额。
4. 原子发布到服务端对象键，写 attachments。
5. F002 可用 Fake Parser 将允许的文本标记为 ready；复杂解析在 F004 实现。

上传响应不暴露宿主机绝对路径。下载和删除再次校验归属。

### 7.3 发送消息并创建任务

客户端通过 WebSocket 发送：

```json
{
  "type":"user_message",
  "client_message_id":"uuid",
  "idempotency_key":"uuid",
  "conversation_id":"uuid",
  "content":"分析库存异常",
  "attachment_ids":[]
}
```

Service 在同一事务中：

1. 锁 conversation 并校验 active、owner。
2. 校验附件属于会话且 ready。
3. 查询幂等键；已存在且请求摘要一致则返回原 message/task。
4. 检查活动任务；存在则返回 `CONVERSATION_BUSY`，不写消息。
5. 分配 `seq_no`，插入 user message。
6. 插入 queued task，并记录创建时 config version。
7. 更新 last_message_at，提交后发布 queued 事件。

数据库唯一约束冲突同样映射为忙碌或幂等响应，覆盖跨实例竞态。

### 7.4 Fake Worker

Fake Worker 用于验证运行时，不包含 Agent：

```text
claim queued
→ task_status running
→ message_start
→ 可配置若干 message_delta/tool_start/tool_finish
→ task_status success 或注入 failed/cancelled
→ done
```

事件必须通过 JSON Schema。Fake Worker 支持可控延迟和故障注入，便于取消与重连测试。

### 7.5 取消

- HTTP 和 WebSocket 取消共用同一 Service。
- queued：写 cancel_requested_at 并直接转 cancelled。
- running：写 cancel_requested_at，通知 Worker；Worker 在短循环和外部调用边界检查并转 cancelled。
- 重复取消返回当前状态；success/failed 不改变。
- 取消完成顺序为 `task_status(cancelled)` → `done(cancelled)`。

### 7.6 重连和恢复

- 关键事件持久化到 task_logs，任务内 event_seq 唯一递增。
- 客户端保存最后 event_seq，重连发送 `resume`。
- 保留窗口内重放缺失事件；无法重放 message delta 时返回 snapshot_required。
- 客户端拉取任务快照、历史消息和结果接口恢复，不依赖内存连接状态。

## 8 API 和事件

实现 `../docs/07_api_and_realtime.md` 中以下接口：

```text
POST /api/chat/create
POST /api/chat/delete
POST /api/chat/update
GET  /api/chat/ls
GET  /api/chat/ls/{conversation_id}
POST /api/attachment/upload
POST /api/attachment/delete
GET  /api/attachment/get
POST /api/chat/ws-token
WS   /api/chat/ws/chat
POST /api/tasks/{task_id}/cancel
GET  /api/tasks/{task_id}
```

F002 不要求 `GET /api/results/{task_id}` 返回真实结果；可返回明确 `RESULT_NOT_READY`。

服务端事件至少实现：`message_start/message_delta/tool_start/tool_finish/task_status/error/done`。`result_ready` 在 F006 产生，但 F002 应能解析和转发其合同类型。

## 9 前端状态规则

- 会话切换后丢弃旧会话连接产生的视觉更新，但不取消旧任务；事件按 conversation/task 路由。
- 发送成功前输入区保持 pending；收到相同 task 的 queued/running 后清空。
- 忙碌错误显示现有任务并提供取消，不静默重发。
- 相同 event_id 不重复追加文本；发现 event_seq 缺口触发 resume。
- 页面刷新后用会话历史和任务快照恢复，不能只依赖浏览器内存。
- 附件只有 ready 可随消息发送，failed 展示安全错误摘要。

## 10 验收场景

### AC1 并发唯一

Given 同一 active 会话，When 两个客户端同时发送不同消息，Then 恰好一个事务成功，另一个返回 `CONVERSATION_BUSY`，数据库中无孤立失败消息且最多一个活动任务。

### AC2 幂等重试

Given 首次响应在客户端观察前丢失，When 使用相同 client_message_id 和 idempotency_key 重试，Then 返回相同 message_id/task_id，不产生重复事件起点。

### AC3 消息顺序

Given 多个系统和工具消息并发写入，When 加载历史，Then seq_no 唯一递增并按原顺序回放。

### AC4 取消运行任务

Given Fake Worker 正在输出，When 用户取消，Then cancel_requested 持久化，Worker 停止，任务最终 cancelled，之后无 message_delta/result_ready，done 最后发送。

### AC5 WebSocket 重放

Given 客户端收到 event_seq 1 至 4 后断线，When 携带 after_event_seq=4 重连，Then 收到缺失事件或 snapshot_required，最终 UI 与任务快照一致且无重复文本。

### AC6 附件归属

Given 用户 A 的 attachment_id，When 用户 B 尝试下载、删除或绑定消息，Then 返回 404，日志记录拒绝但不泄露文件路径。

### AC7 会话删除

Given 无活动任务的会话及三个目录，When 删除成功，Then子记录和目录均消失；模拟文件删除失败时会话处于不可见 deleted 状态并可补偿重试。

## 11 测试要求

- Unit：状态机、序号分配服务、幂等摘要、token 摘要、路径对象键、事件序列器。
- Repository Integration：外键级联、唯一活动槽、消息唯一序号、任务乐观锁、token 单次消费。
- API Contract：所有接口字段、状态码、错误码、分页。
- WebSocket Contract：每类事件通过 Draft 2020-12 Schema，顺序和终态性质测试。
- Concurrency：至少 100 轮双请求竞争和双 Worker 领取。
- Security：IDOR、CSRF/Origin、token 过期/重放、上传大小和类型、路径穿越。
- Browser E2E：登录 Stub → 新建会话 → 上传 → 发送 → 实时过程 → 取消/成功 → 刷新回放 → 删除。

## 12 Gate

- 同会话竞争始终最多一个活动任务。
- 所有幂等测试无重复消息、任务和文件对象。
- queued/running 取消最终进入 cancelled，取消后不发布结果。
- 事件合同 100% 通过，done 始终为最后事件。
- 断线恢复率在测试故障注入中达到 100%。
- 跨用户资源访问成功次数为 0。
- 日志、事件和响应不含明文 WebSocket token、绝对路径和附件正文。
- 实现范围不包含真实 Agent 或工具业务。

## 13 完成报告附加项

报告数据库约束验证方式、并发轮数、重放保留策略、取消最坏延迟、文件清理补偿结果和所有未实现的生产存储适配器。

