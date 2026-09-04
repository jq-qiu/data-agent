# F001 Foundation

## 1 Feature 状态

- 建议初始状态：`ready`
- 前置依赖：无
- 后续消费者：F002 至 F007

## 2 目标

建立可启动、可配置、可迁移、可观测和可测试的最小工程基础。完成后系统尚不执行归因分析，但后续 Feature 可以依赖稳定的配置、数据库事务、认证主体、日志追踪、错误模型和开发环境。

## 3 用户价值

- 开发者可以使用一条清晰命令启动本地依赖和服务。
- 运维人员可以判断进程是否存活、是否准备接收请求以及当前配置版本。
- 认证中心用户可以被安全映射为本地用户主体。
- Coding Agent 有稳定目录和层次约束，不会把业务逻辑放进基础设施层。

## 4 In Scope

1. 前端、API、Worker、领域、Service、Repository、Client、配置、迁移和测试目录骨架。
2. 类型化配置加载，区分环境变量、非密钥配置和 Secret 引用。
3. MySQL 连接生命周期、事务入口和迁移框架。
4. Redis 或队列客户端生命周期接口，开发环境可使用 Stub。
5. 认证中心协议适配边界、当前用户解析和开发认证 Stub。
6. 统一成功/错误响应、`request_id` 和 trace context。
7. 结构化日志、敏感字段脱敏和基础审计接口。
8. `/health/live`、`/health/ready`、`/health/startup`。
9. 本地 Docker Compose、种子配置和 CI 基础命令。

## 5 Out of Scope

- 会话、附件、任务和 WebSocket 业务实现。
- 指标语义层、向量检索和上下文摘要。
- SQL、文件、命令工具。
- Agent、归因算法、报告和正式 Golden Dataset。
- 生产 Kubernetes 资源的完整优化；本 Feature 只定义可容器化契约。

## 6 架构约束

```text
api        只处理协议 认证 输入输出映射
services   编排用例和事务
domain     纯数据模型 状态和规则
repositories  持久化端口和实现
clients    连接 建连 健康和关闭
runtime    配置 日志 追踪 队列启动
```

- Client 不包含业务查询、Prompt 或权限决策。
- Repository 不调用 LLM，不创建模型 Prompt。
- 配置对象启动后不可变；热更新由后续 Feature 构建新快照替换。
- 密钥字段不得有示例真实值，不得出现在 repr、日志或健康响应。
- 所有外部依赖通过接口注入，单元测试可替换为 Stub。

## 7 功能需求

### 7.1 配置

配置至少包含：

```text
app.environment
app.public_base_url
database.dsn_secret_ref
database.pool_size
queue.url_secret_ref
auth.issuer
auth.client_id
auth.client_secret_ref
auth.redirect_uri
storage.backend
storage.root_or_bucket
model.provider
observability.log_level
```

要求：

- `local/test/staging/production` 使用同一 Schema。
- 缺失必填、类型错误、未知高风险键或生产不安全默认值时启动失败。
- 输出配置摘要时只展示非敏感键和值，Secret 只展示引用名和是否成功加载。
- 配置带正整数 `version`，F001 可固定为启动版本；F003 实现热更新。

### 7.2 数据库和迁移

- 提供连接池创建、健康检查、事务上下文和幂等关闭。
- Repository 接收抽象 session/transaction，不自行创建全局连接。
- migration job 独立执行；应用启动只检查版本，不自动做破坏性迁移。
- 建立 F001 必需的 `users`、`system_configs` 基础表，或一次建立第 6 章全表；若一次建全表，也不得提前实现 F002 业务逻辑。

### 7.3 认证边界

定义：

```text
IdentityProvider
  build_authorization_url
  exchange_code
  validate_token
  get_user_info

CurrentUser
  id external_user_id username display_name role status
```

生产实现校验 issuer、audience、签名、过期、state 和 PKCE。测试 Stub 用固定本地用户且只能在 `local/test` 启用，生产检测到 Stub 必须启动失败。

### 7.4 错误与可观测性

- 定义稳定错误结构 `code/message/request_id/details`。
- 未捕获异常返回通用错误，不暴露栈、SQL、路径或上游响应。
- 日志默认 JSON，包含时间、level、service、environment、request_id、trace_id、action、result。
- 提供脱敏器，覆盖 Authorization、Cookie、token、password、api_key、DSN 和签名 URL。

### 7.5 健康端点

- live 只检查进程与事件循环。
- ready 检查配置、MySQL 和必要队列；返回组件状态但不返回 DSN。
- startup 检查迁移版本与初始化完成。
- 健康端点可配置为集群内部访问，不需要暴露详细错误给公网。

## 8 接口合同

```http
GET /health/live
200 {"status":"ok"}

GET /health/ready
200 {"status":"ready","config_version":1,"components":{"database":"ok","queue":"ok"}}
503 {"status":"not_ready","components":{"database":"unavailable"}}

GET /health/startup
200 {"status":"started","migration_version":"..."}
```

认证路由仅实现协议骨架：

```http
GET /auth/login
GET /auth/callback
```

回调成功需 upsert `users` 并建立安全登录态；完整工作台资源由 F002 提供。

## 9 实现步骤

1. 创建目录与依赖边界，增加架构依赖测试，防止反向引用。
2. 定义配置模型、Secret 加载器和启动验证。
3. 定义日志、request/trace 中间件和错误映射。
4. 实现 MySQL Client、事务入口、迁移和测试数据库 fixture。
5. 实现认证端口、开发 Stub 与生产实现骨架。
6. 实现健康端点和优雅启动/关闭。
7. 增加 Compose、示例配置和 CI。

## 10 验收场景

### AC1 最小启动

Given 本地示例配置和依赖已启动，When 执行标准启动命令，Then API 和 Worker 启动，startup/ready 返回成功，日志包含版本且不含秘密。

### AC2 配置失败快速退出

Given 数据库 Secret 缺失或生产环境启用了认证 Stub，When 启动服务，Then 进程以非零码退出并输出脱敏的稳定配置错误。

### AC3 认证映射

Given 合法授权回调，When 系统取得相同 `sub` 两次，Then 只存在一个 users 记录，展示字段可更新，角色不被上游任意字段提升。

### AC4 事务回滚

Given Service 事务中第二次写入失败，When 事务退出，Then 第一次写入也不存在，连接可继续使用。

### AC5 优雅关闭

Given API 正常运行，When 收到终止信号，Then 停止接收新请求、关闭连接池并在宽限期内退出。

## 11 测试要求

- Unit：配置解析、Secret 脱敏、错误映射、认证 claim 映射、日志过滤。
- Integration：MySQL 迁移 up/down 或前滚恢复、事务回滚、连接关闭、用户唯一约束。
- Contract：健康响应和错误 Schema。
- Security：生产禁用 Stub、开放重定向、state/PKCE 校验、日志秘密扫描。
- CI：format、lint、type check、unit、integration、secret scan。

## 12 Gate

- 所有 F001 测试通过。
- 干净环境可以按 README 启动和关闭。
- 数据库迁移可在空库执行，重复运行不会重复创建对象。
- 健康检查不泄露连接信息。
- 仓库搜索无真实密钥、硬编码生产 IP 和用户本机绝对路径。
- git diff 不包含 F002 业务实现。

## 13 完成报告附加项

除通用报告外，列出实际配置键、迁移版本、健康端点、开发 Stub 限制和未接通的真实外部依赖。未执行真实认证联调时必须明确写为 Known Issue。

