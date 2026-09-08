from __future__ import annotations

import re
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE_DOCUMENTS = (
    Path("AGENTS.md"),
    Path("README.md"),
    Path("IMPLEMENTATION_PLAN.md"),
    Path("docs/01_product_scope.md"),
    Path("docs/02_data_and_metric_design.md"),
    Path("docs/03_metadata_and_nl2sql.md"),
    Path("docs/04_analysis_methodology.md"),
    Path("docs/05_agent_workflow.md"),
    Path("docs/06_evaluation.md"),
)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^]]+]\(([^)]+)\)")
SEMANTIC_DESIGN_SPEC = Path("specs/SEM-001_analysis_semantic_context_design.md")


@pytest.mark.parametrize("relative_path", AUTHORITATIVE_DOCUMENTS)
def test_authoritative_document_exists(relative_path: Path) -> None:
    assert (REPOSITORY_ROOT / relative_path).is_file()


@pytest.mark.parametrize("relative_path", AUTHORITATIVE_DOCUMENTS)
def test_local_markdown_links_resolve(relative_path: Path) -> None:
    document_path = REPOSITORY_ROOT / relative_path
    content = document_path.read_text(encoding="utf-8")

    for target in MARKDOWN_LINK_PATTERN.findall(content):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target_path = target.split("#", maxsplit=1)[0]
        assert (document_path.parent / target_path).resolve().exists(), (
            f"Broken local link in {relative_path}: {target}"
        )


def test_gate_zero_facts_are_frozen() -> None:
    agents = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    data_design = (REPOSITORY_ROOT / "docs/02_data_and_metric_design.md").read_text(
        encoding="utf-8"
    )
    metadata_design = (
        REPOSITORY_ROOT / "docs/03_metadata_and_nl2sql.md"
    ).read_text(encoding="utf-8")
    product_scope = (REPOSITORY_ROOT / "docs/01_product_scope.md").read_text(
        encoding="utf-8"
    )

    assert "GMV = SUM(item_sales_amount)" in agents
    assert "AOV = GMV / COUNT(DISTINCT order_id)" in agents
    assert "Order Count = COUNT(DISTINCT order_id)" in readme
    assert "日期 × 客户所在州" in data_design
    assert "日期 × 客户所在州 × 商品品类" in data_design
    assert "category_order_count" in data_design
    assert "禁止跨品类求和" in data_design
    assert "ODS、DWD 原始值不能被 Synthetic Generator 覆盖" in data_design
    assert "Controlled Query Builder" in metadata_design
    assert "单轮 Query API" in product_scope
    assert "严格因果推断 | 不支持" in product_scope
    assert "当前第一个执行任务" not in readme


def test_semantic_planning_design_is_frozen() -> None:
    spec = (REPOSITORY_ROOT / SEMANTIC_DESIGN_SPEC).read_text(encoding="utf-8")
    metadata_design = (
        REPOSITORY_ROOT / "docs/03_metadata_and_nl2sql.md"
    ).read_text(encoding="utf-8")
    methodology = (
        REPOSITORY_ROOT / "docs/04_analysis_methodology.md"
    ).read_text(encoding="utf-8")
    workflow = (REPOSITORY_ROOT / "docs/05_agent_workflow.md").read_text(
        encoding="utf-8"
    )
    evaluation = (REPOSITORY_ROOT / "docs/06_evaluation.md").read_text(
        encoding="utf-8"
    )

    assert "`Semantic Grounding`（语义绑定）" in spec
    assert "`PlannerSemanticContext`（规划器语义上下文）" in spec
    assert "物理表名、列名、JOIN、SQL" in spec
    assert "分析恒等式" in metadata_design
    assert "当前诊断 Parser 已实现确定性规范值和别名绑定" in metadata_design
    assert "客户所在州" in methodology
    assert "`AnalysisTask` 已是类型化工具调用" in methodology
    assert "Planner Model Calls <= 1" in evaluation
    assert "Total Attribution Model Calls <= 2" in evaluation
    assert "Schema Leakage Count = 0" in evaluation
    assert "确定性回退" in workflow


