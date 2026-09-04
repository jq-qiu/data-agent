# 数据模型详细设计

## 1 目标与边界

本数据模型支撑经营归因分析系统的认证映射、会话、多轮消息、附件、分析任务、结构化结果、上下文摘要、WebSocket 临时令牌、热更新配置和审计日志。业务明细仍保存在企业数仓或用户附件中，本库只保存分析运行所需的控制数据、引用和可审计结果，不复制完整业务数据。

本设计以 MySQL 8.0 为基线。所有时间使用 UTC 写入 `DATETIME(3)`，API 层按用户时区展示；主键使用应用生成的 UUIDv7 字符串 `CHAR(36)`。JSON 字段必须在应用层通过模型校验，数据库层仅承担合法 JSON 校验。

## 2 核心不变量

1. 所有资源均有明确所有者，普通用户只能访问 `user_id` 与当前用户一致的会话及其子资源。
2. 一条用户消息最多创建一个分析任务，通过 `(conversation_id, input_message_id)` 唯一约束保证。
3. 同一会话最多存在一个活动任务。活动任务指 `queued` 或 `running`；再次发送时返回 `409 CONVERSATION_BUSY`，前端应等待、取消原任务或在任务结束后重试。
4. 会话内消息 `seq_no` 严格递增且不可修改，唯一约束为 `(conversation_id, seq_no)`。
5. `success`、`failed`、`cancelled` 为任务终态，终态不可逆。
6. 每个成功任务至多有一份当前结构化结果，结果正文中的数字必须可追溯到证据或工具运行记录。
7. 上下文摘要仅覆盖连续、已完成的消息区间；同一会话的有效摘要区间不得重叠。
8. WebSocket 明文令牌只返回一次，数据库仅保存摘要；令牌短时、单次消费并绑定用户与会话。
9. 运行中的任务固定使用创建时的 `config_version`。配置热更新只影响之后创建的任务，避免一次分析前后口径变化。
10. 会话删除必须级联删除数据库子记录并清理附件、导出和工作目录；失败的文件清理由后台补偿任务重试并告警。

## 3 关系概览

```text
users 1 ── N conversations 1 ── N messages
  │              │                  │
  │              ├── N attachments ┘ 可选关联 message_id
  │              ├── N analysis_tasks 1 ── 0..1 analysis_results
  │              ├── N context_summaries
  │              └── N websocket_tokens
  └── N analysis_tasks

analysis_tasks 1 ── N task_logs
system_configs 独立保存可热更新的非密钥配置
```

## 4 枚举约定

| 类型 | 允许值 | 说明 |
|---|---|---|
| `users.role` | `analyst`、`admin` | 分析用户、系统管理员 |
| `users.status` | `active`、`disabled` | 禁用后拒绝新登录和令牌签发 |
| `conversations.status` | `active`、`archived`、`deleted` | `deleted` 仅用于删除过程和审计，最终硬删除 |
| `messages.role` | `user`、`assistant`、`tool`、`system` | `system` 不接受前端直接写入 |
| `messages.message_type` | `text`、`tool_call`、`tool_result`、`status`、`error` | 历史回放类型 |
| `attachments.parse_status` | `uploaded`、`parsing`、`ready`、`failed` | 只有 `ready` 可进入分析上下文 |
| `analysis_tasks.task_status` | `queued`、`running`、`success`、`failed`、`cancelled` | 有限状态机见第 7 节 |
| `task_logs.log_level` | `DEBUG`、`INFO`、`WARNING`、`ERROR` | 生产默认不持久化 DEBUG |

## 5 表结构

### 5.1 users

认证中心用户在本系统中的本地映射。`external_user_id` 是认证中心稳定主体标识，不使用可能变化的用户名作为关联键。

| 字段 | 类型 | 约束与用途 |
|---|---|---|
| `id` | `CHAR(36)` | 主键 |
| `external_user_id` | `VARCHAR(191)` | 非空、唯一 |
| `username` | `VARCHAR(128)` | 非空，用于展示和检索 |
| `display_name` | `VARCHAR(128)` | 可空 |
| `role` | `VARCHAR(32)` | 非空，默认 `analyst` |
| `status` | `VARCHAR(32)` | 非空，默认 `active` |
| `created_at`、`updated_at` | `DATETIME(3)` | 非空 |

