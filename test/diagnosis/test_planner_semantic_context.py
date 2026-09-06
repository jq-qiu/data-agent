from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.diagnosis.capability import (
    AnalysisMethod,
    CapabilityAssessment,
    CapabilityLevel,
    DataQualityStatus,
)
from app.diagnosis.planner import TaskMethod
from app.diagnosis.question import (
    AnalysisDimension,
    AnalysisScope,
    CandidateFactor,
    ComparisonType,
    DatePeriod,
    ParsedAnalysisQuestion,
)
from app.diagnosis.semantics import (
    AnalysisSemanticRegistry,
    PlannerSemanticContext,
    PlannerSemanticContextBuilder,
)
from app.metadata.catalog import MetadataCatalog, load_catalog

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def catalog() -> MetadataCatalog:
    return load_catalog(ROOT / "conf/meta_config.yaml")


@pytest.fixture(scope="module")
def registry(catalog: MetadataCatalog) -> AnalysisSemanticRegistry:
    return AnalysisSemanticRegistry.from_catalog(catalog)


def _question() -> ParsedAnalysisQuestion:
    return ParsedAnalysisQuestion(
        target_metric="gmv",
        current_period=DatePeriod(start=date(2018, 5, 1), end=date(2018, 5, 31)),
        baseline_period=DatePeriod(start=date(2018, 4, 1), end=date(2018, 4, 30)),
        comparison_type=ComparisonType.PREVIOUS_PERIOD,
        scope=AnalysisScope(),
        requested_dimensions=tuple(AnalysisDimension),
        requested_factors=tuple(CandidateFactor),
    )


def _capability(
    *,
    supported: tuple[AnalysisMethod, ...] = (
        AnalysisMethod.PERIOD_COMPARISON,
        AnalysisMethod.METRIC_DECOMPOSITION,
        AnalysisMethod.DIMENSION_CONTRIBUTION,
        AnalysisMethod.TRAFFIC_VALIDATION,
        AnalysisMethod.PROMOTION_VALIDATION,
        AnalysisMethod.INVENTORY_VALIDATION,
    ),
    dimensions: tuple[AnalysisDimension, ...] = tuple(AnalysisDimension),
    missing_evidence: tuple[str, ...] = (),
    quality: DataQualityStatus = DataQualityStatus.PASS,
) -> CapabilityAssessment:
    unsupported = tuple(
        method
        for method in AnalysisMethod
        if method not in supported and method is not AnalysisMethod.CAUSAL_INFERENCE
    ) + (AnalysisMethod.CAUSAL_INFERENCE,)
    return CapabilityAssessment(
        level=(
            CapabilityLevel.ASSOCIATION_DIAGNOSIS
            if supported
            else CapabilityLevel.UNSUPPORTED
        ),
        supported_methods=supported,
        unsupported_methods=unsupported,
        available_dimensions=dimensions,
        missing_evidence=missing_evidence,
        data_quality_status=quality,
    )


def test_registry_is_validated_against_physical_metadata(
    catalog: MetadataCatalog,
    registry: AnalysisSemanticRegistry,
) -> None:
    assert registry.metric_map["gmv"].analysis_identity == "GMV = Order Count × AOV"
    assert tuple(registry.dimension_map) == tuple(AnalysisDimension)
    assert tuple(registry.factor_map) == tuple(CandidateFactor)
    assert tuple(registry.tool_map) == tuple(TaskMethod)

    catalog_without_gmv = MetadataCatalog(
        version=catalog.version,
        tables=catalog.tables,
        metrics=tuple(item for item in catalog.metrics if item.metric_id != "gmv"),
        relationships=catalog.relationships,
    )
    with pytest.raises(ValueError, match="registered gmv"):
        AnalysisSemanticRegistry.from_catalog(catalog_without_gmv)


def test_full_context_contains_only_logical_planning_projection(
    registry: AnalysisSemanticRegistry,
) -> None:
    context = PlannerSemanticContextBuilder(registry).build(
        _question(),
        _capability(),
    )

    assert [item.dimension for item in context.available_dimensions] == list(
        AnalysisDimension
    )
    assert [item.factor for item in context.available_factors] == list(CandidateFactor)
    assert [item.method for item in context.available_tools] == list(TaskMethod)
    assert context.constraints.max_tasks == 4
    assert context.constraints.sql_allowed is False
    assert context.constraints.physical_schema_allowed is False
    assert context.constraints.deterministic_math_required is True
    assert context.constraints.causal_claims_allowed is False
    assert context.limitations == ("association_not_causation",)

    serialized = context.model_dump_json()
    for forbidden in (
        "dws_",
        "fact_",
        "dim_",
        "analysis_sales_",
        "select ",
        " join ",
        "ground_truth",
    ):
        assert forbidden not in serialized.casefold()


def test_context_intersects_requested_semantics_with_runtime_capability(
    registry: AnalysisSemanticRegistry,
) -> None:
    context = PlannerSemanticContextBuilder(registry).build(
        _question(),
        _capability(
            supported=(
                AnalysisMethod.PERIOD_COMPARISON,
                AnalysisMethod.METRIC_DECOMPOSITION,
                AnalysisMethod.TRAFFIC_VALIDATION,
            ),
            dimensions=(AnalysisDimension.REGION,),
            missing_evidence=(
                "dws_sales_region_daily.promoted_sku_count",
                "dws_sales_region_daily.available_sku_count",
            ),
        ),
    )

    assert context.available_dimensions == ()
    assert [item.factor for item in context.available_factors] == [
        CandidateFactor.TRAFFIC
    ]
    assert [item.method for item in context.available_tools] == [
        TaskMethod.PERIOD_COMPARISON,
        TaskMethod.METRIC_DECOMPOSITION,
        TaskMethod.CANDIDATE_VALIDATION,
    ]
    assert context.limitations == (
        "region_dimension_unavailable",
        "category_dimension_unavailable",
        "promotion_evidence_unavailable",
        "inventory_evidence_unavailable",
        "association_not_causation",
    )
    serialized = context.model_dump_json()
    assert "promoted_sku_count" not in serialized
    assert "available_sku_count" not in serialized
    assert "dws_sales_region_daily" not in serialized


def test_failed_data_quality_exposes_no_tools_or_factors(
    registry: AnalysisSemanticRegistry,
) -> None:
    context = PlannerSemanticContextBuilder(registry).build(
        _question(),
        _capability(
            supported=(),
            dimensions=(),
            missing_evidence=("data_quality_failed",),
            quality=DataQualityStatus.FAIL,
        ),
    )

    assert context.available_tools == ()
    assert context.available_dimensions == ()
    assert context.available_factors == ()
    assert context.limitations[0] == "data_quality_failed"
    assert "association_not_causation" in context.limitations


def test_context_schema_is_frozen_and_rejects_physical_extras(
    registry: AnalysisSemanticRegistry,
) -> None:
    payload = PlannerSemanticContextBuilder(registry).build(
        _question(),
        _capability(),
    ).model_dump(mode="json")
    payload["tables"] = ["dws_sales_region_daily"]

    with pytest.raises(ValidationError, match="Extra inputs"):
        PlannerSemanticContext.model_validate(payload)
