# 部署与运维详细设计

## 1 部署目标

部署方案需要同时满足本地可运行、测试环境可重复、生产环境可横向扩展，并保证长任务、WebSocket、数据库查询、文件处理和配置热更新在滚动发布或依赖故障时保持可恢复。开发环境可简化为 Docker Compose；生产环境建议将 API、任务 Worker、文件解析 Worker 和命令沙箱分开部署。

## 2 运行组件

```text
Browser
  │ HTTPS / WebSocket
  ▼
Ingress or Reverse Proxy
  ├──────────────▶ API instances
  │                   ├─ MySQL control database
  │                   ├─ Redis queue and PubSub
  │                   ├─ Object storage or managed file storage
  │                   └─ Authentication center
  │
  └─ WebSocket upgrade

Task workers
  ├─ Metric and metadata service
  ├─ Enterprise read only data sources
  ├─ LLM and embedding provider
  ├─ File parser workers
  └─ Command sandbox workers optional and disabled by default

All services ──▶ logs metrics traces audit storage
```

### 2.1 组件职责

| 组件 | 职责 | 扩缩容依据 |
|---|---|---|
| Web/API | 认证、资源接口、WebSocket、事件转发 | HTTP QPS、连接数、发送队列延迟 |
| Task Worker | Agent 工作流和工具编排 | 队列深度、运行任务数、模型和 DB 延迟 |
| Parser Worker | Office/PDF/CSV 解析和扫描 | 待解析附件数、CPU、内存 |
| Command Sandbox | 受控转换或报告工具 | 任务数、沙箱资源；默认 0 副本或禁用 |
| MySQL | 控制数据、任务状态、结果和持久事件 | 连接、事务延迟、存储、复制延迟 |
| Redis | 队列、短期分布式协调、跨实例实时分发 | 内存、命中率、消费者滞后 |
| Object Storage | 上传、导出和必要中间产物 | 容量、错误率、请求延迟 |

Redis Pub/Sub 只承担实时加速，不作为唯一事实源。任务状态、结果和可重放关键事件必须先持久化到 MySQL；Redis 丢失后客户端仍可通过 HTTP 快照恢复。

## 3 环境划分

### 3.1 local

- Docker Compose 启动 API、Worker、MySQL、Redis，可选 MinIO。
- 认证中心、LLM 和企业数据源可使用确定性 Stub。
- 文件可以存放在仓库外的绑定数据卷，禁止写入源码目录。
- 提供小型种子数据和两个场景的一键初始化命令。

### 3.2 test and staging

- 与生产使用相同镜像和迁移，不共享生产数据或密钥。
- staging 对接认证中心测试租户、只读脱敏数据源和受限模型账户。
- 执行合同、集成、E2E、Golden、安全和性能测试。

### 3.3 production

- API 与 Worker 至少两个故障域，数据库和对象存储使用高可用方案。
- 仅允许 TLS，网络策略限制服务间和出站访问。
- 密钥来自 Secret Manager，镜像不可写且以非 root 用户运行。
- 命令工具使用独立节点池或外部沙箱，不与 API 进程同容器。

环境配置只保存差异，不复制整份文件；配置 Schema 在 CI 和启动时验证。生产禁用调试模式、自动重载和详细错误栈。

## 4 容器和资源边界

- 镜像固定基础镜像摘要和依赖锁文件，生成 SBOM 并执行漏洞扫描。
- 进程捕获 `SIGTERM`：API 停止接收新任务，Worker 停止领取任务并在宽限期内保存检查点。
- API、Task Worker、Parser 和 Sandbox 使用独立服务账号及最小文件权限。
- 为每类容器设置 CPU、内存、进程数、临时盘和日志上限；禁止无界缓存。
- 上传目录、导出目录和工作目录使用不同逻辑前缀；工作目录按会话隔离。
- 模型和数据源连接池根据副本数计算总连接，避免横向扩容耗尽下游。

## 5 启动 健康与就绪

### 5.1 健康端点

| 端点 | 含义 | 不应检查 |
|---|---|---|
| `/health/live` | 事件循环和进程存活 | 不访问所有外部依赖，避免级联重启 |
| `/health/ready` | 可接收新请求；配置有效、MySQL 可用、必要依赖可用 | 可选数据源和命令沙箱不必阻断全部流量 |
| `/health/startup` | 迁移版本与初始化完成 | 不承担长期监控 |

Worker 就绪需验证队列、控制库、配置快照和必要模型客户端可初始化。单个企业数据源故障通过功能状态暴露，不一定让整个 API 失去就绪。

### 5.2 启动顺序

1. 数据库与 Redis 可用。
2. 由独立 migration job 获取锁并执行迁移。
3. API 和 Worker 启动，读取同一配置版本。
4. readiness 通过后接入流量。
5. Parser 和可选沙箱按功能开关启动。

应用启动不自动执行破坏性迁移；多个副本不得竞争执行迁移。

## 6 数据库迁移发布

采用 expand and contract：

