from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.diagnosis.capability import (
    AnalysisMethod,
    CapabilityAssessment,
    CapabilityLevel,
    DataQualityStatus,
)
from app.diagnosis.planner import (
    AnalysisPlan,
    AnalysisPlanner,
    AnalysisPlannerNode,
    AnalysisTask,
    PlanStopReason,
    TaskMethod,
)
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


def test_full_capability_creates_four_bounded_tasks() -> None:
    plan = AnalysisPlanner().plan(_question(), _capability())

    assert [task.task_id for task in plan.tasks] == ["T1", "T2", "T3", "T4"]
    assert [task.method for task in plan.tasks] == list(TaskMethod)
    assert plan.tasks[2].dimensions == tuple(AnalysisDimension)
    assert plan.tasks[3].factors == tuple(CandidateFactor)
    assert plan.tasks[0].depends_on == ()
    assert all(task.depends_on == ("T1",) for task in plan.tasks[1:])
    assert plan.stop_reason is None


def test_plan_reuses_question_parameters_without_rewriting() -> None:
    question = _question()
    plan = AnalysisPlanner().plan(question, _capability())

    for task in plan.tasks:
        assert task.metric == question.target_metric
        assert task.current_period == question.current_period
        assert task.baseline_period == question.baseline_period
        assert task.scope == question.scope


def test_partial_factor_capability_selects_only_supported_factors() -> None:
    capability = _capability(
        supported=(
            AnalysisMethod.PERIOD_COMPARISON,
            AnalysisMethod.METRIC_DECOMPOSITION,
            AnalysisMethod.TRAFFIC_VALIDATION,
            AnalysisMethod.INVENTORY_VALIDATION,
        ),
        missing_evidence=("dws_sales_region_daily.promoted_sku_count",),
    )

    plan = AnalysisPlanner().plan(_question(), capability)

    assert plan.tasks[-1].method is TaskMethod.CANDIDATE_VALIDATION
    assert plan.tasks[-1].factors == (
        CandidateFactor.TRAFFIC,
        CandidateFactor.INVENTORY,
    )
    assert plan.missing_evidence == capability.missing_evidence


def test_partial_dimension_capability_intersects_requested_dimensions() -> None:
    capability = _capability(
        available_dimensions=(AnalysisDimension.REGION,),
        missing_evidence=("dws_sales_category_daily.gmv",),
    )

    plan = AnalysisPlanner().plan(_question(), capability)

    assert plan.tasks[2].dimensions == (AnalysisDimension.REGION,)


def test_unrequested_optional_methods_are_not_planned() -> None:
    question = _question(dimensions=(), factors=())

    plan = AnalysisPlanner().plan(question, _capability())

    assert [task.method for task in plan.tasks] == [
        TaskMethod.PERIOD_COMPARISON,
        TaskMethod.METRIC_DECOMPOSITION,
    ]


def test_unsupported_decomposition_does_not_block_other_supported_tasks() -> None:
    capability = _capability(
        supported=(
            AnalysisMethod.PERIOD_COMPARISON,
            AnalysisMethod.DIMENSION_CONTRIBUTION,
        ),
        missing_evidence=("dws_sales_region_daily.order_count",),
    )

    plan = AnalysisPlanner().plan(_question(factors=()), capability)

    assert [task.method for task in plan.tasks] == [
        TaskMethod.PERIOD_COMPARISON,
        TaskMethod.DIMENSION_CONTRIBUTION,
    ]
    assert plan.tasks[1].task_id == "T2"
    assert plan.tasks[1].depends_on == ("T1",)


def test_no_supported_factors_means_no_candidate_task() -> None:
    capability = _capability(
        supported=(
            AnalysisMethod.PERIOD_COMPARISON,
            AnalysisMethod.METRIC_DECOMPOSITION,
        )
    )

    plan = AnalysisPlanner().plan(_question(), capability)

    assert all(task.method is not TaskMethod.CANDIDATE_VALIDATION for task in plan.tasks)


def test_missing_period_capability_returns_insufficient_data_stop() -> None:
    capability = _capability(
        supported=(),
        missing_evidence=("baseline_period",),
    )

    plan = AnalysisPlanner().plan(_question(), capability)

    assert plan.tasks == ()
    assert plan.stop_reason is PlanStopReason.INSUFFICIENT_DATA
    assert plan.missing_evidence == ("baseline_period",)


