"""对受控查询结果执行确定性期间比较、Shapley 拆解、维度贡献和候选因素计算。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.diagnosis.planner import AnalysisPlan, AnalysisTask, TaskMethod
from app.diagnosis.query import AnalysisQueryResult, MetricLineage
from app.diagnosis.question import AnalysisDimension, CandidateFactor

DERIVED_QUANTUM = Decimal("0.000001")
RECONCILIATION_TOLERANCE = Decimal("0.01")
MAX_ANALYSIS_RESULTS = 5
_NUMERIC_PATTERN = re.compile(r"^[+-]?(?:0|[1-9]\d*)(?:\.\d+)?$")


class AnalysisErrorCode(StrEnum):
    INVALID_ANALYSIS_INPUT = "INVALID_ANALYSIS_INPUT"
    MISSING_QUERY_RESULT = "MISSING_QUERY_RESULT"
    DUPLICATE_QUERY_RESULT = "DUPLICATE_QUERY_RESULT"
    METRIC_VERSION_MISMATCH = "METRIC_VERSION_MISMATCH"
    NUMERIC_RECONCILIATION_FAILED = "NUMERIC_RECONCILIATION_FAILED"


class AnalysisWarning(StrEnum):
    BASELINE_ZERO = "BASELINE_ZERO"
    AOV_DENOMINATOR_ZERO = "AOV_DENOMINATOR_ZERO"
    DIMENSION_TOTAL_MISMATCH = "DIMENSION_TOTAL_MISMATCH"
    TOTAL_DELTA_NEAR_ZERO = "TOTAL_DELTA_NEAR_ZERO"
    RATIO_DENOMINATOR_ZERO_OR_MISSING = "RATIO_DENOMINATOR_ZERO_OR_MISSING"


class AnalysisMethod(StrEnum):
    PERIOD_COMPARISON = "period_comparison"
    GMV_SHAPLEY = "gmv_shapley"
    DIMENSION_CONTRIBUTION = "dimension_contribution"
    CANDIDATE_FACTORS = "candidate_factors"


class ReconciliationStatus(StrEnum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"


class AnalysisError(ValueError):
    """Closed failure with a stable machine-readable error code."""

    def __init__(self, code: AnalysisErrorCode, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"{code.value}: {reason}")


class MetricChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    baseline_value: Decimal | None
    current_value: Decimal | None
    absolute_delta: Decimal | None
    change_rate: Decimal | None


class PeriodComparisonValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["period_comparison"] = "period_comparison"
    change: MetricChange


class GmvShapleyValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["gmv_shapley"] = "gmv_shapley"
    baseline_gmv: Decimal
    current_gmv: Decimal
    baseline_order_count: Decimal
    current_order_count: Decimal
    baseline_aov: Decimal | None
    current_aov: Decimal | None
    order_count_contribution: Decimal | None
    aov_contribution: Decimal | None
    total_delta: Decimal


class DimensionMemberContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension_value: str = Field(min_length=1)
    baseline_value: Decimal
    current_value: Decimal
    absolute_delta: Decimal
    contribution: Decimal | None


class DimensionContributionValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["dimension_contribution"] = "dimension_contribution"
    dimension: AnalysisDimension
    total_delta: Decimal
    members: tuple[DimensionMemberContribution, ...]


class CandidateFactorAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    factor: CandidateFactor
    primary_metric: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    primary_change: MetricChange
    conversion_rate_change: MetricChange
    order_count_change: MetricChange


class CandidateFactorValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["candidate_factors"] = "candidate_factors"
    factors: tuple[CandidateFactorAnalysis, ...]


AnalysisValues = Annotated[
    PeriodComparisonValues
    | GmvShapleyValues
    | DimensionContributionValues
    | CandidateFactorValues,
    Field(discriminator="kind"),
]


class NumericReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ReconciliationStatus
    expected: Decimal
    actual: Decimal
    difference: Decimal
    tolerance: Decimal = RECONCILIATION_TOLERANCE


class AnalysisResult(BaseModel):
    """确定性计算产物，包含输入 Query ID、指标版本、对账状态和警告。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_result_id: str = Field(pattern=r"^A\d{3}$")
    method: AnalysisMethod
    input_query_ids: tuple[str, ...] = Field(min_length=1)
    metric_versions: tuple[MetricLineage, ...] = Field(min_length=1)
    values: AnalysisValues
    reconciliation: NumericReconciliation | None = None
    warnings: tuple[AnalysisWarning, ...] = ()

    @model_validator(mode="after")
    def method_matches_values(self) -> AnalysisResult:
        if self.method.value != self.values.kind:
            raise ValueError("analysis method must match the values discriminator")
        return self