索引：`UNIQUE(external_user_id)`、`INDEX(status, updated_at)`。

### 5.2 conversations

| 字段 | 类型 | 约束与用途 |
|---|---|---|
| `id` | `CHAR(36)` | 主键 |
| `user_id` | `CHAR(36)` | 外键到 `users.id` |
| `title` | `VARCHAR(255)` | 非空，清除控制字符，最长 100 个展示字符 |
| `status` | `VARCHAR(32)` | 非空，默认 `active` |
| `last_message_at` | `DATETIME(3)` | 会话排序使用，可空 |
| `next_seq_no` | `BIGINT UNSIGNED` | 非空，默认 1；事务内锁行分配消息序号 |
| `version` | `INT UNSIGNED` | 乐观锁版本，默认 1 |
| `created_at`、`updated_at` | `DATETIME(3)` | 非空 |

索引：`INDEX(user_id, status, last_message_at DESC)`。所有更新必须包含 `WHERE id=? AND user_id=? AND version=?`。

### 5.3 messages

| 字段 | 类型 | 约束与用途 |
|---|---|---|
| `id` | `CHAR(36)` | 主键 |
| `conversation_id` | `CHAR(36)` | 外键，删除会话时级联 |
| `role` | `VARCHAR(32)` | 非空 |
| `message_type` | `VARCHAR(32)` | 非空，默认 `text` |
| `content` | `MEDIUMTEXT` | 非空；工具结果只保存脱敏摘要，不保存巨量原始数据 |
| `tool_name` | `VARCHAR(128)` | 工具消息可填 |
| `tool_status` | `VARCHAR(32)` | `started/succeeded/failed/cancelled`，普通消息为空 |
| `seq_no` | `BIGINT UNSIGNED` | 会话内顺序号 |
| `client_message_id` | `VARCHAR(128)` | 用户消息幂等键，可空 |
| `created_at` | `DATETIME(3)` | 非空 |

索引与约束：`UNIQUE(conversation_id, seq_no)`、`UNIQUE(conversation_id, client_message_id)`。MySQL 对 `NULL` 允许多行，因此系统消息无需伪造幂等键。

**序号分配：**事务中 `SELECT next_seq_no FROM conversations ... FOR UPDATE`，按需要预留一个或多个序号，更新 `next_seq_no` 后插入消息。禁止使用 `MAX(seq_no)+1`，否则并发时会重复。

### 5.4 attachments

| 字段 | 类型 | 约束与用途 |
|---|---|---|
| `id` | `CHAR(36)` | 主键 |
| `conversation_id` | `CHAR(36)` | 外键，非空 |
| `message_id` | `CHAR(36)` | 外键，可空；上传后可在发送消息时绑定 |
| `file_name` | `VARCHAR(255)` | 用户原始名称，仅展示 |
| `file_path` | `VARCHAR(1024)` | 服务端生成的相对对象键，不接受客户端路径 |
| `file_type` | `VARCHAR(128)` | 服务端嗅探后的 MIME 类型 |
| `file_size` | `BIGINT UNSIGNED` | 字节数 |
| `sha256` | `CHAR(64)` | 内容摘要，用于完整性和可选去重 |
| `parse_status` | `VARCHAR(32)` | 非空，默认 `uploaded` |
| `parse_error` | `VARCHAR(1000)` | 脱敏后的解析错误，可空 |
| `created_at` | `DATETIME(3)` | 非空 |

索引：`INDEX(conversation_id, created_at)`、`INDEX(sha256)`。`file_path` 只能是逻辑对象键，例如 `uploads/{user_id}/{conversation_id}/{attachment_id}.pdf`。

### 5.5 analysis_tasks

