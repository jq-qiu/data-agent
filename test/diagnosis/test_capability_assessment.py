import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.diagnosis.capability import (
    AnalysisMethod,
    CapabilityAssessment,
    CapabilityAssessmentNode,
    CapabilityAssessor,
    CapabilityDataSource,
    CapabilityLevel,
    DataCapabilityProfile,
    DataQualityStatus,
)
from app.diagnosis.question import ParsedAnalysisQuestion
from app.metadata.catalog import MetadataCatalog, load_catalog
from app.scripts.evaluate_capability_assessment_v1 import evaluate

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def catalog() -> MetadataCatalog:
    return load_catalog(ROOT / "conf/meta_config.yaml")


@pytest.fixture(scope="module")
def assessor(catalog: MetadataCatalog) -> CapabilityAssessor:
    return CapabilityAssessor(catalog)


def _question(
    *,
    region: str | None = None,
    category: str | None = None,
    dimensions: tuple[str, ...] = ("region", "category"),
    factors: tuple[str, ...] = ("traffic", "promotion", "inventory"),
) -> ParsedAnalysisQuestion:
    return ParsedAnalysisQuestion(
        target_metric="gmv",
        current_period={"start": "2018-05-01", "end": "2018-05-31"},
        baseline_period={"start": "2018-04-01", "end": "2018-04-30"},
        comparison_type="previous_period",
        scope={"region": region, "category": category},
        requested_dimensions=dimensions,
        requested_factors=factors,
    )


def _profile(
    catalog: MetadataCatalog,
    *,
    source: CapabilityDataSource = CapabilityDataSource.WAREHOUSE,
    remove: tuple[str, ...] = (),
    empty: tuple[str, ...] = (),
    period: tuple[str, str] = ("2018-04-01", "2018-05-31"),
    quality: DataQualityStatus = DataQualityStatus.PASS,
    quality_issues: tuple[str, ...] = (),
    experimental_design_present: bool = False,
) -> DataCapabilityProfile:
    available = tuple(sorted(catalog.column_ids - set(remove)))
    non_empty = tuple(item for item in available if item not in empty)
    return DataCapabilityProfile(
        source=source,
        available_period={"start": period[0], "end": period[1]},
        available_columns=available,
        non_empty_columns=non_empty,
        data_quality_status=quality,
        data_quality_issues=quality_issues,
        experimental_design_present=experimental_design_present,
    )


def test_profile_and_assessment_schemas_reject_invalid_contracts() -> None:
    with pytest.raises(ValidationError, match="unique"):
        DataCapabilityProfile(
            source="warehouse",
            available_period={"start": "2018-04-01", "end": "2018-05-31"},
            available_columns=["table.column", "table.column"],
            non_empty_columns=["table.column"],
            data_quality_status="pass",
        )
    with pytest.raises(ValidationError, match="table.column"):
        DataCapabilityProfile(
            source="warehouse",
            available_period={"start": "2018-04-01", "end": "2018-05-31"},
            available_columns=["unqualified"],
            non_empty_columns=[],
            data_quality_status="pass",
        )
    with pytest.raises(ValidationError, match="must be available"):
        DataCapabilityProfile(
            source="warehouse",
            available_period={"start": "2018-04-01", "end": "2018-05-31"},
            available_columns=["table.column"],
            non_empty_columns=["table.other"],
            data_quality_status="pass",
        )
    with pytest.raises(ValidationError, match="stable codes"):
        DataCapabilityProfile(
            source="warehouse",
            available_period={"start": "2018-04-01", "end": "2018-05-31"},
            available_columns=["table.column"],
            non_empty_columns=["table.column"],
            data_quality_status="fail",
            data_quality_issues=["free text is not allowed"],
        )
    with pytest.raises(ValidationError, match="causal inference"):
        CapabilityAssessment(
            level="association_diagnosis",
            supported_methods=["period_comparison", "causal_inference"],
            unsupported_methods=[],
            available_dimensions=[],
            missing_evidence=[],
            data_quality_status="pass",
        )