class PeriodComparator:
    """计算本期与基期绝对变化；基期为零时保留事实并将变化率降级为空。"""

    def analyze(self, result: AnalysisQueryResult) -> tuple[PeriodComparisonValues, tuple[AnalysisWarning, ...]]:
        # period_role 把两行结果明确标成 baseline/current，避免依赖数据库返回顺序。
        rows = _period_rows(result, required_fields=("gmv",))
        baseline = _measure(rows["baseline"], "gmv")
        current = _measure(rows["current"], "gmv")
        change, warnings = _metric_change("gmv", baseline, current)
        return PeriodComparisonValues(change=change), warnings


class GmvShapleyAnalyzer:
    """用 Decimal 执行 GMV=订单量×AOV 的对称两因素拆解，并强制对账。"""

    def analyze(
        self, result: AnalysisQueryResult
    ) -> tuple[GmvShapleyValues, NumericReconciliation | None, tuple[AnalysisWarning, ...]]:
        rows = _period_rows(result, required_fields=("gmv", "order_count"))
        baseline_gmv = _measure(rows["baseline"], "gmv")
        current_gmv = _measure(rows["current"], "gmv")
        baseline_orders = _count(rows["baseline"], "order_count")
        current_orders = _count(rows["current"], "order_count")

        for role, gmv, orders in (
            ("baseline", baseline_gmv, baseline_orders),
            ("current", current_gmv, current_orders),
        ):
            if orders == 0 and gmv != 0:
                raise AnalysisError(
                    AnalysisErrorCode.NUMERIC_RECONCILIATION_FAILED,
                    f"{role}_gmv_nonzero_with_zero_orders",
                )

        # 总变化直接来自查询结果，后面的两个贡献项必须加总回这个基准值。
        total_delta = current_gmv - baseline_gmv
        # 任一期间订单量为零时 AOV 无法完整定义：保留 GMV/订单事实，但不编造贡献值。
        if baseline_orders == 0 or current_orders == 0:
            values = GmvShapleyValues(
                baseline_gmv=baseline_gmv,
                current_gmv=current_gmv,
                baseline_order_count=baseline_orders,
                current_order_count=current_orders,
                baseline_aov=None if baseline_orders == 0 else _derived(baseline_gmv / baseline_orders),
                current_aov=None if current_orders == 0 else _derived(current_gmv / current_orders),
                order_count_contribution=None,
                aov_contribution=None,
                total_delta=total_delta,
            )
            return values, None, (AnalysisWarning.AOV_DENOMINATOR_ZERO,)

        # 财务值使用 Decimal 和固定精度，避免二进制浮点误差破坏贡献项对账。
        with localcontext() as context:
            context.prec = 28
            context.rounding = ROUND_HALF_EVEN
            baseline_aov_raw = baseline_gmv / baseline_orders
            current_aov_raw = current_gmv / current_orders
            # Shapley 对两个变化顺序取平均，公平分配订单量与 AOV 的交互项。
            order_contribution_raw = (
                (current_orders - baseline_orders)
                * (current_aov_raw + baseline_aov_raw)
                / 2
            )
            aov_contribution_raw = (
                (current_aov_raw - baseline_aov_raw)
                * (current_orders + baseline_orders)
                / 2
            )
            actual = order_contribution_raw + aov_contribution_raw
        # 贡献项与实际 GMV 变化超过金额容差时直接失败，不能带着不平衡数字生成报告。
        difference = actual - total_delta
        if abs(difference) > RECONCILIATION_TOLERANCE:
            raise AnalysisError(
                AnalysisErrorCode.NUMERIC_RECONCILIATION_FAILED,
                "gmv_shapley_total_mismatch",
            )
        reconciliation = NumericReconciliation(
            status=ReconciliationStatus.PASS,
            expected=total_delta,
            actual=_derived(actual),
            difference=_derived(difference),
        )
        values = GmvShapleyValues(
            baseline_gmv=baseline_gmv,
            current_gmv=current_gmv,
            baseline_order_count=baseline_orders,
            current_order_count=current_orders,
            baseline_aov=_derived(baseline_aov_raw),
            current_aov=_derived(current_aov_raw),
            order_count_contribution=_derived(order_contribution_raw),
            aov_contribution=_derived(aov_contribution_raw),
            total_delta=total_delta,
        )
        return values, reconciliation, ()