1. **Expand**：新增可空列、表或兼容索引，旧代码仍可工作。
2. **Deploy**：发布可同时读写旧新结构的代码。
3. **Backfill**：限速回填并核验数量和哈希。
4. **Switch**：切换读路径，观察一个发布周期。
5. **Contract**：后续版本再收紧约束或删除旧列。

迁移前自动备份、估算锁表影响并在 staging 演练。大表索引使用在线 DDL 或影子表方案。回滚应用前确认数据库结构向后兼容；不可逆迁移必须有单独审批和恢复脚本。

## 7 任务调度 一致性与恢复

- 数据库活动槽唯一约束保证同会话最多一个 `queued/running` 任务，分布式锁只能作为优化。
- Worker 通过原子状态更新领取任务；任务包含 owner、租约或心跳时，应定期续约。
- 每个可恢复 Agent 节点完成后保存轻量可序列化检查点，Client 和连接对象不进入 State。
- Worker 崩溃后，恢复器扫描过期 `running`：存在安全检查点则重新入队，否则转 `failed/WORKER_LOST`。
- 工具副作用需要幂等。SQL 工具只读；导出以 `task_id + result_version` 固定对象键；保存结果受 `UNIQUE(task_id)` 保护。
- 取消请求写数据库后通过队列或 Pub/Sub 通知 Worker；即便通知丢失，Worker 也在节点与工具轮询点读取取消状态。

## 8 WebSocket 多实例运行

- 连接可落在任意 API 实例，`conversation_id` 不依赖粘性会话。
- Worker 先提交状态和关键事件，再向 Redis channel 发布事件 ID；持有连接的 API 实例读取完整事件并推送。
- 客户端按 `event_id` 去重、按 `event_seq` 检查缺口。断线后使用 `after_event_seq` 重放；超出窗口则拉取 HTTP 快照。
- API 实例发送队列有界，优先保留状态和终态事件，合并相邻文本 delta。
- 滚动发布时先摘除 readiness，通知客户端重连，等待短暂排空后关闭。状态事实不随连接丢失。

## 9 配置热更新的集群一致性

1. 管理员提交 `expected_version`。
2. 配置服务构建完整候选快照，执行 Schema、交叉字段、安全策略和依赖健康校验。
3. 在数据库事务中提交新版本与脱敏 diff。
4. 发布 `config_version_changed` 内部通知；每个实例重新读取并构造不可变快照。
5. 实例加载成功后上报版本；失败则继续旧版本、退出 readiness 并告警。
6. 新任务使用新版本，运行中任务保持创建时版本。

不得通过热更新扩大命令根白名单、修改密钥或取消安全硬限制。集群仪表盘应显示每个实例的当前版本，版本不一致超过 2 分钟触发告警。

## 10 可观测性

### 10.1 指标

建议至少暴露：

```text
http_requests_total and http_request_duration_seconds
websocket_connections and websocket_send_queue_depth
analysis_tasks_total by status scenario model config_version
analysis_task_duration_seconds
analysis_active_tasks and task_queue_depth
tool_calls_total by tool status denial_reason
tool_duration_seconds by tool
sql_rows_scanned sql_rows_returned sql_timeout_total
llm_tokens_total llm_cost_total llm_error_total
attachment_parse_total and attachment_parse_duration_seconds
config_loaded_version and config_reload_total
orphan_files and stuck_tasks
```

标签不得包含用户问题、文件名、SQL、令牌或高基数会话 ID。

### 10.2 日志与追踪

- JSON 结构化日志包含 `request_id/trace_id/user_id_hash/conversation_id/task_id/config_version/action/result`。
- API → 队列 → Worker → 工具 → 模型或数据库保持同一 trace；跨进程使用标准 trace context。
- 错误日志只保存稳定错误码和脱敏摘要，详细原始数据进入受限诊断流程。
- 安全审计与普通应用日志分离，限制修改和读取权限。

### 10.3 初始 SLO

| SLI | 初始目标 | 说明 |
|---|---:|---|
| API 可用性 | 99.9% 月度 | 排除公告维护窗口 |
| 创建会话 P95 | ≤ 500 ms | 不含外部认证跳转 |
| 首状态事件 P95 | ≤ 1 s | 从服务接收消息到 queued/running 事件 |
| WebSocket 恢复成功率 | ≥ 99% | 在保留窗口内 |
| 任务状态一致率 | 100% | 事件终态与数据库一致 |
| 数字一致性 | 100% | 报告关键数字与证据一致 |

端到端分析时延受 SQL、模型和场景复杂度影响，先建立分场景基线再设 P95，避免用单一不现实阈值。

## 11 告警策略