| 字段 | 类型 | 约束与用途 |
|---|---|---|
| `id` | `CHAR(36)` | 主键 |
| `conversation_id` | `CHAR(36)` | 外键，非空 |
| `user_id` | `CHAR(36)` | 外键，非空，便于权限过滤与审计 |
| `input_message_id` | `CHAR(36)` | 外键到用户消息，非空 |
| `input_text` | `MEDIUMTEXT` | 创建时的问题快照，非空 |
| `idempotency_key` | `VARCHAR(128)` | 客户端本轮请求键，非空 |
| `task_status` | `VARCHAR(32)` | 非空，默认 `queued` |
| `current_step` | `VARCHAR(128)` | 当前节点，例如 `problem_definition` |
| `config_version` | `BIGINT UNSIGNED` | 创建时固定的配置版本 |
| `attempt_no` | `INT UNSIGNED` | 整体任务重试次数，默认 1 |
| `cancel_requested_at` | `DATETIME(3)` | 收到取消时写入，可空 |
| `started_at`、`finished_at` | `DATETIME(3)` | 可空 |
| `error_code` | `VARCHAR(64)` | 稳定错误码，可空 |
| `error_message` | `VARCHAR(2000)` | 脱敏错误，可空 |
| `version` | `INT UNSIGNED` | 状态乐观锁 |
| `active_slot` | 生成列 | 活动状态为 1，终态为 `NULL` |
| `created_at`、`updated_at` | `DATETIME(3)` | 非空 |

关键约束：

```sql
UNIQUE KEY uq_task_per_message (conversation_id, input_message_id),
UNIQUE KEY uq_task_idempotency (user_id, idempotency_key),
UNIQUE KEY uq_one_active_task (conversation_id, active_slot)
```

`active_slot` 定义：

```sql
active_slot TINYINT GENERATED ALWAYS AS (
  CASE WHEN task_status IN ('queued', 'running') THEN 1 ELSE NULL END
) STORED
```

这一数据库约束是并发安全的最终防线，不能只依赖应用进程内锁。冲突统一映射为 `409 CONVERSATION_BUSY`，并返回现有活动 `task_id`。

### 5.6 analysis_results

| 字段 | 类型 | 约束与用途 |
|---|---|---|
| `id` | `CHAR(36)` | 主键 |
| `task_id` | `CHAR(36)` | 外键、唯一 |
| `conversation_id` | `CHAR(36)` | 外键，非空 |
| `problem_definition` | `TEXT` | 问题定义 |
| `key_metrics_json` | `JSON` | 指标数组 |
| `evidence_list_json` | `JSON` | 证据数组，只保存引用和必要摘要 |
| `conclusion_text` | `MEDIUMTEXT` | 归因结论 |
| `missing_data_text` | `TEXT` | 待补充数据 |
| `next_action_text` | `TEXT` | 至少两条建议，JSON 数组亦可在 API 层表达 |
| `result_markdown` | `LONGTEXT` | 可直接展示的完整报告 |
| `result_file_path` | `VARCHAR(1024)` | 导出文件逻辑对象键，可空 |
| `result_version` | `INT UNSIGNED` | 默认 1 |
| `created_at` | `DATETIME(3)` | 非空 |

约束：`UNIQUE(task_id)`、`INDEX(conversation_id, created_at DESC)`。保存结果与任务转为 `success` 必须处于同一数据库事务中。

### 5.7 context_summaries

| 字段 | 类型 | 约束与用途 |
|---|---|---|
| `id` | `CHAR(36)` | 主键 |
| `conversation_id` | `CHAR(36)` | 外键 |
| `start_seq_no`、`end_seq_no` | `BIGINT UNSIGNED` | 闭区间，满足 `start <= end` |
| `summary_text` | `MEDIUMTEXT` | 保留问题、口径、结论、证据引用和未决事项 |
| `summary_schema_version` | `VARCHAR(16)` | 摘要格式版本 |
| `source_hash` | `CHAR(64)` | 被摘要消息规范化内容的摘要，防止错误复用 |
| `created_at` | `DATETIME(3)` | 非空 |

约束：`UNIQUE(conversation_id, start_seq_no, end_seq_no)`、`INDEX(conversation_id, end_seq_no DESC)`。保存前由服务层在事务内锁会话并检查区间不重叠。摘要不是事实源，发生冲突时以原始消息、工具结果和数据库证据为准。

### 5.8 websocket_tokens

| 字段 | 类型 | 约束与用途 |
|---|---|---|
| `id` | `CHAR(36)` | 主键 |
| `user_id`、`conversation_id` | `CHAR(36)` | 绑定主体和会话 |
| `token` | `CHAR(64)` | 保存随机令牌的 SHA-256/HMAC 摘要，不保存明文 |
| `expires_at` | `DATETIME(3)` | 建议签发后 60 秒失效 |
| `consumed_at` | `DATETIME(3)` | 首次握手时原子写入 |
| `created_at` | `DATETIME(3)` | 非空 |

