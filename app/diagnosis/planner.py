"""把已解析问题与运行时能力转换为数量受限、依赖明确的结构化 AnalysisTask。"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.diagnosis.capability import (
    AnalysisMethod,
    CapabilityAssessment,
    DataQualityStatus,
)
from app.diagnosis.question import (
    AnalysisDimension,
    AnalysisScope,
    CandidateFactor,
    DatePeriod,
    ParsedAnalysisQuestion,
)


class TaskMethod(StrEnum):
    PERIOD_COMPARISON = "period_comparison"
    METRIC_DECOMPOSITION = "metric_decomposition"
    DIMENSION_CONTRIBUTION = "dimension_contribution"
    CANDIDATE_VALIDATION = "candidate_validation"


class PlanStopReason(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_QUALITY_FAILED = "DATA_QUALITY_FAILED"


_TASK_METHOD_ORDER = {method: index for index, method in enumerate(TaskMethod)}
_DIMENSION_ORDER = {
    dimension: index for index, dimension in enumerate(AnalysisDimension)
}
_FACTOR_ORDER = {factor: index for index, factor in enumerate(CandidateFactor)}
_FACTOR_CAPABILITY = {
    CandidateFactor.TRAFFIC: AnalysisMethod.TRAFFIC_VALIDATION,
    CandidateFactor.PROMOTION: AnalysisMethod.PROMOTION_VALIDATION,
    CandidateFactor.INVENTORY: AnalysisMethod.INVENTORY_VALIDATION,
}


class AnalysisTask(BaseModel):
    """类型化分析工具调用，只允许白名单 method、Scope、维度、因素和显式依赖。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(pattern=r"^T[1-4]$")
    method: TaskMethod
    metric: Literal["gmv"]
    current_period: DatePeriod
    baseline_period: DatePeriod
    scope: AnalysisScope
    dimensions: tuple[AnalysisDimension, ...] = ()
    factors: tuple[CandidateFactor, ...] = ()
    depends_on: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_task_contract(self) -> AnalysisTask:
        if self.baseline_period.end >= self.current_period.start:
            raise ValueError("baseline period must precede current period")
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("task dimensions must be unique")
        if len(self.factors) != len(set(self.factors)):
            raise ValueError("task factors must be unique")
        if self.dimensions != tuple(
            sorted(self.dimensions, key=_DIMENSION_ORDER.__getitem__)
        ):
            raise ValueError("task dimensions must use frozen order")
        if self.factors != tuple(sorted(self.factors, key=_FACTOR_ORDER.__getitem__)):
            raise ValueError("task factors must use frozen order")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("task dependencies must be unique")
        if any(not dependency.startswith("T") for dependency in self.depends_on):
            raise ValueError("task dependencies must use task identifiers")

        is_dimension_task = self.method is TaskMethod.DIMENSION_CONTRIBUTION
        is_factor_task = self.method is TaskMethod.CANDIDATE_VALIDATION
        if is_dimension_task != bool(self.dimensions):
            raise ValueError("only dimension contribution requires dimensions")
        if is_factor_task != bool(self.factors):
            raise ValueError("only candidate validation requires factors")
        if self.method is TaskMethod.PERIOD_COMPARISON:
            if self.depends_on:
                raise ValueError("period comparison cannot have dependencies")
        elif self.depends_on != ("T1",):
            raise ValueError("downstream tasks must depend only on T1")
        return self