class DimensionContributionAnalyzer:
    """按互斥维度汇总成员变化；只有与整体变化对账后才计算贡献率。"""

    def analyze(
        self,
        result: AnalysisQueryResult,
        period_result: AnalysisQueryResult,
        dimension: AnalysisDimension,
    ) -> tuple[
        DimensionContributionValues,
        NumericReconciliation,
        tuple[AnalysisWarning, ...],
    ]:
        overall_rows = _period_rows(period_result, required_fields=("gmv",))
        overall_delta = _measure(overall_rows["current"], "gmv") - _measure(
            overall_rows["baseline"], "gmv"
        )
        member_values: dict[str, dict[str, Decimal]] = {}
        seen: set[tuple[str, str]] = set()
        for row in result.rows:
            role = _role(row)
            member = row.get("dimension_value")
            if not isinstance(member, str) or not member:
                raise _invalid("dimension_value_invalid")
            key = (role, member)
            if key in seen:
                raise AnalysisError(
                    AnalysisErrorCode.DUPLICATE_QUERY_RESULT,
                    "duplicate_dimension_period_member",
                )
            seen.add(key)
            member_values.setdefault(member, {})[role] = _measure(row, "gmv")
        if not member_values:
            raise _invalid("dimension_rows_empty")

        member_deltas = {
            member: periods.get("current", Decimal(0))
            - periods.get("baseline", Decimal(0))
            for member, periods in member_values.items()
        }
        # 所有成员绝对变化之和必须回到同口径整体变化，才说明维度互斥且覆盖完整。
        grouped_delta = sum(member_deltas.values(), Decimal(0))
        difference = grouped_delta - overall_delta
        reconciled = abs(difference) <= RECONCILIATION_TOLERANCE
        near_zero = abs(overall_delta) <= RECONCILIATION_TOLERANCE
        warnings: list[AnalysisWarning] = []
        if not reconciled:
            warnings.append(AnalysisWarning.DIMENSION_TOTAL_MISMATCH)
        if near_zero:
            warnings.append(AnalysisWarning.TOTAL_DELTA_NEAR_ZERO)

        # 总变化接近零或分组未对账时，比例会失去解释意义，因此只保留绝对变化。
        members = tuple(
            DimensionMemberContribution(
                dimension_value=member,
                baseline_value=member_values[member].get("baseline", Decimal(0)),
                current_value=member_values[member].get("current", Decimal(0)),
                absolute_delta=member_deltas[member],
                contribution=(
                    _derived(member_deltas[member] / overall_delta)
                    if reconciled and not near_zero
                    else None
                ),
            )
            for member in sorted(member_values)
        )
        reconciliation = NumericReconciliation(
            status=(
                ReconciliationStatus.PASS if reconciled else ReconciliationStatus.DEGRADED
            ),
            expected=overall_delta,
            actual=grouped_delta,
            difference=difference,
        )
        return (
            DimensionContributionValues(
                dimension=dimension,
                total_delta=overall_delta,
                members=members,
            ),
            reconciliation,
            tuple(warnings),
        )