约束：`UNIQUE(token)`、`INDEX(expires_at)`。消费 SQL 必须同时要求 `consumed_at IS NULL AND expires_at > NOW(3)`；受影响行数为 0 即拒绝连接。

### 5.9 system_configs

| 字段 | 类型 | 约束与用途 |
|---|---|---|
| `id` | `CHAR(36)` | 主键 |
| `config_key` | `VARCHAR(191)` | 唯一，如 `agent.max_iterations` |
| `config_value` | `JSON` | 配置值，不保存 API Key 等密钥 |
| `config_group` | `VARCHAR(64)` | `agent/tool/evaluation/ui` 等 |
| `version` | `BIGINT UNSIGNED` | 每次更新递增 |
| `updated_by` | `CHAR(36)` | 管理员用户 ID |
| `updated_at` | `DATETIME(3)` | 非空 |

索引：`UNIQUE(config_key)`、`INDEX(config_group, updated_at)`。热更新服务读取完整快照，完成 Schema 校验和依赖健康检查后再以原子引用替换；不得逐项修改进程内配置。

### 5.10 task_logs

| 字段 | 类型 | 约束与用途 |
|---|---|---|
| `id` | `BIGINT UNSIGNED` | 自增主键，天然用于事件游标 |
| `task_id` | `CHAR(36)` | 外键 |
| `log_level` | `VARCHAR(16)` | 非空 |
| `log_type` | `VARCHAR(64)` | 如 `state_transition/tool_event/security` |
| `log_content` | `MEDIUMTEXT` | 脱敏的人类可读摘要 |
| `event_type` | `VARCHAR(64)` | 对应实时事件类型，可空 |
| `event_seq` | `BIGINT UNSIGNED` | 任务内事件序号，可空 |
| `trace_id` | `VARCHAR(64)` | 链路追踪 ID |
| `created_at` | `DATETIME(3)` | 非空 |

约束：`UNIQUE(task_id, event_seq)`，其中非实时日志允许 `event_seq=NULL`；索引 `INDEX(task_id, created_at)`、`INDEX(trace_id)`。禁止写入访问令牌、数据库密码、完整 SQL 结果和附件正文。

## 6 推荐 DDL 关键片段

完整迁移应由迁移工具生成，以下片段展示最容易遗漏的约束：

```sql
CREATE TABLE analysis_tasks (
  id CHAR(36) PRIMARY KEY,
  conversation_id CHAR(36) NOT NULL,
  user_id CHAR(36) NOT NULL,
  input_message_id CHAR(36) NOT NULL,
  input_text MEDIUMTEXT NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  task_status VARCHAR(32) NOT NULL DEFAULT 'queued',
  current_step VARCHAR(128) NULL,
  config_version BIGINT UNSIGNED NOT NULL,
  attempt_no INT UNSIGNED NOT NULL DEFAULT 1,
  cancel_requested_at DATETIME(3) NULL,
  started_at DATETIME(3) NULL,
  finished_at DATETIME(3) NULL,
  error_code VARCHAR(64) NULL,
  error_message VARCHAR(2000) NULL,
  version INT UNSIGNED NOT NULL DEFAULT 1,
  active_slot TINYINT GENERATED ALWAYS AS (
    CASE WHEN task_status IN ('queued','running') THEN 1 ELSE NULL END
  ) STORED,
  created_at DATETIME(3) NOT NULL,
  updated_at DATETIME(3) NOT NULL,
  UNIQUE KEY uq_task_per_message (conversation_id, input_message_id),
  UNIQUE KEY uq_task_idempotency (user_id, idempotency_key),
  UNIQUE KEY uq_one_active_task (conversation_id, active_slot),
  KEY ix_task_status_created (task_status, created_at),
  CONSTRAINT fk_task_conversation FOREIGN KEY (conversation_id)
    REFERENCES conversations(id) ON DELETE CASCADE,
  CONSTRAINT fk_task_user FOREIGN KEY (user_id)
    REFERENCES users(id)
);
```