class AnalysisPlan(BaseModel):
    """数量受限且依赖有序的任务集合；空任务计划必须给出停止原因。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_version: Literal["analysis-plan-v1"] = "analysis-plan-v1"
    tasks: tuple[AnalysisTask, ...] = Field(max_length=4)
    stop_reason: PlanStopReason | None = None
    missing_evidence: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_plan_contract(self) -> AnalysisPlan:
        if len(self.missing_evidence) != len(set(self.missing_evidence)):
            raise ValueError("missing evidence entries must be unique")
        if not self.tasks:
            if self.stop_reason is None:
                raise ValueError("an empty plan requires a stop reason")
            return self
        if self.stop_reason is not None:
            raise ValueError("an executable plan cannot include a stop reason")

        expected_ids = tuple(f"T{index}" for index in range(1, len(self.tasks) + 1))
        actual_ids = tuple(task.task_id for task in self.tasks)
        if actual_ids != expected_ids:
            raise ValueError("task identifiers must be consecutive and ordered")
        methods = tuple(task.method for task in self.tasks)
        if len(methods) != len(set(methods)):
            raise ValueError("task methods must be unique")
        if methods != tuple(sorted(methods, key=_TASK_METHOD_ORDER.__getitem__)):
            raise ValueError("task methods must use frozen order")
        if methods[0] is not TaskMethod.PERIOD_COMPARISON:
            raise ValueError("period comparison must be the first task")
        if any(
            task.depends_on != (() if index == 0 else ("T1",))
            for index, task in enumerate(self.tasks)
        ):
            raise ValueError("plan tasks contain an invalid dependency")
        return self


class AnalysisPlanner:
    """Creates a bounded deterministic plan from accepted schemas only."""

    def plan(
        self,
        question: ParsedAnalysisQuestion,
        capability: CapabilityAssessment,
    ) -> AnalysisPlan:
        """从问题与 supported_methods 的交集生成最多四类任务，不生成 SQL。"""

        # Capability 已把“理论支持”收窄为“当前切片可执行”，Planner 只读取这个白名单。
        supported = set(capability.supported_methods)
        if AnalysisMethod.PERIOD_COMPARISON not in supported:
            reason = (
                PlanStopReason.DATA_QUALITY_FAILED
                if capability.data_quality_status is DataQualityStatus.FAIL
                else PlanStopReason.INSUFFICIENT_DATA
            )
            # 连期间对比都不可用时直接生成带原因的空计划，后续查询和分析节点不会运行。
            return AnalysisPlan(
                tasks=(),
                stop_reason=reason,
                missing_evidence=capability.missing_evidence,
            )

        task_inputs: list[
            tuple[TaskMethod, tuple[AnalysisDimension, ...], tuple[CandidateFactor, ...]]
        ] = [(TaskMethod.PERIOD_COMPARISON, (), ())]
        if AnalysisMethod.METRIC_DECOMPOSITION in supported:
            task_inputs.append((TaskMethod.METRIC_DECOMPOSITION, (), ()))

        # 维度任务只取“用户明确请求”和“运行时可用”的交集，不能擅自增加下钻方向。
        requested_dimensions = set(question.requested_dimensions)
        available_dimensions = set(capability.available_dimensions)
        dimensions = tuple(
            dimension
            for dimension in AnalysisDimension
            if dimension in requested_dimensions and dimension in available_dimensions
        )
        if AnalysisMethod.DIMENSION_CONTRIBUTION in supported and dimensions:
            task_inputs.append((TaskMethod.DIMENSION_CONTRIBUTION, dimensions, ()))

        # 每个候选因素还必须有对应 Evidence 方法可用，缺数据的因素不会进入任务。
        requested_factors = set(question.requested_factors)
        factors = tuple(
            factor
            for factor in CandidateFactor
            if factor in requested_factors and _FACTOR_CAPABILITY[factor] in supported
        )
        if factors:
            task_inputs.append((TaskMethod.CANDIDATE_VALIDATION, (), factors))

        # 除 T1 外的任务都显式依赖期间对比，确保先确认异常再解释变化来源。
        tasks = tuple(
            AnalysisTask(
                task_id=f"T{index}",
                method=method,
                metric=question.target_metric,
                current_period=question.current_period,
                baseline_period=question.baseline_period,
                scope=question.scope,
                dimensions=dimensions_for_task,
                factors=factors_for_task,
                depends_on=() if index == 1 else ("T1",),
            )
            for index, (method, dimensions_for_task, factors_for_task) in enumerate(
                task_inputs, start=1
            )
        )
        return AnalysisPlan(
            tasks=tasks,
            missing_evidence=capability.missing_evidence,
        )


class AnalysisPlannerNode:
    """Reads serializable question/capability values and emits only a plan."""

    def __init__(self, planner: AnalysisPlanner | None = None) -> None:
        self._planner = planner or AnalysisPlanner()

    async def __call__(self, state: Mapping[str, Any]) -> dict[str, Any]:
        question = ParsedAnalysisQuestion.model_validate(state.get("parsed_question"))
        capability = CapabilityAssessment.model_validate(state.get("capability"))
        plan = self._planner.plan(question, capability)
        return {"analysis_plan": plan.model_dump(mode="json")}
