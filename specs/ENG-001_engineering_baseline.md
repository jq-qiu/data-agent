# ENG-001 Engineering Baseline

## Goal

为现有 `data-agent` 建立最小、可重复、可验证的工程基线。本 Feature 只处理 Git、开发工具、验证命令和 Baseline 报告，不修改任何业务行为。

## Current State

- `data-agent` 已初始化为独立 Git 仓库，但尚无首个 Commit；
- `.gitignore` 已创建；
- `conf/app_config.yaml` 因包含本地凭据模式而被忽略；
- `pyproject.toml` 已添加 pytest、pytest-asyncio、pytest-cov、Ruff 和 mypy；
- `uv.lock` 已更新；
- 项目 D 盘 `.venv` 已创建；
- pytest、Ruff 和 mypy 已安装，但尚未运行正式 Baseline。

## In Scope

1. 检查 Git 状态和忽略规则；
2. 验证开发工具版本；
3. 运行真实 pytest、Ruff、mypy 基线；
4. 统计错误数量和主要类别；
5. 创建 `ENG-001_BASELINE.md`；
6. 检查暂存内容、敏感信息和 Diff；
7. 建立首个本地工程基线 Commit；
8. 输出完成报告并停止。

## Out of Scope

- AOV 或 Metric Registry 修改；
- Olist、DWD、DWS、Synthetic 和 Ground Truth；
- Metadata、Qdrant、Elasticsearch 业务修改；
- NL2SQL、LangGraph 和 API 业务修改；
- Diagnosis Agent；
- 旧设计包整理；
- 为追求全绿而修复存量业务代码。

## Validation Commands

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git status --short
git diff --cached --stat
git diff --cached --check
```

## Baseline Report Requirements

`ENG-001_BASELINE.md` 至少记录：

```text
Date and Environment
Repository State
Tool Versions
Commands Executed
Pytest Result
Ruff Result
Mypy Result
Known Issues
Acceptance Criteria
```

禁止在报告中写入 API Key、数据库密码、Token 或完整连接串。

## Acceptance Criteria

- [ ] Git 仓库根目录确认；
- [ ] 本地凭据、日志、缓存和虚拟环境未纳入版本控制；
- [ ] pytest 可以执行并记录真实结果；
- [ ] Ruff 可以执行并记录真实结果；
- [ ] mypy 可以执行并记录真实结果；
- [ ] 存量失败未被隐藏；
- [ ] 未修改业务逻辑；
- [ ] `ENG-001_BASELINE.md` 已创建；
- [ ] 暂存内容完成安全和范围检查；
- [ ] 首个本地基线 Commit 已建立；
- [ ] 完成报告已输出；
- [ ] 未自动进入 DOC-001。

## Completion Rule

旧代码不要求全绿。Definition of Done 是工具链能够稳定执行、存量问题被真实测量、敏感配置没有进入版本控制，并形成可复查的工程基线。

