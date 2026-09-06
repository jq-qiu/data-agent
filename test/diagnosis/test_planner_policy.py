from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.diagnosis.capability import (
    AnalysisMethod,
    CapabilityAssessment,
    CapabilityLevel,
    DataQualityStatus,
)
from app.diagnosis.planner import AnalysisPlan, AnalysisPlanner
from app.diagnosis.planner_policy import (
    BoundedPlannerPolicy,
    BoundedPlanResult,
    LegalPlanOption,
    PlanningSource,
    PlanValidationFailure,
    SelectorOption,
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
    dimensions: tuple[AnalysisDimension, ...] = (),
    factors: tuple[CandidateFactor, ...] = (),
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


def _capability() -> CapabilityAssessment:
    supported = (
        AnalysisMethod.PERIOD_COMPARISON,
        AnalysisMethod.METRIC_DECOMPOSITION,
        AnalysisMethod.DIMENSION_CONTRIBUTION,
        AnalysisMethod.TRAFFIC_VALIDATION,
        AnalysisMethod.PROMOTION_VALIDATION,
        AnalysisMethod.INVENTORY_VALIDATION,
    )
    unsupported = tuple(
        method
        for method in AnalysisMethod
        if method not in supported and method is not AnalysisMethod.CAUSAL_INFERENCE
    ) + (AnalysisMethod.CAUSAL_INFERENCE,)
    return CapabilityAssessment(
        level=CapabilityLevel.ASSOCIATION_DIAGNOSIS,
        supported_methods=supported,
        unsupported_methods=unsupported,
        available_dimensions=tuple(AnalysisDimension),
        missing_evidence=(),
        data_quality_status=DataQualityStatus.PASS,
    )


class MultipleOptionProvider:
    """Architecture-only fixture proving the generic bounded LLM branch."""

    def __init__(self, plan: AnalysisPlan) -> None:
        self.plan = plan

    def options(
        self,
        question: ParsedAnalysisQuestion,
        capability: CapabilityAssessment,
    ) -> tuple[LegalPlanOption, ...]:
        return (
            LegalPlanOption(
                variant_id="v1",
                description="默认确定性计划",
                plan=self.plan,
            ),
            LegalPlanOption(
                variant_id="v2",
                description="精简计划（仅期间对比）",
                plan=AnalysisPlan(tasks=(self.plan.tasks[0],)),
            ),
        )


class RecordingSelector:
    def __init__(
        self,
        result: str | None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls = 0
        self.seen_options: tuple[SelectorOption, ...] = ()

    async def choose(
        self,
        question: ParsedAnalysisQuestion,
        context: Any,
        options: tuple[SelectorOption, ...],
    ) -> str | None:
        self.calls += 1
        self.seen_options = options
        if self.error is not None:
            raise self.error
        return self.result


def test_unique_legal_plan_is_deterministic_with_zero_model_calls() -> None:
    question = _question()
    capability = _capability()
    policy = BoundedPlannerPolicy()

    result = policy.plan(question, capability)

    assert result.source is PlanningSource.DETERMINISTIC
    assert result.model_calls == 0
    assert result.decision_reason == "unique_legal_plan"
    assert result.plan == AnalysisPlanner().plan(question, capability)
    assert result.validator_issues == ()


@pytest.mark.asyncio
async def test_unique_legal_plan_async_never_calls_selector() -> None:
    selector = RecordingSelector(result="v2")
    policy = BoundedPlannerPolicy(selector=selector)  # type: ignore[arg-type]

    result = await policy.aplan(_question(), _capability())

    assert result.source is PlanningSource.DETERMINISTIC
    assert result.model_calls == 0
    assert selector.calls == 0


@pytest.mark.asyncio
async def test_multiple_legal_plans_accept_valid_llm_choice() -> None:
    question = _question()
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)
    selector = RecordingSelector(result="v2")
    policy = BoundedPlannerPolicy(
        provider=MultipleOptionProvider(plan),
        selector=selector,  # type: ignore[arg-type]
    )

    result = await policy.aplan(question, capability)

    assert result.source is PlanningSource.LLM
    assert result.model_calls == 1
    assert result.decision_reason == "llm_choice_accepted"
    assert result.plan.tasks == (plan.tasks[0],)
    assert selector.calls == 1
    assert [option.variant_id for option in selector.seen_options] == ["v1", "v2"]


@pytest.mark.asyncio
async def test_unknown_llm_choice_falls_back_to_deterministic() -> None:
    question = _question()
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)
    policy = BoundedPlannerPolicy(
        provider=MultipleOptionProvider(plan),
        selector=RecordingSelector(result="v9"),  # type: ignore[arg-type]
    )

    result = await policy.aplan(question, capability)

    assert result.source is PlanningSource.FALLBACK
    assert result.model_calls == 1
    assert result.decision_reason == "llm_choice_invalid_fallback"
    assert result.validator_issues == ("unknown_variant",)
    assert result.plan == plan


@pytest.mark.asyncio
async def test_empty_llm_choice_falls_back_without_retry() -> None:
    question = _question()
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)
    policy = BoundedPlannerPolicy(
        provider=MultipleOptionProvider(plan),
        selector=RecordingSelector(result=None),  # type: ignore[arg-type]
    )

    result = await policy.aplan(question, capability)

    assert result.source is PlanningSource.FALLBACK
    assert result.model_calls == 1
    assert result.decision_reason == "llm_choice_empty_fallback"
    assert result.plan == plan


@pytest.mark.asyncio
async def test_selector_failure_falls_back_without_retry() -> None:
    question = _question()
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)
    selector = RecordingSelector(
        result=None,
        error=TimeoutError("model timeout"),
    )
    policy = BoundedPlannerPolicy(
        provider=MultipleOptionProvider(plan),
        selector=selector,  # type: ignore[arg-type]
    )

    result = await policy.aplan(question, capability)

    assert result.source is PlanningSource.FALLBACK
    assert result.model_calls == 1
    assert result.decision_reason == "llm_failure_fallback"
    assert result.plan == plan
    assert selector.calls == 1


@pytest.mark.asyncio
async def test_missing_selector_uses_zero_call_deterministic_fallback() -> None:
    question = _question()
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)
    policy = BoundedPlannerPolicy(provider=MultipleOptionProvider(plan))

    result = await policy.aplan(question, capability)

    assert result.source is PlanningSource.FALLBACK
    assert result.model_calls == 0
    assert result.decision_reason == "selector_unavailable_fallback"
    assert result.plan == plan


@pytest.mark.asyncio
async def test_sync_plan_rejects_multiple_options_without_async_selector() -> None:
    question = _question()
    capability = _capability()
    plan = AnalysisPlanner().plan(question, capability)
    policy = BoundedPlannerPolicy(provider=MultipleOptionProvider(plan))

    with pytest.raises(PlanValidationFailure, match="require the async"):
        policy.plan(question, capability)


def test_result_serialization_contains_no_physical_schema() -> None:
    question = _question()
    capability = _capability()
    result = BoundedPlannerPolicy().plan(question, capability)
    payload = BoundedPlanResult.model_validate(
        result.model_dump(mode="json")
    ).model_dump_json()

    assert payload.casefold().count("sql") == 0
    assert "password" not in payload.casefold()
    assert "join" not in payload.casefold()
