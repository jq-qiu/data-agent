from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.diagnosis.capability import (
    AnalysisMethod,
    CapabilityAssessment,
    DataQualityStatus,
)
from app.diagnosis.planner import (
    AnalysisPlan,
    AnalysisTask,
    PlanStopReason,
    TaskMethod,
)
from app.diagnosis.question import CandidateFactor, ParsedAnalysisQuestion


class PlanValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class PlanValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    issues: tuple[PlanValidationIssue, ...] = ()

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)


class AnalysisPlanValidator:
    """Validates a plan against the parsed question and runtime capability."""

    _FACTOR_METHOD: ClassVar[dict[CandidateFactor, AnalysisMethod]] = {
        CandidateFactor.TRAFFIC: AnalysisMethod.TRAFFIC_VALIDATION,
        CandidateFactor.PROMOTION: AnalysisMethod.PROMOTION_VALIDATION,
        CandidateFactor.INVENTORY: AnalysisMethod.INVENTORY_VALIDATION,
    }

    def validate(
        self,
        plan: AnalysisPlan,
        question: ParsedAnalysisQuestion,
        capability: CapabilityAssessment,
    ) -> PlanValidationResult:
        issues: list[PlanValidationIssue] = []
        if plan.tasks:
            for task in plan.tasks:
                issues.extend(self._task_issues(task, question, capability))
        else:
            issues.extend(self._empty_plan_issues(plan, capability))
        return self._result(issues)

    def _task_issues(
        self,
        task: AnalysisTask,
        question: ParsedAnalysisQuestion,
        capability: CapabilityAssessment,
    ) -> list[PlanValidationIssue]:
        issues: list[PlanValidationIssue] = []
        if task.metric != question.target_metric:
            issues.append(
                self._issue(
                    "metric_mutation",
                    f"task {task.task_id} changes the parsed metric",
                )
            )
        if task.current_period != question.current_period:
            issues.append(
                self._issue(
                    "current_period_mutation",
                    f"task {task.task_id} changes the current period",
                )
            )
        if task.baseline_period != question.baseline_period:
            issues.append(
                self._issue(
                    "baseline_period_mutation",
                    f"task {task.task_id} changes the baseline period",
                )
            )
        if task.scope != question.scope:
            issues.append(
                self._issue(
                    "scope_mutation",
                    f"task {task.task_id} changes the parsed scope",
                )
            )

        if task.method is TaskMethod.PERIOD_COMPARISON:
            if AnalysisMethod.PERIOD_COMPARISON not in capability.supported_methods:
                issues.append(self._unsupported(task))
        elif task.method is TaskMethod.METRIC_DECOMPOSITION:
            if AnalysisMethod.METRIC_DECOMPOSITION not in capability.supported_methods:
                issues.append(self._unsupported(task))
        elif task.method is TaskMethod.DIMENSION_CONTRIBUTION:
            if AnalysisMethod.DIMENSION_CONTRIBUTION not in capability.supported_methods:
                issues.append(self._unsupported(task))
            requested_dimensions = set(question.requested_dimensions)
            available_dimensions = set(capability.available_dimensions)
            for dimension in task.dimensions:
                if dimension not in requested_dimensions:
                    issues.append(
                        self._issue(
                            "unrequested_dimension",
                            f"task {task.task_id} uses an unrequested dimension",
                        )
                    )
                if dimension not in available_dimensions:
                    issues.append(
                        self._issue(
                            "dimension_not_available",
                            f"task {task.task_id} uses an unavailable dimension",
                        )
                    )
        elif task.method is TaskMethod.CANDIDATE_VALIDATION:
            requested_factors = set(question.requested_factors)
            for factor in task.factors:
                method = self._FACTOR_METHOD[factor]
                if factor not in requested_factors:
                    issues.append(
                        self._issue(
                            "unrequested_factor",
                            f"task {task.task_id} uses an unrequested factor",
                        )
                    )
                if method not in capability.supported_methods:
                    issues.append(
                        self._issue(
                            "factor_validation_unavailable",
                            f"task {task.task_id} uses an unsupported factor validation",
                        )
                    )
        else:  # pragma: no cover - guarded by TaskMethod enum
            issues.append(self._unsupported(task))
        return issues

    def _empty_plan_issues(
        self,
        plan: AnalysisPlan,
        capability: CapabilityAssessment,
    ) -> list[PlanValidationIssue]:
        if plan.stop_reason is None:
            return [self._issue("empty_plan_without_stop_reason", "empty plan lacks a stop reason")]

        quality_failed = capability.data_quality_status is DataQualityStatus.FAIL
        period_supported = AnalysisMethod.PERIOD_COMPARISON in capability.supported_methods
        if plan.stop_reason is PlanStopReason.DATA_QUALITY_FAILED and not quality_failed:
            return [
                self._issue(
                    "inconsistent_stop_reason",
                    "data quality stop reason does not match capability",
                )
            ]
        if plan.stop_reason is PlanStopReason.INSUFFICIENT_DATA and quality_failed:
            return [
                self._issue(
                    "inconsistent_stop_reason",
                    "insufficient data stop reason does not match data quality",
                )
            ]
        if plan.stop_reason is PlanStopReason.INSUFFICIENT_DATA and period_supported:
            return [
                self._issue(
                    "inconsistent_stop_reason",
                    "period comparison is supported but the plan stopped",
                )
            ]
        return []

    @staticmethod
    def _unsupported(task: AnalysisTask) -> PlanValidationIssue:
        return PlanValidationIssue(
            code="unsupported_method",
            detail=f"task {task.task_id} selects an unsupported method",
        )

    @staticmethod
    def _issue(code: str, detail: str) -> PlanValidationIssue:
        return PlanValidationIssue(code=code, detail=detail)

    @staticmethod
    def _result(issues: list[PlanValidationIssue]) -> PlanValidationResult:
        deduplicated: list[PlanValidationIssue] = []
        seen: set[tuple[str, str]] = set()
        for issue in issues:
            identity = (issue.code, issue.detail)
            if identity in seen:
                continue
            seen.add(identity)
            deduplicated.append(issue)
        return PlanValidationResult(
            valid=not deduplicated,
            issues=tuple(deduplicated),
        )