class CandidateFactorAnalyzer:
    """重算流量、促销、库存相关比率，输出关联链所需数值而不判断因果。"""

    def analyze(
        self, result: AnalysisQueryResult, factors: tuple[CandidateFactor, ...]
    ) -> tuple[CandidateFactorValues, tuple[AnalysisWarning, ...]]:
        required = ["order_count"]
        if CandidateFactor.TRAFFIC in factors:
            required.append("visitors")
        if CandidateFactor.PROMOTION in factors:
            required.extend(("promoted_sku_count", "active_sku_count"))
        if CandidateFactor.INVENTORY in factors:
            required.extend(("available_sku_count", "required_sku_count"))
        rows = _period_rows(result, required_fields=tuple(required), optional_fields=("visitors",))
        baseline_orders = _count(rows["baseline"], "order_count")
        current_orders = _count(rows["current"], "order_count")
        baseline_visitors = _optional_count(rows["baseline"], "visitors")
        current_visitors = _optional_count(rows["current"], "visitors")
        # Conversion 等比率由聚合后的分子/分母重算，不能把每日比例直接相加或平均。
        conversion_baseline = _ratio(baseline_orders, baseline_visitors)
        conversion_current = _ratio(current_orders, current_visitors)
        warnings: list[AnalysisWarning] = []
        if conversion_baseline is None or conversion_current is None:
            warnings.append(AnalysisWarning.RATIO_DENOMINATOR_ZERO_OR_MISSING)

        order_change, order_warnings = _metric_change(
            "order_count", baseline_orders, current_orders
        )
        conversion_change, conversion_warnings = _metric_change(
            "conversion_rate", conversion_baseline, conversion_current
        )
        warnings.extend(order_warnings)
        warnings.extend(conversion_warnings)

        analyses: list[CandidateFactorAnalysis] = []
        # 三类因素共用订单和转化链路，但各自的主指标分子/分母不同。
        for factor in factors:
            if factor is CandidateFactor.TRAFFIC:
                primary_metric = "visitors"
                baseline_primary = baseline_visitors
                current_primary = current_visitors
            elif factor is CandidateFactor.PROMOTION:
                primary_metric = "promotion_coverage"
                baseline_primary = _ratio(
                    _count(rows["baseline"], "promoted_sku_count"),
                    _optional_count(rows["baseline"], "active_sku_count"),
                )
                current_primary = _ratio(
                    _count(rows["current"], "promoted_sku_count"),
                    _optional_count(rows["current"], "active_sku_count"),
                )
            else:
                primary_metric = "inventory_fill_rate"
                baseline_primary = _ratio(
                    _count(rows["baseline"], "available_sku_count"),
                    _optional_count(rows["baseline"], "required_sku_count"),
                )
                current_primary = _ratio(
                    _count(rows["current"], "available_sku_count"),
                    _optional_count(rows["current"], "required_sku_count"),
                )
            if baseline_primary is None or current_primary is None:
                warnings.append(AnalysisWarning.RATIO_DENOMINATOR_ZERO_OR_MISSING)
            primary_change, primary_warnings = _metric_change(
                primary_metric, baseline_primary, current_primary
            )
            warnings.extend(primary_warnings)
            analyses.append(
                CandidateFactorAnalysis(
                    factor=factor,
                    primary_metric=primary_metric,
                    primary_change=primary_change,
                    conversion_rate_change=conversion_change,
                    order_count_change=order_change,
                )
            )
        return CandidateFactorValues(factors=tuple(analyses)), tuple(dict.fromkeys(warnings))


