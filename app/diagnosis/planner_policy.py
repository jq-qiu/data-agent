"""在合法计划集合上实施有界规划策略，并在模型选择失败时确定性回退。"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.diagnosis.capability import CapabilityAssessment
from app.diagnosis.plan_validator import AnalysisPlanValidator
from app.diagnosis.planner import AnalysisPlan, AnalysisPlanner
from app.diagnosis.question import ParsedAnalysisQuestion
from app.diagnosis.semantics import PlannerSemanticContext


class PlanningSource(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    LLM = "LLM"
    FALLBACK = "FALLBACK"


class LegalPlanOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: str = Field(pattern=r"^v\d+$")
    description: str = Field(min_length=1)
    plan: AnalysisPlan


class SelectorOption(BaseModel):
    """Safe logical summary passed to the bounded plan selector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: str = Field(pattern=r"^v\d+$")
    description: str = Field(min_length=1)


class PlanValidationFailure(RuntimeError):
    """Raised when a planner output fails the context validator."""


class PlanVariantProvider(Protocol):
    def options(
        self,
        question: ParsedAnalysisQuestion,
        capability: CapabilityAssessment,
    ) -> tuple[LegalPlanOption, ...]: ...


class PlanSelector(Protocol):
    async def choose(
        self,
        question: ParsedAnalysisQuestion,
        context: PlannerSemanticContext | None,
        options: tuple[SelectorOption, ...],
    ) -> str | None: ...


class V1PlanVariantProvider:
    """V1 questions have exactly one legal deterministic plan."""

    def __init__(self, planner: AnalysisPlanner | None = None) -> None:
        self._planner = planner or AnalysisPlanner()

    def options(
        self,
        question: ParsedAnalysisQuestion,
        capability: CapabilityAssessment,
    ) -> tuple[LegalPlanOption, ...]:
        plan = self._planner.plan(question, capability)
        return (
            LegalPlanOption(
                variant_id="v1",
                description="标准确定性诊断计划",
                plan=plan,
            ),
        )


class BoundedPlanResult(BaseModel):
    """记录最终合法计划、选择来源和回退原因，便于审计模型是否被调用。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan: AnalysisPlan
    source: PlanningSource
    model_calls: int = Field(ge=0, le=1)
    decision_reason: str = Field(min_length=1)
    validator_issues: tuple[str, ...] = ()


class BoundedPlannerPolicy:
    """Deterministic-first planning with at most one bounded LLM selection."""

    def __init__(
        self,
        validator: AnalysisPlanValidator | None = None,
        provider: PlanVariantProvider | None = None,
        selector: PlanSelector | None = None,
    ) -> None:
        self._validator = validator or AnalysisPlanValidator()
        self._provider = provider or V1PlanVariantProvider()
        self._selector = selector

    def plan(
        self,
        question: ParsedAnalysisQuestion,
        capability: CapabilityAssessment,
    ) -> BoundedPlanResult:
        # 同步入口仅接受唯一合法计划；多选需要异步 selector，因此这里明确拒绝。
        options = self._valid_options(question, capability)
        if len(options) == 1:
            return self._result(
                options[0],
                source=PlanningSource.DETERMINISTIC,
                model_calls=0,
                decision_reason="unique_legal_plan",
            )
        raise PlanValidationFailure(
            "multiple legal plans require the async bounded planner"
        )

    async def aplan(
        self,
        question: ParsedAnalysisQuestion,
        capability: CapabilityAssessment,
        context: PlannerSemanticContext | None = None,
    ) -> BoundedPlanResult:
        """唯一合法方案直接确定；多方案才选择一次，失败后不重试模型。"""

        # 所有候选先经过同一个 PlanValidator，模型永远看不到或选择不了非法计划。
        options = self._valid_options(question, capability)
        if len(options) == 1:
            return self._result(
                options[0],
                source=PlanningSource.DETERMINISTIC,
                model_calls=0,
                decision_reason="unique_legal_plan",
            )
        # 第一项是确定性默认方案；selector 缺失、异常或输出非法时都立即回到它。
        default = options[0]
        if self._selector is None:
            return self._result(
                default,
                source=PlanningSource.FALLBACK,
                model_calls=0,
                decision_reason="selector_unavailable_fallback",
            )

        summaries = tuple(
            SelectorOption(variant_id=option.variant_id, description=option.description)
            for option in options
        )
        try:
            # 选择器只收到逻辑摘要和 variant_id，不接触 SQL、表列、连接或原始数据。
            choice = await self._selector.choose(question, context, summaries)
        except Exception:  # noqa: BLE001 - any selector failure must fall back
            return self._result(
                default,
                source=PlanningSource.FALLBACK,
                model_calls=1,
                decision_reason="llm_failure_fallback",
            )

        if choice is None:
            return self._result(
                default,
                source=PlanningSource.FALLBACK,
                model_calls=1,
                decision_reason="llm_choice_empty_fallback",
            )
        selected = next(
            (option for option in options if option.variant_id == choice),
            None,
        )
        if selected is None:
            return self._result(
                default,
                source=PlanningSource.FALLBACK,
                model_calls=1,
                decision_reason="llm_choice_invalid_fallback",
                validator_issues=("unknown_variant",),
            )
        return self._result(
            selected,
            source=PlanningSource.LLM,
            model_calls=1,
            decision_reason="llm_choice_accepted",
        )

    def _valid_options(
        self,
        question: ParsedAnalysisQuestion,
        capability: CapabilityAssessment,
    ) -> tuple[LegalPlanOption, ...]:
        options = self._provider.options(question, capability)
        if not options:
            raise PlanValidationFailure("legal plan provider returned no options")
        valid: list[LegalPlanOption] = []
        for option in options:
            validation = self._validator.validate(option.plan, question, capability)
            if validation.valid:
                valid.append(option)
            else:
                raise PlanValidationFailure(
                    "legal plan provider returned an invalid option"
                )
        return tuple(valid)

    @staticmethod
    def _result(
        option: LegalPlanOption,
        *,
        source: PlanningSource,
        model_calls: int,
        decision_reason: str,
        validator_issues: tuple[str, ...] = (),
    ) -> BoundedPlanResult:
        return BoundedPlanResult(
            plan=option.plan,
            source=source,
            model_calls=model_calls,
            decision_reason=decision_reason,
            validator_issues=validator_issues,
        )
