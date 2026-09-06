from __future__ import annotations

from datetime import date

from app.diagnosis.capability import (
    AnalysisMethod,
    CapabilityAssessment,
    CapabilityLevel,
    DataQualityStatus,
)
from app.diagnosis.plan_validator import AnalysisPlanValidator
from app.diagnosis.planner import AnalysisPlan, AnalysisPlanner, PlanStopReason
from app.diagnosis.question import (
    AnalysisDimension,
    AnalysisScope,
    CandidateFactor,
    ComparisonType,
    DatePeriod,
    ParsedAnalysisQuestion,
)


def _question(
    *,
    dimensions: tuple[AnalysisDimension, ...] = (
        AnalysisDimension.REGION,
        AnalysisDimension.CATEGORY,
    ),
    factors: tuple[CandidateFactor, ...] = tuple(CandidateFactor),
) -> ParsedAnalysisQuestion:
    return ParsedAnalysisQuestion(
        target_metric="gmv",
        current_period=DatePeriod(start=date(2018, 5, 1), end=date(2018, 5, 31)),
        baseline_period=DatePeriod(start=date(2018, 4, 1), end=date(2018, 4, 30)),
        comparison_type=ComparisonType.PREVIOUS_PERIOD,
        scope=AnalysisScope(),
        requested_dimensions=dimensions,
        requested_factors=factors,
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
    available_dimensions: tuple[AnalysisDimension, ...] = tuple(AnalysisDimension),
    missing_evidence: tuple[str, ...] = (),
    quality: DataQualityStatus = DataQualityStatus.PASS,
) -> CapabilityAssessment:
    unsupported = tuple(
        method
        for method in AnalysisMethod
        if method not in supported and method is not AnalysisMethod.CAUSAL_INFERENCE
    ) + (AnalysisMethod.CAUSAL_INFERENCE,)
    level = (
        CapabilityLevel.UNSUPPORTED
        if not supported
        else CapabilityLevel.ASSOCIATION_DIAGNOSIS
    )
    return CapabilityAssessment(
        level=level,
        supported_methods=supported,
        unsupported_methods=unsupported,
        available_dimensions=available_dimensions,
        missing_evidence=missing_evidence,
        data_quality_status=quality,
    )


def _replaced_task(
    plan: AnalysisPlan,
    index: int,
    **updates: object,
) -> AnalysisPlan:
    current = plan.tasks[index]
    updated = current.model_copy(update=updates)
    return AnalysisPlan(
        tasks=(*plan.tasks[:index], updated, *plan.tasks[index + 1 :]),
        missing_evidence=plan.missing_evidence,
    )


def test_validator_accepts_full_deterministic_plan() -> None:
    question = _question()
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)

    result = AnalysisPlanValidator().validate(plan, question, capability)

    assert result.valid
    assert result.issues == ()


def test_validator_rejects_period_mutation() -> None:
    question = _question()
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)
    mutated = _replaced_task(
        plan,
        1,
        current_period=DatePeriod(start=date(2018, 6, 1), end=date(2018, 6, 30)),
    )

    result = AnalysisPlanValidator().validate(mutated, question, capability)

    assert not result.valid
    assert result.codes == ("current_period_mutation",)


def test_validator_rejects_scope_mutation() -> None:
    question = _question()
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)
    mutated = _replaced_task(
        plan,
        1,
        scope=AnalysisScope(region="SP"),
    )

    result = AnalysisPlanValidator().validate(mutated, question, capability)

    assert not result.valid
    assert result.codes == ("scope_mutation",)


def test_validator_rejects_unsupported_method_for_reduced_capability() -> None:
    question = _question()
    full = AnalysisPlanner().plan(question, _capability())
    reduced = _capability(
        supported=(
            AnalysisMethod.PERIOD_COMPARISON,
            AnalysisMethod.METRIC_DECOMPOSITION,
        )
    )

    result = AnalysisPlanValidator().validate(full, question, reduced)

    assert not result.valid
    assert "unsupported_method" in result.codes


def test_validator_rejects_unrequested_dimension() -> None:
    question = _question(dimensions=(AnalysisDimension.REGION,))
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)
    mutated = _replaced_task(
        plan,
        2,
        dimensions=tuple(AnalysisDimension),
    )

    result = AnalysisPlanValidator().validate(mutated, question, capability)

    assert not result.valid
    assert result.codes == ("unrequested_dimension",)


def test_validator_rejects_unavailable_dimension() -> None:
    question = _question(dimensions=tuple(AnalysisDimension))
    capability = _capability(available_dimensions=(AnalysisDimension.REGION,))
    plan = AnalysisPlanner().plan(question, capability)
    mutated = _replaced_task(
        plan,
        2,
        dimensions=tuple(AnalysisDimension),
    )

    result = AnalysisPlanValidator().validate(mutated, question, capability)

    assert not result.valid
    assert result.codes == ("dimension_not_available",)


def test_validator_rejects_unrequested_factor() -> None:
    question = _question(factors=(CandidateFactor.TRAFFIC,))
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)
    mutated = _replaced_task(
        plan,
        3,
        factors=(CandidateFactor.TRAFFIC, CandidateFactor.PROMOTION),
    )

    result = AnalysisPlanValidator().validate(mutated, question, capability)

    assert not result.valid
    assert result.codes == ("unrequested_factor",)


def test_validator_rejects_unsupported_factor_validation() -> None:
    question = _question(factors=tuple(CandidateFactor))
    capability = _capability(
        supported=(
            AnalysisMethod.PERIOD_COMPARISON,
            AnalysisMethod.METRIC_DECOMPOSITION,
            AnalysisMethod.TRAFFIC_VALIDATION,
        )
    )
    plan = AnalysisPlanner().plan(question, capability)
    mutated = _replaced_task(
        plan,
        2,
        factors=(CandidateFactor.TRAFFIC, CandidateFactor.INVENTORY),
    )

    result = AnalysisPlanValidator().validate(mutated, question, capability)

    assert not result.valid
    assert result.codes == ("factor_validation_unavailable",)


def test_validator_accepts_matching_empty_plan() -> None:
    capability = _capability(
        supported=(),
        missing_evidence=("baseline_period",),
    )
    plan = AnalysisPlanner().plan(_question(), capability)

    result = AnalysisPlanValidator().validate(plan, _question(), capability)

    assert result.valid
    assert plan.stop_reason is PlanStopReason.INSUFFICIENT_DATA


def test_validator_accepts_data_quality_stop_plan() -> None:
    capability = _capability(
        supported=(),
        missing_evidence=("data_quality_failed",),
        quality=DataQualityStatus.FAIL,
    )
    plan = AnalysisPlanner().plan(_question(), capability)

    result = AnalysisPlanValidator().validate(plan, _question(), capability)

    assert result.valid
    assert plan.stop_reason is PlanStopReason.DATA_QUALITY_FAILED


def test_validator_rejects_inconsistent_stop_reasons() -> None:
    capability = _capability(
        supported=(),
        missing_evidence=("baseline_period",),
    )
    pass_plan = AnalysisPlanner().plan(_question(), capability)
    mismatched = pass_plan.model_copy(
        update={"stop_reason": PlanStopReason.DATA_QUALITY_FAILED}
    )

    result = AnalysisPlanValidator().validate(
        mismatched, _question(), capability
    )

    assert not result.valid
    assert result.codes == ("inconsistent_stop_reason",)