class DeterministicAnalyzer:
    """Turns a frozen plan and validated query results into numeric facts only."""

    # LLM 不参与财务计算，确保同一输入得到可复现、可逐项对账的结果。

    def __init__(self) -> None:
        self._period = PeriodComparator()
        self._shapley = GmvShapleyAnalyzer()
        self._dimension = DimensionContributionAnalyzer()
        self._candidate = CandidateFactorAnalyzer()

    def analyze(
        self, plan: AnalysisPlan, query_results: Sequence[AnalysisQueryResult]
    ) -> tuple[AnalysisResult, ...]:
        if not plan.tasks:
            if query_results:
                raise _invalid("stopped_plan_has_query_results")
            return ()
        results_by_task = self._validate_inputs(plan, query_results)
        period_query = results_by_task["T1"][0]
        output: list[AnalysisResult] = []

        for task in plan.tasks:
            task_results = results_by_task[task.task_id]
            if task.method is TaskMethod.PERIOD_COMPARISON:
                period_values, warnings = self._period.analyze(task_results[0])
                output.append(
                    self._result(
                        output,
                        AnalysisMethod.PERIOD_COMPARISON,
                        task_results,
                        period_values,
                        warnings=warnings,
                    )
                )
            elif task.method is TaskMethod.METRIC_DECOMPOSITION:
                shapley_values, reconciliation, warnings = self._shapley.analyze(
                    task_results[0]
                )
                output.append(
                    self._result(
                        output,
                        AnalysisMethod.GMV_SHAPLEY,
                        task_results,
                        shapley_values,
                        reconciliation,
                        warnings,
                    )
                )
            elif task.method is TaskMethod.DIMENSION_CONTRIBUTION:
                by_role = {item.query_role: item for item in task_results}
                for dimension in task.dimensions:
                    query = by_role[f"dimension_contribution:{dimension.value}"]
                    dimension_values, reconciliation, warnings = self._dimension.analyze(
                        query, period_query, dimension
                    )
                    output.append(
                        self._result(
                            output,
                            AnalysisMethod.DIMENSION_CONTRIBUTION,
                            (period_query, query),
                            dimension_values,
                            reconciliation,
                            warnings,
                        )
                    )
            else:
                candidate_values, warnings = self._candidate.analyze(
                    task_results[0], task.factors
                )
                output.append(
                    self._result(
                        output,
                        AnalysisMethod.CANDIDATE_FACTORS,
                        task_results,
                        candidate_values,
                        warnings=warnings,
                    )
                )

        if len(output) > MAX_ANALYSIS_RESULTS:
            raise _invalid("analysis_result_limit_exceeded")
        return tuple(output)

    def _validate_inputs(
        self, plan: AnalysisPlan, query_results: Sequence[AnalysisQueryResult]
    ) -> dict[str, tuple[AnalysisQueryResult, ...]]:
        query_ids = [result.query_id for result in query_results]
        if len(query_ids) != len(set(query_ids)):
            raise AnalysisError(
                AnalysisErrorCode.DUPLICATE_QUERY_RESULT, "duplicate_query_id"
            )
        tasks = {task.task_id: task for task in plan.tasks}
        grouped: dict[str, list[AnalysisQueryResult]] = {task_id: [] for task_id in tasks}
        versions: dict[str, str] = {}
        for result in query_results:
            task = tasks.get(result.task_id)
            if task is None or result.method is not task.method:
                raise _invalid("query_result_task_mismatch")
            for lineage in result.metric_versions:
                previous = versions.setdefault(lineage.metric_id, lineage.version)
                if previous != lineage.version:
                    raise AnalysisError(
                        AnalysisErrorCode.METRIC_VERSION_MISMATCH,
                        f"metric_version_mismatch:{lineage.metric_id}",
                    )
            grouped[result.task_id].append(result)

        validated: dict[str, tuple[AnalysisQueryResult, ...]] = {}
        for task in plan.tasks:
            actual = grouped[task.task_id]
            expected_roles = _expected_roles(task)
            actual_roles = tuple(item.query_role for item in actual)
            if not actual:
                raise AnalysisError(
                    AnalysisErrorCode.MISSING_QUERY_RESULT,
                    f"missing_query_result:{task.task_id}",
                )
            if len(actual_roles) != len(set(actual_roles)):
                raise AnalysisError(
                    AnalysisErrorCode.DUPLICATE_QUERY_RESULT,
                    f"duplicate_query_role:{task.task_id}",
                )
            if set(actual_roles) != set(expected_roles):
                raise AnalysisError(
                    AnalysisErrorCode.MISSING_QUERY_RESULT,
                    f"query_role_mismatch:{task.task_id}",
                )
            role_order = {role: index for index, role in enumerate(expected_roles)}
            validated[task.task_id] = tuple(
                sorted(actual, key=lambda item: role_order[item.query_role])
            )
        return validated

    @staticmethod
    def _result(
        existing: Sequence[AnalysisResult],
        method: AnalysisMethod,
        inputs: Sequence[AnalysisQueryResult],
        values: AnalysisValues,
        reconciliation: NumericReconciliation | None = None,
        warnings: tuple[AnalysisWarning, ...] = (),
    ) -> AnalysisResult:
        lineage: list[MetricLineage] = []
        seen: set[tuple[str, str]] = set()
        for query in inputs:
            for item in query.metric_versions:
                key = (item.metric_id, item.version)
                if key not in seen:
                    seen.add(key)
                    lineage.append(item)
        if not lineage:
            raise _invalid("metric_lineage_empty")
        return AnalysisResult(
            analysis_result_id=f"A{len(existing) + 1:03d}",
            method=method,
            input_query_ids=tuple(query.query_id for query in inputs),
            metric_versions=tuple(lineage),
            values=values,
            reconciliation=reconciliation,
            warnings=warnings,
        )