def test_profile_columns_must_exist_in_catalog(
    assessor: CapabilityAssessor,
) -> None:
    profile = DataCapabilityProfile(
        source="warehouse",
        available_period={"start": "2018-04-01", "end": "2018-05-31"},
        available_columns=["unknown_table.unknown_column"],
        non_empty_columns=["unknown_table.unknown_column"],
        data_quality_status="pass",
    )

    with pytest.raises(ValueError, match="unknown Catalog columns"):
        assessor.assess(_question(), profile)


def test_full_profile_opens_six_v1_methods_and_never_causal(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
) -> None:
    assessment = assessor.assess(_question(), _profile(catalog))

    assert assessment == CapabilityAssessment(
        level=CapabilityLevel.ASSOCIATION_DIAGNOSIS,
        supported_methods=(
            AnalysisMethod.PERIOD_COMPARISON,
            AnalysisMethod.METRIC_DECOMPOSITION,
            AnalysisMethod.DIMENSION_CONTRIBUTION,
            AnalysisMethod.TRAFFIC_VALIDATION,
            AnalysisMethod.PROMOTION_VALIDATION,
            AnalysisMethod.INVENTORY_VALIDATION,
        ),
        unsupported_methods=(AnalysisMethod.CAUSAL_INFERENCE,),
        available_dimensions=("region", "category"),
        missing_evidence=(),
        data_quality_status=DataQualityStatus.PASS,
    )


@pytest.mark.parametrize(
    "period,missing",
    (
        (("2018-05-01", "2018-05-31"), ("baseline_period",)),
        (("2018-04-01", "2018-04-30"), ("current_period",)),
    ),
)
def test_missing_period_closes_every_requested_method(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
    period: tuple[str, str],
    missing: tuple[str, ...],
) -> None:
    assessment = assessor.assess(_question(), _profile(catalog, period=period))

    assert assessment.level is CapabilityLevel.UNSUPPORTED
    assert assessment.supported_methods == ()
    assert assessment.missing_evidence == missing
    assert assessment.unsupported_methods == tuple(AnalysisMethod)


def test_missing_gmv_closes_every_downstream_method(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
) -> None:
    column = "dws_sales_region_daily.gmv"
    assessment = assessor.assess(_question(), _profile(catalog, empty=(column,)))

    assert assessment.supported_methods == ()
    assert assessment.unsupported_methods == tuple(AnalysisMethod)
    assert assessment.missing_evidence == (column,)


def test_missing_overall_order_count_preserves_period_and_dimensions_only(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
) -> None:
    column = "dws_sales_region_daily.order_count"
    assessment = assessor.assess(_question(), _profile(catalog, empty=(column,)))

    assert assessment.supported_methods == (
        AnalysisMethod.PERIOD_COMPARISON,
        AnalysisMethod.DIMENSION_CONTRIBUTION,
    )
    assert assessment.unsupported_methods == (
        AnalysisMethod.METRIC_DECOMPOSITION,
        AnalysisMethod.TRAFFIC_VALIDATION,
        AnalysisMethod.PROMOTION_VALIDATION,
        AnalysisMethod.INVENTORY_VALIDATION,
        AnalysisMethod.CAUSAL_INFERENCE,
    )
    assert assessment.missing_evidence == (column,)


def test_one_factor_field_only_closes_its_method(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
) -> None:
    column = "dws_sales_region_daily.promoted_sku_count"
    assessment = assessor.assess(_question(), _profile(catalog, empty=(column,)))

    assert AnalysisMethod.TRAFFIC_VALIDATION in assessment.supported_methods
    assert AnalysisMethod.PROMOTION_VALIDATION in assessment.unsupported_methods
    assert AnalysisMethod.INVENTORY_VALIDATION in assessment.supported_methods
    assert assessment.missing_evidence == (column,)


