# SHOWCASE-001 Completion Report

## Feature

将仓库整理为适合招聘者和技术面试官浏览的 GitHub 展示项目。README 现在从项目价值
出发，依次说明 ODS→DWD→DWS、混合意图路由、NL2SQL、经营诊断、安全边界、SSE
前端、真实评测和运行方式；34份历史 Feature 报告从根目录集中归档到
`docs/reports/`。本 Feature 只改变文档内容和组织，不改变运行逻辑。

## Changed Files

- `README.md`：重写公开展示结构和两张 Mermaid 架构图；
- `docs/reports/README.md`：新增分类报告索引和推荐阅读顺序；
- `docs/reports/*_COMPLETION.md`、`docs/reports/ENG-001_BASELINE.md`：从根目录移动
  34份历史报告；其中33份原文不变，INTERVIEW-001 报告仅移除不公开资料说明；
- `specs/*.md`、`IMPLEMENTATION_STATUS.md`：更新报告路径引用；
- `test/test_documentation_contract.py`：移除对本地面试演示脚本的公开仓库契约依赖，
  继续校验架构讲解中的真实生产边界；
- `INTERVIEW-001_ARCHITECTURE_NARRATIVE.md`：保留公开架构正文，移除面试 Q&A；
- `specs/SHOWCASE-001_public_repository_presentation.md`：冻结本 Feature 范围；
- `docs/reports/SHOWCASE-001_COMPLETION.md`：本完成报告。

未修改 `app/**`、`frontend/src/**`、业务测试逻辑、Prompt、SQL、API、数据、配置、
索引、依赖、锁文件或生成内容。`INTERVIEW-001_DEMO_SCRIPT.md` 按用户要求仅在本地
保留，推送前将从未发布提交及公开分支历史排除。

## Added Dependencies

无。

## Commands Executed

```powershell
.\.venv\Scripts\python.exe -m pytest test\test_documentation_contract.py -q
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
npm test --prefix frontend
npm run build --prefix frontend
git diff --check
git status --short --branch
```

另执行只读检查：

- 对34份移动报告比较移动前 Git blob 与移动后文件哈希；
- 解析当前事实源全部 Markdown 相对链接并检查目标是否存在；
- 扫描当前树和39个 Git 历史提交中的私钥、常见 Token、云访问键与带凭据 URL
  高风险模式；
- 检查 `conf/app_config.yaml` 的忽略状态和 Git 历史；
- 检查已跟踪敏感路径、数据文件、大文件、根目录报告数量和允许修改范围；
- 检查 GitHub CLI 登录、远端同步与未登录公开访问状态。

## Test Results

- 文档契约：23 passed；
- 后端全量回归：338 passed；
- 前端：11 passed；
- Vite生产构建：通过。

## Lint Results

`ruff check .`：通过，0项诊断。

## Type Check Results

`mypy app`：通过，`Success: no issues found in 112 source files`。输出仅包含既有的
未类型化函数体提示，不是错误。

## Evaluation Results

未重新运行 Metadata、NL2SQL 或 Diagnosis Golden Dataset。本 Feature 没有改变模型、
检索、SQL、分析或报告行为；README 只引用已有真实报告中的结果，并明确区分固定
Synthetic 回归、Stub 契约和生产泛化能力。

## Acceptance Criteria

1. README 首屏说明项目目标、开放问数与诊断双链路：通过；
2. ODS→DWD→DWS、意图识别、NL2SQL、诊断、SSE/Trace 均有独立说明：通过；
3. Mermaid 正确区分语义澄清、能力降级和强边界拒绝：通过；
4. 34份历史报告全部进入 `docs/reports/`，根目录历史报告数量为0：通过；
5. 33/34 移动报告内容哈希一致；INTERVIEW-001 报告只有经授权的不公开资料说明
   删除；报告索引遗漏为0：通过；
6. 当前事实源135个 Markdown 文件的仓库内相对链接断链为0：通过；
7. 文档中的评测数字有数据集边界，不宣称未评测生产能力：通过；
8. 全量测试、前端构建、Ruff、mypy 和 Diff 检查通过：通过；
9. GitHub 可见性未经最终确认未修改：通过。
10. README 与文档契约不再依赖本地面试演示脚本或面试 Q&A：通过；待发布 `main`
    当前树及其可达历史均不包含这些资料，本地忽略副本保留：通过。

## Known Issues

- `attribution-analysis-agent-spec/` 是明确标记的旧版参考目录，其中存在13个历史断链；
  当前 V1 事实源没有断链，本 Feature 不扩展范围修复旧版设计资料。
- 仓库当前没有开源许可证。Public 只提供公开可见性，不自动授予复制、修改或分发权；
  许可证类型需要仓库所有者另行选择。
- GitHub CLI 当前未登录，未登录公开访问返回404；用户已授权提交并显式推送 `main`，
  实际推送结果在本次任务最终回复中记录。
- 两个尚未推送的本地提交已从 `origin/main` 安全重建为 `716a288` 与 `414d03d`；
  后续必须使用显式 `git push origin main`，不得使用会推送本地工具内部引用的
  `git push --mirror`。
- 之前 Git push 因无法连接 GitHub 443 端口失败。公开可见性变更需要网络和登录恢复，
  并在最终操作前再次取得用户确认。

## Diff Review Summary

- 运行源代码与业务测试逻辑变更：0；文档契约移除本地脚本依赖；
- 历史报告：33份原文移动；INTERVIEW-001 报告只移除不公开资料说明；
- 根目录 Markdown 从40份减少到6份；
- 报告路径引用更新仅涉及 Markdown；测试文件无需修改；
- 当前事实源 Markdown 断链0，`git diff --check` 通过；
- 未新增 API Key、密码、Token、Cookie、私钥或完整连接串；
- `conf/app_config.yaml`、原始 Olist CSV、数据库、索引、`node_modules`、`dist`、
  lockfile 和评测数据均未进入 Diff；
- 用户已复核并授权提交、推送；GitHub 可见性仍保持不变，等待最终操作确认。