枚举值建议在应用模型与迁移测试中强校验；如使用数据库 `CHECK`，需确认实际 MySQL 版本会执行约束。

## 7 任务状态机与取消

允许的状态变化：

```text
queued  ──▶ running ──▶ success
  │             ├────▶ failed
  └─────────────└────▶ cancelled
```

- Worker 领取任务：`UPDATE ... SET task_status='running', started_at=NOW(), version=version+1 WHERE id=? AND task_status='queued' AND cancel_requested_at IS NULL`。
- 取消请求是幂等操作：首次写入 `cancel_requested_at`；`queued` 可立即转为 `cancelled`，`running` 由执行器在安全检查点取消。
- 工具必须接收取消令牌。数据库查询调用驱动取消或关闭当前语句；文件解析和命令执行终止子进程；不可中断的外部请求完成后丢弃结果，不得继续生成报告。
- 任务转为终态时必须写 `finished_at`，清空活动唯一槽位，并按顺序发布 `task_status`、可选 `error/result_ready`、`done`。
- 服务重启后，超过租约且仍为 `running` 的任务由恢复器判定：有可恢复检查点则重新入队；否则转 `failed`，错误码为 `WORKER_LOST`。不得静默永久停留在 `running`。

## 8 幂等与事务边界

| 操作 | 幂等依据 | 事务边界 |
|---|---|---|
| 创建会话 | `Idempotency-Key + user_id`，服务端幂等记录或响应缓存 | 创建单表事务 |
| 发送用户消息并建任务 | `client_message_id` 与 `idempotency_key` | 锁会话、分配序号、插消息、插任务、更新时间，单事务 |
| 取消任务 | `task_id`，重复取消返回当前终态 | 状态更新与取消日志单事务 |
| 保存结果 | `UNIQUE(task_id)` | 结果 upsert、assistant 消息、任务成功单事务 |
| 附件上传 | `attachment_id + sha256` | 文件先写临时对象，校验后原子提交对象键和记录 |
| 配置重载 | `expected_version` | 只在新快照通过验证后提交版本 |

API 超时后客户端必须复用原 `Idempotency-Key`，不能重新生成。服务端收到相同键且请求体摘要一致时返回首次结果；请求体不同则返回 `409 IDEMPOTENCY_KEY_REUSED`。

## 9 会话删除一致性

删除采用可恢复的三步流程：

1. 在事务内锁定会话，拒绝存在活动任务的删除，或先由用户显式取消并等待终态；将状态置为 `deleted`。
2. 按经过校验的对象键删除 `uploads/{user_id}/{conversation_id}/`、`exports/...` 和 `workspace/...`。路径必须做规范化和归属校验。
3. 文件删除成功后硬删除会话，依赖外键 `ON DELETE CASCADE` 清理消息、附件、任务、结果、摘要、令牌和日志。若第 2 步失败，保留 `deleted` 状态并由清理作业重试，普通查询不再展示。

该流程避免数据库记录已消失但文件永远遗留，也避免文件先删后因活动任务继续写入。管理员审计日志只保存资源 ID、操作者、时间和结果，不保留被删除内容。

## 10 数据保留与容量

- `websocket_tokens`：过期或消费后最多保留 24 小时。
- `workspace` 临时文件：任务终态后 24 小时清理；失败时最多 7 天用于排障，且必须脱敏。
- `task_logs`：按环境配置保留 30 至 90 天，错误和安全事件可单独延长。
- `analysis_results` 与附件：跟随会话生命周期；组织策略可设置最长保留期。
- 大型工具结果只存对象存储引用和摘要，禁止塞入 `messages` 或 `task_logs`。
- 定期检查孤儿对象、无任务结果、无消息附件和长期 `running` 任务，指标暴露给监控系统。

## 11 迁移与兼容

1. 所有迁移须可重复验证但只执行一次；启动服务不自动执行破坏性迁移。
2. 先新增可空列和索引，再发布兼容读写代码，回填后再收紧非空约束。
3. WebSocket Schema、结果 JSON 和摘要格式均带版本；读端至少兼容当前与上一版本。
4. 回滚代码前确认旧版本能够忽略新增列和新事件字段；删除列至少跨两个发布周期。
5. 迁移测试必须覆盖外键级联、活动任务唯一约束、消息序号并发和终态不可逆。