class DeterministicAnalyzerNode:
    def __init__(self, analyzer: DeterministicAnalyzer | None = None) -> None:
        self._analyzer = analyzer or DeterministicAnalyzer()

    def __call__(self, state: Mapping[str, Any]) -> dict[str, object]:
        plan = AnalysisPlan.model_validate(state.get("analysis_plan"))
        raw_results = state.get("query_results")
        if not isinstance(raw_results, (list, tuple)):
            raise _invalid("query_results_not_a_sequence")
        query_results = tuple(
            AnalysisQueryResult.model_validate(result) for result in raw_results
        )
        analysis_results = self._analyzer.analyze(plan, query_results)
        return {
            "analysis_results": [
                result.model_dump(mode="json") for result in analysis_results
            ]
        }


def _expected_roles(task: AnalysisTask) -> tuple[str, ...]:
    if task.method is TaskMethod.PERIOD_COMPARISON:
        return ("period_comparison",)
    if task.method is TaskMethod.METRIC_DECOMPOSITION:
        return ("metric_decomposition",)
    if task.method is TaskMethod.CANDIDATE_VALIDATION:
        return ("candidate_validation",)
    return tuple(
        f"dimension_contribution:{dimension.value}" for dimension in task.dimensions
    )


def _period_rows(
    result: AnalysisQueryResult,
    *,
    required_fields: tuple[str, ...],
    optional_fields: tuple[str, ...] = (),
) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in result.rows:
        role = _role(row)
        if role in rows:
            raise AnalysisError(
                AnalysisErrorCode.DUPLICATE_QUERY_RESULT,
                f"duplicate_period_role:{role}",
            )
        for field in required_fields:
            if field not in row and field not in optional_fields:
                raise _invalid(f"missing_numeric_field:{field}")
        rows[role] = row
    if set(rows) != {"baseline", "current"}:
        raise _invalid("baseline_and_current_rows_required")
    return rows


def _role(row: Mapping[str, Any]) -> str:
    role = row.get("period_role")
    if role not in ("baseline", "current"):
        raise _invalid("period_role_invalid")
    return str(role)


def _measure(row: Mapping[str, Any], field: str) -> Decimal:
    value = _decimal(row.get(field), field)
    if value < 0:
        raise _invalid(f"negative_measure:{field}")
    return value


def _count(row: Mapping[str, Any], field: str) -> Decimal:
    value = _measure(row, field)
    if value != value.to_integral_value():
        raise _invalid(f"non_integral_count:{field}")
    return value


def _optional_count(row: Mapping[str, Any], field: str) -> Decimal | None:
    raw = row.get(field)
    if raw is None:
        return None
    return _count(row, field)


def _decimal(raw: Any, field: str) -> Decimal:
    if isinstance(raw, (bool, float)):
        raise _invalid(f"unsafe_numeric_type:{field}")
    if isinstance(raw, int):
        value = Decimal(raw)
    elif isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, str) and _NUMERIC_PATTERN.fullmatch(raw):
        try:
            value = Decimal(raw)
        except InvalidOperation as error:
            raise _invalid(f"invalid_numeric_value:{field}") from error
    else:
        raise _invalid(f"invalid_numeric_value:{field}")
    if not value.is_finite():
        raise _invalid(f"non_finite_numeric_value:{field}")
    return value


def _ratio(numerator: Decimal, denominator: Decimal | None) -> Decimal | None:
    if denominator is None or denominator == 0:
        return None
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        return _derived(numerator / denominator)


def _metric_change(
    metric_id: str, baseline: Decimal | None, current: Decimal | None
) -> tuple[MetricChange, tuple[AnalysisWarning, ...]]:
    if baseline is None or current is None:
        return (
            MetricChange(
                metric_id=metric_id,
                baseline_value=baseline,
                current_value=current,
                absolute_delta=None,
                change_rate=None,
            ),
            (),
        )
    delta = current - baseline
    if baseline == 0:
        return (
            MetricChange(
                metric_id=metric_id,
                baseline_value=baseline,
                current_value=current,
                absolute_delta=delta,
                change_rate=None,
            ),
            (AnalysisWarning.BASELINE_ZERO,),
        )
    return (
        MetricChange(
            metric_id=metric_id,
            baseline_value=baseline,
            current_value=current,
            absolute_delta=delta,
            change_rate=_derived(delta / abs(baseline)),
        ),
        (),
    )


def _derived(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        return value.quantize(DERIVED_QUANTUM)


def _invalid(reason: str) -> AnalysisError:
    return AnalysisError(AnalysisErrorCode.INVALID_ANALYSIS_INPUT, reason)
