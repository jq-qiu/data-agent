# DATA-001 Olist Import

## Goal

建立可重复、可审计的 Olist 原始数据获取与 ODS 导入流程，保持源 CSV 原值，不引入 DWD、DWS 或 Synthetic 逻辑。原始文件不进入 Git；版本化清单、导入代码、测试和行数报告进入版本控制。

## Prerequisites

- DOC-001 已完成并通过 Gate 0；
- 官方数据源确定为 Kaggle 上由 Olist 发布的 Brazilian E-Commerce Public Dataset；
- 数据集许可与下载访问条件可被确认；
- 目标存储连接可用且不会在仓库或输出中暴露凭据。

## Inputs

- 官方 Olist 数据集的 9 个 CSV 文件；
- CSV 文件名、表头、字节大小和 SHA-256；
- 项目现有配置与数据库访问体系；
- `docs/02_data_and_metric_design.md` 中 ODS 分层及数据不可覆盖约束。

## Outputs

- 版本化 Olist 源文件清单；
- 忽略本地 Raw 文件的安全规则；
- 可重复运行的 ODS 导入脚本/模块；
- 导入批次和逐表行数记录；
- 主键/源文件基本质量检查；
- DATA-001 专项测试与完成报告；
- 独立 DATA-001 Commit 和 Push。

## In Scope

1. 从 Olist 官方 Kaggle 数据页获取或验证原始压缩包；
2. 验证 9 个预期 CSV、表头、编码、大小和校验和；
3. 原样保存 CSV，并通过 `.gitignore` 阻止原始数据进入版本控制；
4. 按源文件表头建立 ODS Raw 表，不重命名或派生业务字段；
5. 使用批次元数据记录数据集版本、源文件、校验和、源行数、导入行数和状态；
6. 以幂等方式导入，重复同版本和校验和时不得产生重复数据；
7. 对账每个源 CSV 数据行数与导入行数；
8. 使用受控 Fixture/临时存储运行普通单元测试；真实数据库集成单独标识。

## Out of Scope

- DWD、维度表、事实表、DWS、指标计算或 JOIN；
- GMV、AOV、Order Count 对账；
- Synthetic Evidence、Ground Truth 或异常注入；
- Metadata、Qdrant、Elasticsearch、NL2SQL、LangGraph、API 或诊断业务逻辑；
- 修改 Olist 原始值或伪装地域语义；
- 将原始 CSV、压缩包、本地数据库或凭据提交到 Git。

## Acceptance Criteria

- [x] 官方数据源、许可、数据集版本和 9 个源文件已记录；
- [x] 原始下载物和本地数据库未进入版本控制；
- [x] 每个源文件的表头、大小、SHA-256 和数据行数已验证；
- [x] ODS 表严格保留源字段和值；
- [x] 导入批次可审计且失败不会伪装为成功；
- [x] 同版本重复执行幂等；
- [x] 9 个源文件行数与导入行数逐一相等；
- [x] DATA-001 专项测试通过；
- [x] 全量 pytest 不新增失败；
- [x] Ruff 不超过 51 项存量诊断；
- [x] mypy 不超过 40 个存量错误；
- [x] 未实现 DATA-002 或后续能力；
- [x] DATA-001 独立提交并推送。

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest test/data/test_olist_import.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
git diff --check
git status --short
```

数据验收还必须输出逐文件源行数、导入行数和一致性结果。未实际运行真实数据导入时不得宣称通过。

## Completion Rule

只有官方源文件可用、9 个文件逐一完成真实导入与行数对账、专项与回归检查不劣化、完成报告、独立 Commit 和 Push 均成功后，DATA-001 才算完成。任何登录/条款、数据库权限或网络阻塞都必须写入 `IMPLEMENTATION_STATUS.md` 并停止，不得进入 DATA-002。