def test_llm_planner_production_boundary_is_documented() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    workflow = (REPOSITORY_ROOT / "docs/05_agent_workflow.md").read_text(
        encoding="utf-8"
    )
    implementation_plan = (
        REPOSITORY_ROOT / "IMPLEMENTATION_PLAN.md"
    ).read_text(encoding="utf-8")

    assert "`CLARIFY-001` 已将三种绑定结果接入生产单轮 API 与前端" in readme
    assert "`PLAN-LLM-001` 已实现可独立调用的 `AnalysisPlanValidator`" in readme
    assert "尚未接入生产 Graph/API" in readme
    assert "未接入生产 Graph/API" in implementation_plan
    assert "尚未接入生产 Graph/API" in workflow


def test_semantic_grounding_implementation_boundary_is_documented() -> None:
    metadata_design = (
        REPOSITORY_ROOT / "docs/03_metadata_and_nl2sql.md"
    ).read_text(encoding="utf-8")
    methodology = (
        REPOSITORY_ROOT / "docs/04_analysis_methodology.md"
    ).read_text(encoding="utf-8")
    evaluation = (REPOSITORY_ROOT / "docs/06_evaluation.md").read_text(
        encoding="utf-8"
    )

    assert "Qdrant 只召回 Catalog 中存在的指标" in metadata_design
    assert "Elasticsearch 只召回允许值列" in metadata_design
    assert "真实/Synthetic 的字段可用性仍由现有 Capability 链决定" in methodology
    assert "Physical Schema Leakage Count = 0" in evaluation
    assert "不代表真实外部检索准确率" in evaluation


def _markdown_section(content: str, heading: str) -> str:
    start = content.index(heading) + len(heading)
    remainder = content[start:]
    next_heading = remainder.find("\n## ")
    return remainder if next_heading < 0 else remainder[:next_heading]


def test_current_status_and_resume_instructions_are_consistent() -> None:
    status = (REPOSITORY_ROOT / "IMPLEMENTATION_STATUS.md").read_text(
        encoding="utf-8"
    )

    assert "SQL-012 Required Metric Subquery Flattening" in _markdown_section(
        status, "## Current Feature"
    )
    assert "SQL-012 Required Metric Subquery Flattening" in _markdown_section(
        status, "## Last Completed Feature"
    )
    assert "SQL-013 Plan Grouping and Calendar Join Repair" in _markdown_section(
        status, "## Next Feature"
    )
    assert "SQL-013 Spec" in _markdown_section(status, "## Resume From")
    assert "Commit and explicitly push the complete SHOWCASE-001" not in status
    assert "GitHub CLI 尚未登录" not in status


def test_semantic_grounding_and_planner_boundaries_are_current() -> None:
    metadata_design = (
        REPOSITORY_ROOT / "docs/03_metadata_and_nl2sql.md"
    ).read_text(encoding="utf-8")
    implementation_plan = (
        REPOSITORY_ROOT / "IMPLEMENTATION_PLAN.md"
    ).read_text(encoding="utf-8")

    assert "`CLARIFY-001` 已把三种绑定结果接入生产单轮 API 与前端" in metadata_design
    assert "`PLAN-LLM-001` 已实现 `BoundedPlannerPolicy`" in metadata_design
    assert "真实模型规划尚未评测，也未接入生产 Graph/API" in metadata_design
    assert "受控检索兜底属于后续 Feature，尚未实现" not in metadata_design
    assert "LLM Planner 尚未实现" not in metadata_design
    assert "绑定能力经 CLARIFY-001 接入生产单轮 API" in implementation_plan
    assert "EVAL-002 NL2SQL Evaluation Integrity" in implementation_plan
    assert "EVAL-003 Primary Failure Classification Completeness" in implementation_plan
    assert "已完成；Evaluator v3" in implementation_plan


def test_architecture_narrative_keeps_production_boundaries_honest() -> None:
    narrative = (
        REPOSITORY_ROOT / "INTERVIEW-001_ARCHITECTURE_NARRATIVE.md"
    ).read_text(encoding="utf-8")
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

    assert "已实现但未接入生产" in narrative
    assert "Planner Model Calls <= 1" in narrative
    assert "标准诊断规划" in narrative
    assert "0 次" in narrative
    assert "[架构讲解](INTERVIEW-001_ARCHITECTURE_NARRATIVE.md)" in readme