| 告警 | 触发参考 | 首要动作 |
|---|---|---|
| 任务积压 | 队列最老任务等待超过阈值 | 检查 Worker、下游限流和扩容 |
| 卡死任务 | `running` 超过场景最大时长且无心跳 | 请求取消、保存证据、恢复或失败 |
| MySQL 错误 | 错误率或 P95 持续升高 | 降低领取速率，保护数据库 |
| 模型故障 | 5xx/429/超时激增 | 退避、熔断、启用批准的备用模型或降级 |
| WebSocket 缺口 | 重放/快照请求激增 | 检查 Pub/Sub、API 发送队列和代理超时 |
| 配置不一致 | 实例版本分裂超过 2 分钟 | 摘除异常实例并回滚候选版本 |
| 存储容量 | 使用率超过 75%/85% | 清理工作区、扩容、检查异常产物 |
| 安全拒绝激增 | SQL/路径/Prompt 攻击出现异常峰值 | 限流、封禁、保留审计并调查 |

告警必须可操作且有负责人和 Runbook；避免为每次用户可恢复错误发送高优先级告警。

## 12 Runbook

### 12.1 MySQL 不可用

1. API readiness 失败并停止接受会产生状态的请求；现有连接返回稳定 `DEPENDENCY_UNAVAILABLE`。
2. Worker 停止领取新任务，不在内存中继续推进无法持久化的状态。
3. 检查主从切换、连接上限、磁盘和迁移锁。
4. 恢复后核查活动任务唯一约束、状态和事件缺口，再开放流量。

### 12.2 Redis 或实时分发不可用

1. 保持状态与事件写 MySQL，允许任务继续但 UI 可能延迟。
2. 客户端退化为轮询任务快照；界面明确提示实时连接降级。
3. Redis 恢复后不尝试相信丢失的 Pub/Sub，使用事件游标补齐。

### 12.3 模型服务限流

1. 指数退避并遵守上游 Retry-After，限制每任务重试。
2. 达到预算或超时后转失败或输出明确的阶段性结果，不编造完整结论。
3. 只有经过评测批准的兼容模型可自动切换，并记录模型版本。

### 12.4 数据源慢查询

1. 驱动取消查询，标记工具超时并回收连接。
2. 查看 EXPLAIN 摘要、扫描量和并发，必要时临时降低工具并发。
3. 不为绕过超时而扩大权限或取消安全限制；转为要求更小时间范围或预聚合数据。

### 12.5 文件存储满

1. 暂停新上传与导出，分析查询可继续时进入降级模式。
2. 清理已过期 workspace 和失败临时文件，核查异常大对象。
3. 扩容后执行孤儿扫描与文件记录一致性检查。

### 12.6 错误配置发布

1. 由于候选快照原子切换，校验失败应自动保留旧版本。
2. 若新版本引起运行异常，管理员选择上一有效版本执行同样的验证和审计回滚。
3. 检查所有实例配置版本，异常副本退出 readiness 并重新部署。

## 13 备份与恢复

- MySQL 每日全量加持续增量或 binlog，按业务确定 RPO/RTO；至少每季度做一次真实恢复演练。
- 对象存储启用版本或软删除窗口，并与数据库备份时间对齐。
- 配置版本、指标口径、Prompt 版本和迁移文件与代码一同版本化；密钥由密钥系统独立备份。
- 恢复顺序：基础设施 → 数据库到一致点 → 对象存储 → 配置快照 → API/Worker → 一致性扫描。
- 恢复后检查附件引用、结果文件哈希、活动任务、事件序号和过期 token，不直接恢复旧的短时令牌。

## 14 发布与回滚

### 14.1 发布前

- 镜像签名、SBOM、漏洞和密钥扫描通过。
- 数据迁移在 staging 演练，备份和回滚方案确认。
- 两场景 Golden、合同、安全和性能 Gate 通过。
- 配置与 Feature Flag 使用默认安全值，命令工具默认关闭。

### 14.2 发布

1. 先执行向后兼容迁移。
2. 金丝雀发布少量 API 和 Worker，观察错误、延迟、成本和评测探针。
3. 分批扩容新版本；Worker 旧版本停止领取后排空。
4. 完成后核对实例版本、配置版本、迁移版本和核心 SLO。

### 14.3 回滚

- 应用回滚不自动回滚数据库；仅回到仍兼容新增结构的上一镜像。
- 若 Prompt、模型或指标口径引起回归，优先通过已审计版本回滚，运行中任务仍按原版本完成或取消。
- 若出现越权、写库或数据泄漏，立即关闭相关工具和入口，轮换凭据并启动安全响应，不等待常规发布窗口。

## 15 上线验收清单

- [ ] 所有服务非 root 运行，密钥未进入镜像、Git 和日志。
- [ ] 生产数据源账号只读，SQL 和文件策略红队测试通过。
- [ ] MySQL 活动任务唯一约束和外键级联已验证。
- [ ] WebSocket token 单次消费，断线重放和 HTTP 快照可用。
- [ ] Worker 优雅停止、取消和丢失任务恢复已演练。
- [ ] 配置热更新在多实例下原子且可回滚。
- [ ] 上传、导出、workspace 配额和清理任务生效。
- [ ] 仪表盘、告警、Runbook、值班联系人和审计权限已配置。
- [ ] 备份恢复演练成功，RPO/RTO 有实际记录。
- [ ] F007 发布报告有版本、样本数、Gate 结果和已知限制。

