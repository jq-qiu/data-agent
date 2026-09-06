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


def test_future_llm_planner_is_not_claimed_as_implemented() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    workflow = (REPOSITORY_ROOT / "docs/05_agent_workflow.md").read_text(
        encoding="utf-8"
    )
    implementation_plan = (
        REPOSITORY_ROOT / "IMPLEMENTATION_PLAN.md"
    ).read_text(encoding="utf-8")

    assert "尚未接入生产 Graph、API 或前端" in readme
    assert "LLM Planner 与 Validator 仍计划" in workflow
    assert "`CLARIFY-001` 与 `PLAN-LLM-001` 均需用户明确授权" in (
        implementation_plan
    )


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