def test_failed_quality_returns_data_quality_stop() -> None:
    capability = _capability(
        supported=(),
        missing_evidence=("data_quality_failed", "gmv_reconciliation_failed"),
        quality=DataQualityStatus.FAIL,
    )

    plan = AnalysisPlanner().plan(_question(), capability)

    assert plan.tasks == ()
    assert plan.stop_reason is PlanStopReason.DATA_QUALITY_FAILED


def test_serialized_plan_has_no_sql_or_causal_method() -> None:
    payload = AnalysisPlanner().plan(_question(), _capability()).model_dump_json()

    assert "sql" not in payload.casefold()
    assert "causal" not in payload.casefold()


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"sql": "SELECT 1"}, "Extra inputs"),
        ({"dimensions": ["region"]}, "only dimension contribution"),
        ({"factors": ["traffic"]}, "only candidate validation"),
        ({"depends_on": ["T2"]}, "cannot have dependencies"),
    ],
)
def test_task_schema_rejects_out_of_contract_fields(
    updates: dict[str, object], message: str
) -> None:
    payload: dict[str, object] = {
        "task_id": "T1",
        "method": "period_comparison",
        "metric": "gmv",
        "current_period": {"start": "2018-05-01", "end": "2018-05-31"},
        "baseline_period": {"start": "2018-04-01", "end": "2018-04-30"},
        "scope": {},
        "dimensions": [],
        "factors": [],
        "depends_on": [],
    }
    payload.update(updates)

    with pytest.raises(ValidationError, match=message):
        AnalysisTask.model_validate(payload)


def test_plan_schema_rejects_more_than_four_tasks() -> None:
    task = AnalysisPlanner().plan(
        _question(dimensions=(), factors=()), _capability()
    ).tasks[0]

    with pytest.raises(ValidationError, match="at most 4"):
        AnalysisPlan(tasks=(task, task, task, task, task))


def test_plan_schema_rejects_nonconsecutive_identifiers() -> None:
    task = AnalysisPlanner().plan(
        _question(dimensions=(), factors=()), _capability()
    ).tasks[0]
    invalid = task.model_copy(update={"task_id": "T2"})

    with pytest.raises(ValidationError, match="consecutive"):
        AnalysisPlan(tasks=(invalid,))


def test_plan_schema_rejects_duplicate_methods() -> None:
    plan = AnalysisPlanner().plan(_question(dimensions=(), factors=()), _capability())
    duplicate = plan.tasks[1].model_copy(
        update={"task_id": "T3", "method": TaskMethod.METRIC_DECOMPOSITION}
    )

    with pytest.raises(ValidationError, match="methods must be unique"):
        AnalysisPlan(tasks=(*plan.tasks, duplicate))


def test_plan_schema_rejects_forward_dependency_even_for_existing_task() -> None:
    plan = AnalysisPlanner().plan(_question(dimensions=(), factors=()), _capability())
    invalid = plan.tasks[1].model_copy(update={"depends_on": ("T2",)})

    with pytest.raises(ValidationError, match="depend only on T1"):
        AnalysisPlan(tasks=(plan.tasks[0], invalid))


def test_planner_canonicalizes_dimension_and_factor_order() -> None:
    question = _question(
        dimensions=(AnalysisDimension.CATEGORY, AnalysisDimension.REGION),
        factors=(
            CandidateFactor.INVENTORY,
            CandidateFactor.TRAFFIC,
            CandidateFactor.PROMOTION,
        ),
    )

    plan = AnalysisPlanner().plan(question, _capability())

    assert plan.tasks[2].dimensions == tuple(AnalysisDimension)
    assert plan.tasks[3].factors == tuple(CandidateFactor)


@pytest.mark.asyncio
async def test_node_emits_serializable_plan_only() -> None:
    question = _question()
    capability = _capability()

    output = await AnalysisPlannerNode()(
        {
            "parsed_question": question.model_dump(mode="json"),
            "capability": capability.model_dump(mode="json"),
            "runtime_client": object(),
        }
    )

    assert set(output) == {"analysis_plan"}
    assert len(output["analysis_plan"]["tasks"]) == 4
    assert "runtime_client" not in output["analysis_plan"]