def test_missing_category_grain_keeps_region_dimension_available(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
) -> None:
    column = "dws_sales_category_daily.gmv"
    assessment = assessor.assess(
        _question(dimensions=("region", "category"), factors=()),
        _profile(catalog, empty=(column,)),
    )

    assert assessment.available_dimensions == ("region",)
    assert AnalysisMethod.DIMENSION_CONTRIBUTION in assessment.supported_methods
    assert assessment.missing_evidence == (column,)


def test_category_scope_uses_category_order_count_not_overall_order_count(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
) -> None:
    assessment = assessor.assess(
        _question(
            category="informatica_acessorios",
            dimensions=("region",),
        ),
        _profile(catalog, empty=("dws_sales_region_daily.order_count",)),
    )

    assert AnalysisMethod.METRIC_DECOMPOSITION in assessment.supported_methods
    assert AnalysisMethod.TRAFFIC_VALIDATION in assessment.supported_methods
    assert assessment.missing_evidence == ()


def test_synthetic_missing_visitors_degrades_all_candidate_validations(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
) -> None:
    column = "analysis_sales_region_daily.visitors"
    assessment = assessor.assess(
        _question(),
        _profile(
            catalog,
            source=CapabilityDataSource.SYNTHETIC_CASE,
            empty=(column,),
        ),
    )

    assert assessment.supported_methods == (
        AnalysisMethod.PERIOD_COMPARISON,
        AnalysisMethod.METRIC_DECOMPOSITION,
        AnalysisMethod.DIMENSION_CONTRIBUTION,
    )
    assert assessment.unsupported_methods == (
        AnalysisMethod.TRAFFIC_VALIDATION,
        AnalysisMethod.PROMOTION_VALIDATION,
        AnalysisMethod.INVENTORY_VALIDATION,
        AnalysisMethod.CAUSAL_INFERENCE,
    )
    assert assessment.missing_evidence == (column,)


def test_failed_data_quality_closes_all_requested_methods(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
) -> None:
    assessment = assessor.assess(
        _question(),
        _profile(
            catalog,
            quality=DataQualityStatus.FAIL,
            quality_issues=("gmv_reconciliation_failed",),
        ),
    )

    assert assessment.level is CapabilityLevel.UNSUPPORTED
    assert assessment.supported_methods == ()
    assert assessment.unsupported_methods == tuple(AnalysisMethod)
    assert assessment.missing_evidence == (
        "data_quality_failed",
        "gmv_reconciliation_failed",
    )


def test_experimental_flag_cannot_open_causal_inference(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
) -> None:
    assessment = assessor.assess(
        _question(),
        _profile(catalog, experimental_design_present=True),
    )

    assert AnalysisMethod.CAUSAL_INFERENCE not in assessment.supported_methods
    assert assessment.unsupported_methods == (AnalysisMethod.CAUSAL_INFERENCE,)


@pytest.mark.asyncio
async def test_injected_node_emits_only_json_capability_state(
    assessor: CapabilityAssessor,
    catalog: MetadataCatalog,
) -> None:
    question = _question().model_dump(mode="json")
    update = await CapabilityAssessmentNode(assessor, _profile(catalog))(
        {"parsed_question": question}
    )

    assert json.loads(json.dumps(update)) == update
    assert update["capability"]["level"] == "association_diagnosis"
    assert "available_columns" not in update
    assert "catalog" not in update


def test_fixed_evaluation_matches_every_capability_and_degradation_case() -> None:
    result = evaluate()

    assert result["case_count"] == 13
    assert result["metrics"]["exact_match_count"] == 13
    assert result["metrics"]["correct_degradation_count"] == 8
    assert result["metrics"]["causal_method_allowed_count"] == 0
    assert result["metrics"]["failed_quality_method_allowed_count"] == 0
    assert result["failure_count"] == 0
