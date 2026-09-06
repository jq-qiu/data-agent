from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import app.diagnosis.grounding as grounding_module
from app.diagnosis.grounding import (
    BindingField,
    DimensionGroundingCandidate,
    MetricGroundingCandidate,
    QdrantElasticsearchCandidateRetriever,
    SemanticBindingResult,
    SemanticBindingStatus,
    SemanticCandidateBundle,
    SemanticGrounder,
    ValueGroundingCandidate,
)
from app.diagnosis.intent import Intent
from app.diagnosis.question import AnalysisDimension, AnalysisScope
from app.diagnosis.semantics import AnalysisSemanticRegistry
from app.metadata.catalog import load_catalog
from app.metadata.retrieval import RetrievedItem
from app.scripts.evaluate_semantic_grounding_v1 import evaluate

ROOT = Path(__file__).parents[2]


class StubRetriever:
    def __init__(
        self,
        result: SemanticCandidateBundle | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or SemanticCandidateBundle()
        self.error = error
        self.calls = 0

    async def retrieve(self, question: str) -> SemanticCandidateBundle:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(ROOT / "conf/meta_config.yaml")


@pytest.fixture(scope="module")
def registry(catalog) -> AnalysisSemanticRegistry:
    return AnalysisSemanticRegistry.from_catalog(catalog)


@pytest.mark.asyncio
async def test_exact_binding_is_ready_without_external_retrieval(catalog, registry) -> None:
    retriever = StubRetriever()
    grounder = SemanticGrounder(catalog, registry, retriever)

    result = await grounder.bind(
        "为什么2018年5月圣保罗州GMV下降？",
        Intent.DIAGNOSIS,
    )

    assert result.status is SemanticBindingStatus.READY
    assert result.parsed_question is not None
    assert result.parsed_question.scope == AnalysisScope(region="SP")
    assert result.retrieval_used is False
    assert retriever.calls == 0


@pytest.mark.asyncio
async def test_missing_time_requests_clarification_without_retrieval(catalog, registry) -> None:
    retriever = StubRetriever()

    result = await SemanticGrounder(catalog, registry, retriever).bind(
        "为什么GMV下降？",
        Intent.DIAGNOSIS,
    )

    assert result.status is SemanticBindingStatus.CLARIFICATION_REQUIRED
    assert result.missing_fields == (BindingField.TIME,)
    assert result.reason == "missing_current_period"
    assert result.suggested_question is not None
    assert retriever.calls == 0


@pytest.mark.asyncio
async def test_qdrant_metric_candidate_can_complete_supported_metric(
    catalog,
    registry,
) -> None:
    retriever = StubRetriever(
        SemanticCandidateBundle(
            metrics=(
                MetricGroundingCandidate(
                    metric_id="gmv",
                    score=0.91,
                    supported_for_diagnosis=True,
                ),
                MetricGroundingCandidate(
                    metric_id="order_count",
                    score=0.72,
                    supported_for_diagnosis=False,
                ),
            )
        )
    )

    result = await SemanticGrounder(catalog, registry, retriever).bind(
        "为什么2018年5月营业额下降？",
        Intent.DIAGNOSIS,
    )

    assert result.status is SemanticBindingStatus.READY
    assert result.parsed_question is not None
    assert result.parsed_question.target_metric == "gmv"
    assert result.retrieval_used is True
    assert retriever.calls == 1


@pytest.mark.asyncio
async def test_clear_unsupported_metric_candidate_is_rejected(catalog, registry) -> None:
    retriever = StubRetriever(
        SemanticCandidateBundle(
            metrics=(
                MetricGroundingCandidate(
                    metric_id="order_count",
                    score=0.94,
                    supported_for_diagnosis=False,
                ),
                MetricGroundingCandidate(
                    metric_id="gmv",
                    score=0.70,
                    supported_for_diagnosis=True,
                ),
            )
        )
    )

    result = await SemanticGrounder(catalog, registry, retriever).bind(
        "为什么2018年5月订单表现下降？",
        Intent.DIAGNOSIS,
    )

    assert result.status is SemanticBindingStatus.UNSUPPORTED
    assert result.reason == "metric_not_supported"
    assert result.parsed_question is None


@pytest.mark.asyncio
async def test_close_metric_candidates_require_clarification(catalog, registry) -> None:
    retriever = StubRetriever(
        SemanticCandidateBundle(
            metrics=(
                MetricGroundingCandidate(
                    metric_id="gmv",
                    score=0.90,
                    supported_for_diagnosis=True,
                ),
                MetricGroundingCandidate(
                    metric_id="order_count",
                    score=0.88,
                    supported_for_diagnosis=False,
                ),
            )
        )
    )

    result = await SemanticGrounder(catalog, registry, retriever).bind(
        "为什么2018年5月经营指标下降？",
        Intent.DIAGNOSIS,
    )

    assert result.status is SemanticBindingStatus.CLARIFICATION_REQUIRED
    assert result.ambiguous_fields == (BindingField.METRIC,)
    assert result.reason == "ambiguous_metric"


@pytest.mark.asyncio
async def test_elasticsearch_category_value_is_canonicalized(catalog, registry) -> None:
    retriever = StubRetriever(
        SemanticCandidateBundle(
            values=(
                ValueGroundingCandidate(
                    dimension=AnalysisDimension.CATEGORY,
                    canonical_value="livros_interesse_geral",
                ),
            )
        )
    )

    result = await SemanticGrounder(catalog, registry, retriever).bind(
        "为什么2018年5月图书品类GMV下降？",
        Intent.DIAGNOSIS,
    )

    assert result.status is SemanticBindingStatus.READY
    assert result.parsed_question is not None
    assert result.parsed_question.scope.category == "livros_interesse_geral"


@pytest.mark.asyncio
async def test_multiple_values_in_same_dimension_require_clarification(
    catalog,
    registry,
) -> None:
    retriever = StubRetriever(
        SemanticCandidateBundle(
            values=(
                ValueGroundingCandidate(
                    dimension=AnalysisDimension.REGION,
                    canonical_value="PR",
                ),
                ValueGroundingCandidate(
                    dimension=AnalysisDimension.REGION,
                    canonical_value="SP",
                ),
            )
        )
    )

    result = await SemanticGrounder(catalog, registry, retriever).bind(
        "为什么2018年5月南部州GMV下降？",
        Intent.DIAGNOSIS,
    )

    assert result.status is SemanticBindingStatus.CLARIFICATION_REQUIRED
    assert result.ambiguous_fields == (BindingField.SCOPE,)
    assert result.reason == "ambiguous_scope_value"


@pytest.mark.asyncio
async def test_qdrant_column_candidate_maps_to_logical_dimension(catalog, registry) -> None:
    retriever = StubRetriever(
        SemanticCandidateBundle(
            dimensions=(
                DimensionGroundingCandidate(
                    dimension=AnalysisDimension.REGION,
                    score=0.89,
                ),
            )
        )
    )

    result = await SemanticGrounder(catalog, registry, retriever).bind(
        "分析2018年5月GMV按客户所在地的贡献",
        Intent.DIAGNOSIS,
    )

    assert result.status is SemanticBindingStatus.READY
    assert result.parsed_question is not None
    assert result.parsed_question.requested_dimensions == (
        AnalysisDimension.REGION,
    )


@pytest.mark.asyncio
async def test_retrieval_failure_fails_closed(catalog, registry) -> None:
    result = await SemanticGrounder(
        catalog,
        registry,
        StubRetriever(error=RuntimeError("external detail must not escape")),
    ).bind("为什么2018年5月营业额下降？", Intent.DIAGNOSIS)

    assert result.status is SemanticBindingStatus.CLARIFICATION_REQUIRED
    assert result.reason == "semantic_retrieval_unavailable"
    assert result.limitations == ("retrieval_unavailable",)
    assert "external detail" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_non_diagnosis_intent_is_unsupported_without_retrieval(
    catalog,
    registry,
) -> None:
    retriever = StubRetriever()

    result = await SemanticGrounder(catalog, registry, retriever).bind(
        "2018年5月GMV是多少？",
        Intent.QUERY,
    )

    assert result.status is SemanticBindingStatus.UNSUPPORTED
    assert result.reason == "diagnosis_intent_required"
    assert retriever.calls == 0


@pytest.mark.asyncio
async def test_production_retriever_projects_only_registered_logical_candidates(
    monkeypatch: pytest.MonkeyPatch,
    catalog,
    registry,
) -> None:
    async def fake_query(
        client: Any,
        embedding: list[float],
        object_type: str,
        limit: int,
    ) -> list[RetrievedItem]:
        del client, embedding, limit
        if object_type == "metric":
            return [
                RetrievedItem("metric", "gmv", 0.91),
                RetrievedItem("metric", "not_registered", 0.99),
                RetrievedItem("metric", "order_count", 0.40),
            ]
        return [
            RetrievedItem("column", "dim_customer.state", 0.87),
            RetrievedItem("column", "fact_order.status", 0.96),
        ]

    async def fake_values(
        client: Any,
        question: str,
        limit: int,
    ) -> list[dict[str, str]]:
        del client, question, limit
        return [
            {"column_id": "dim_region.state_code", "canonical_value": "PR"},
            {"column_id": "fact_order.status", "canonical_value": "delivered"},
        ]

    class FakeEmbedding:
        async def aembed_query(self, text: str) -> list[float]:
            del text
            return [0.1, 0.2]

    monkeypatch.setattr(grounding_module, "query_metadata_by_vector", fake_query)
    monkeypatch.setattr(grounding_module, "retrieve_value", fake_values)
    retriever = QdrantElasticsearchCandidateRetriever(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        FakeEmbedding(),  # type: ignore[arg-type]
        catalog,
        registry,
    )

    result = await retriever.retrieve("营业额和巴拉那州")

    assert [item.metric_id for item in result.metrics] == ["gmv"]
    assert [item.dimension for item in result.dimensions] == [
        AnalysisDimension.REGION
    ]
    assert result.values == (
        ValueGroundingCandidate(
            dimension=AnalysisDimension.REGION,
            canonical_value="PR",
        ),
    )
    serialized = result.model_dump_json()
    assert "dim_customer.state" not in serialized
    assert "dim_region.state_code" not in serialized
    assert "fact_order.status" not in serialized


def test_binding_schema_rejects_mixed_and_extra_outcomes() -> None:
    with pytest.raises(ValidationError, match="READY requires"):
        SemanticBindingResult(status="READY")
    with pytest.raises(ValidationError, match="non-ready"):
        SemanticBindingResult(
            status="UNSUPPORTED",
            reason="unsupported",
            parsed_question={
                "target_metric": "gmv",
                "current_period": {"start": "2018-05-01", "end": "2018-05-31"},
                "baseline_period": {"start": "2018-04-01", "end": "2018-04-30"},
                "comparison_type": "previous_period",
                "scope": {},
            },
        )
    with pytest.raises(ValidationError):
        SemanticBindingResult(status="UNSUPPORTED", reason="unsupported", sql="SELECT 1")


def test_fixed_semantic_grounding_evaluation_passes() -> None:
    result = evaluate()

    assert result["case_count"] == 12
    assert result["metrics"]["exact_match_count"] == 12
    assert result["metrics"]["binding_status_accuracy_count"] == 12
    assert result["metrics"]["physical_schema_leakage_count"] == 0
    assert result["metrics"]["llm_call_count"] == 0
    assert result["failure_count"] == 0
    assert result["live_external_retrieval_evaluated"] is False
