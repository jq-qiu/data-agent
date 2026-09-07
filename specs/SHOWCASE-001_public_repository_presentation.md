# SHOWCASE-001 Public Repository Presentation

## Feature

将当前仓库整理为适合招聘者和技术面试官浏览的公开 GitHub 项目：重写 README
的信息层级，集中归档 Feature 完成报告，并在公开前完成安全、链接、测试与 Diff
复核。此 Feature 只调整展示和文档组织，不改变任何运行逻辑。

## Read

- `AGENTS.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/01_product_scope.md` 至 `docs/06_evaluation.md`
- `INTERVIEW-001_ARCHITECTURE_NARRATIVE.md`
- `INTERVIEW-001_DEMO_SCRIPT.md`
- 根目录全部 `*_COMPLETION.md`、`*_BASELINE.md` 与相关引用

## In Scope

1. 重写根目录 `README.md`，面向首次访问者依次说明：项目定位、核心能力、演示入口、
   总体架构、ODS→DWD→DWS 数据链路、混合意图识别、NL2SQL 链路、诊断链路、
   安全与 Evidence 约束、真实评测结果、快速开始、目录导航和能力边界。
2. README 中保留一张简洁、专业、与真实运行状态一致的 Mermaid 总体架构图；详细
   节点解释继续链接到架构讲解文档，不把 README 写成完整设计说明书。
3. 新建 `docs/reports/`，将根目录 Feature 完成报告和工程基线报告移动到该目录；保持
   原文件名，避免失去 Feature ID 与历史顺序。
4. 更新所有因报告移动而失效的 Markdown、测试或文档契约引用；不修改报告正文中的
   历史结果，不改写评测数字。
5. 新建 `docs/reports/README.md` 作为报告索引，按 Data、Metadata/NL2SQL、Diagnosis、
   API/Frontend/Deployment、Semantics/Planning、Engineering/Documentation 分类。
6. 公开前检查：当前树与 Git 历史中的高风险凭据模式、被跟踪的敏感配置、原始数据、
   大文件、内部链接、工作区和待推送提交。
7. 文档整理完成并经用户复核后，提交、推送；在 GitHub 可见性从 Private 改为 Public
   的最终操作前，再向用户进行一次明确确认。
8. `INTERVIEW-001_DEMO_SCRIPT.md` 和架构文档中的面试 Q&A 仅保留在本地，不进入
   公开分支的当前文件或可达 Git 历史；公开前重写尚未推送的本地提交，并复核
   远端对象列表。

## Out of Scope

- 不修改 `app/**`、`frontend/src/**` 的运行逻辑、Prompt、SQL、API 或页面行为；
- 不修改 ODS、DWD、DWS、Metadata 索引、数据库、配置或数据文件；
- 不新增依赖，不重新生成评测结果；
- 不声称真实外部 Qdrant/Elasticsearch 召回准确率或生产泛化能力；
- 不把未接入生产 Graph/API 的 LLM Planner 描述为线上能力；
- 除为排除本地面试演示脚本与 Q&A 而重写尚未推送的两个本地提交外，不删除历史报告、
  旧版参考目录或已发布 Git 历史；
- 本 Feature 暂不选择或新增开源许可证，除非用户单独确认许可证类型；
- 本 Feature 暂不制作虚构截图、GIF 或运行结果。

## Allowed Files

- `README.md`
- `docs/reports/**`
- 根目录现有 `*_COMPLETION.md`、`*_BASELINE.md`（仅移动）
- 因移动报告而需要更新链接的 `*.md`
- `test/test_documentation_contract.py`（仅当路径契约必须同步时）
- `INTERVIEW-001_DEMO_SCRIPT.md`（仅从待发布历史排除，本地保留）
- `INTERVIEW-001_ARCHITECTURE_NARRATIVE.md`（仅移除 Q&A，保留架构正文）
- `specs/SHOWCASE-001_public_repository_presentation.md`
- `docs/reports/SHOWCASE-001_COMPLETION.md`

## Architecture Diagram Rule

README 总图使用访客能理解的专业名称，明确区分：

- `QUERY`：Metadata Retrieval → Schema Linking → LLM SQL → Validation → Read-only Execution；
- `DIAGNOSIS`：Semantic Grounding → Capability → Deterministic Plan → Controlled Query →
  Analyzer → Validated Evidence → Report；
- 澄清发生在语义绑定阶段，能力降级发生在诊断链路内部；严格边界请求返回受控拒绝，
  不把三者错误地合并为同一个 `UNSUPPORTED` 节点。

## Validation Commands

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
npm test --prefix frontend
npm run build --prefix frontend
git diff --check
```

另执行只读检查：

- README 与全部 Markdown 相对链接检查；
- 当前树及全部 Git 历史的高风险凭据模式扫描，只报告路径和问题类型；
- 禁止路径、原始数据、配置、生成目录和锁文件 Diff 检查；
- `git status --short --branch` 与远端同步状态检查。

## Acceptance Criteria

1. README 首屏能在较短时间内说明“解决什么问题、两条链路、为什么可信”；
2. ODS→DWD→DWS、意图识别、NL2SQL、诊断、SSE/Trace 均有准确但不过度展开的说明；
3. Mermaid 图与真实代码一致，澄清、降级、拒绝的位置正确；
4. 根目录不再散落 Feature 完成报告，报告索引可定位全部历史报告；
5. 报告移动后没有失效的仓库内 Markdown 链接或文档契约；
6. 所有评测数字注明数据集和边界，不把 Synthetic 结果写成生产准确率；
7. 不新增敏感信息、原始 Olist 文件、连接串、构建产物或依赖；
8. 全量验证通过，或者如实记录已存在且未增加的问题；
9. 未经最终确认不修改 GitHub 仓库可见性。
10. 公开分支与其可达 Git 历史均不包含 `INTERVIEW-001_DEMO_SCRIPT.md` 或面试 Q&A，
    本地副本保留。

## Frozen Scope

本 Spec 经用户确认后冻结。实现期间只完成 SHOWCASE-001，不顺带修改业务代码、增加
功能、制作演示数据或处理下一 Feature。
