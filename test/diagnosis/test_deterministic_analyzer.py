from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.diagnosis.analyzer import (
    AnalysisError,
    AnalysisErrorCode,
    AnalysisMethod,
    AnalysisWarning,
    CandidateFactorValues,
    DeterministicAnalyzer,
    DeterministicAnalyzerNode,
    DimensionContributionValues,
    GmvShapleyValues,
    PeriodComparisonValues,
    ReconciliationStatus,
)
from app.diagnosis.planner import AnalysisPlan, AnalysisTask, TaskMethod
from app.diagnosis.query import (
    AnalysisQueryResult,
    MetricLineage,
    QueryValidationTrace,
)
from app.diagnosis.question import (
    AnalysisDimension,
    AnalysisScope,
    CandidateFactor,
    DatePeriod,
)


def _task(
    task_id: str,
    method: TaskMethod,
    *,
    dimensions: tuple[AnalysisDimension, ...] = (),
    factors: tuple[CandidateFactor, ...] = (),
) -> AnalysisTask:
    return AnalysisTask(
        task_id=task_id,
        method=method,
        metric="gmv",
        current_period=DatePeriod(start=date(2018, 5, 1), end=date(2018, 5, 31)),
        baseline_period=DatePeriod(start=date(2018, 4, 1), end=date(2018, 4, 30)),
        scope=AnalysisScope(),
        dimensions=dimensions,
        factors=factors,
        depends_on=() if task_id == "T1" else ("T1",),
    )


def _plan(*tasks: AnalysisTask) -> AnalysisPlan:
    return AnalysisPlan(tasks=tasks)


def _result(
    query_id: str,
    task: AnalysisTask,
    role: str,
    rows: list[dict[str, Any]],
    *,
    metric_versions: tuple[MetricLineage, ...] | None = None,
) -> AnalysisQueryResult:
    return AnalysisQueryResult(
        query_id=query_id,
        task_id=task.task_id,
        method=task.method,
        query_role=role,
        sql_fingerprint="a" * 64,
        catalog_version="metadata-v1",
        metric_versions=metric_versions
        or (MetricLineage(metric_id="gmv", version="v1"),),
        validation=QueryValidationTrace(
            tables=("dws_sales_region_daily",),
            columns=("dws_sales_region_daily.gmv",),
            join_relations=(),
            grain_warnings=(),
            policy_version="sql-policy-v1",
            max_rows=100,
            timeout_seconds=5,
        ),
        rows=tuple(rows),
    )


def _period_result(
    task: AnalysisTask, baseline: Any = "100", current: Any = "80"
) -> AnalysisQueryResult:
    return _result(
        "Q001",
        task,
        "period_comparison",
        [
            {"period_role": "baseline", "gmv": baseline},
            {"period_role": "current", "gmv": current},
        ],
    )


def test_period_comparison_calculates_delta_and_rate() -> None:
    task = _task("T1", TaskMethod.PERIOD_COMPARISON)

    actual = DeterministicAnalyzer().analyze(_plan(task), [_period_result(task)])

    assert len(actual) == 1
    assert actual[0].analysis_result_id == "A001"
    assert actual[0].method is AnalysisMethod.PERIOD_COMPARISON
    assert actual[0].input_query_ids == ("Q001",)
    assert isinstance(actual[0].values, PeriodComparisonValues)
    assert actual[0].values.change.absolute_delta == Decimal(-20)
    assert actual[0].values.change.change_rate == Decimal("-0.200000")
    assert actual[0].warnings == ()


def test_period_comparison_zero_baseline_returns_null_rate() -> None:
    task = _task("T1", TaskMethod.PERIOD_COMPARISON)

    actual = DeterministicAnalyzer().analyze(
        _plan(task), [_period_result(task, "0", "10")]
    )[0]

    assert isinstance(actual.values, PeriodComparisonValues)
    assert actual.values.change.absolute_delta == Decimal(10)
    assert actual.values.change.change_rate is None
    assert actual.warnings == (AnalysisWarning.BASELINE_ZERO,)


@pytest.mark.parametrize("unsafe", [1.5, True, "NaN", "1e3", -1])
def test_period_comparison_rejects_unsafe_or_negative_input(unsafe: Any) -> None:
    task = _task("T1", TaskMethod.PERIOD_COMPARISON)

    with pytest.raises(AnalysisError) as caught:
        DeterministicAnalyzer().analyze(
            _plan(task), [_period_result(task, unsafe, "10")]
        )

    assert caught.value.code is AnalysisErrorCode.INVALID_ANALYSIS_INPUT


def test_gmv_shapley_reconciles_exactly() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    decomposition = _task("T2", TaskMethod.METRIC_DECOMPOSITION)
    query = _result(
        "Q002",
        decomposition,
        "metric_decomposition",
        [
            {"period_role": "baseline", "gmv": "100", "order_count": 10},
            {"period_role": "current", "gmv": "144", "order_count": 12},
        ],
        metric_versions=(
            MetricLineage(metric_id="gmv", version="v1"),
            MetricLineage(metric_id="order_count", version="v1"),
            MetricLineage(metric_id="aov", version="v1"),
        ),
    )

    actual = DeterministicAnalyzer().analyze(
        _plan(period, decomposition),
        [_period_result(period, "100", "144"), query],
    )[1]

    assert isinstance(actual.values, GmvShapleyValues)
    assert actual.values.baseline_aov == Decimal("10.000000")
    assert actual.values.current_aov == Decimal("12.000000")
    assert actual.values.order_count_contribution == Decimal("22.000000")
    assert actual.values.aov_contribution == Decimal("22.000000")
    assert actual.reconciliation is not None
    assert actual.reconciliation.status is ReconciliationStatus.PASS
    assert actual.reconciliation.difference == Decimal("0.000000")


def test_gmv_shapley_degrades_for_zero_order_and_zero_gmv() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    decomposition = _task("T2", TaskMethod.METRIC_DECOMPOSITION)
    query = _result(
        "Q002",
        decomposition,
        "metric_decomposition",
        [
            {"period_role": "baseline", "gmv": "0", "order_count": 0},
            {"period_role": "current", "gmv": "100", "order_count": 10},
        ],
    )

    actual = DeterministicAnalyzer().analyze(
        _plan(period, decomposition),
        [_period_result(period, "0", "100"), query],
    )[1]

    assert isinstance(actual.values, GmvShapleyValues)
    assert actual.values.baseline_aov is None
    assert actual.values.order_count_contribution is None
    assert actual.reconciliation is None
    assert actual.warnings == (AnalysisWarning.AOV_DENOMINATOR_ZERO,)


def test_gmv_shapley_fails_for_nonzero_gmv_and_zero_orders() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    decomposition = _task("T2", TaskMethod.METRIC_DECOMPOSITION)
    query = _result(
        "Q002",
        decomposition,
        "metric_decomposition",
        [
            {"period_role": "baseline", "gmv": "10", "order_count": 0},
            {"period_role": "current", "gmv": "100", "order_count": 10},
        ],
    )

    with pytest.raises(AnalysisError) as caught:
        DeterministicAnalyzer().analyze(
            _plan(period, decomposition),
            [_period_result(period, "10", "100"), query],
        )

    assert caught.value.code is AnalysisErrorCode.NUMERIC_RECONCILIATION_FAILED


def test_dimension_contribution_allows_opposing_effects() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    dimension = _task(
        "T2",
        TaskMethod.DIMENSION_CONTRIBUTION,
        dimensions=(AnalysisDimension.REGION,),
    )
    query = _result(
        "Q002",
        dimension,
        "dimension_contribution:region",
        [
            {"period_role": "baseline", "dimension_value": "A", "gmv": "60"},
            {"period_role": "current", "dimension_value": "A", "gmv": "20"},
            {"period_role": "baseline", "dimension_value": "B", "gmv": "40"},
            {"period_role": "current", "dimension_value": "B", "gmv": "60"},
        ],
    )

    actual = DeterministicAnalyzer().analyze(
        _plan(period, dimension), [_period_result(period), query]
    )[1]

    assert isinstance(actual.values, DimensionContributionValues)
    assert actual.values.dimension is AnalysisDimension.REGION
    assert [member.contribution for member in actual.values.members] == [
        Decimal("2.000000"),
        Decimal("-1.000000"),
    ]
    assert actual.reconciliation is not None
    assert actual.reconciliation.status is ReconciliationStatus.PASS
    assert actual.input_query_ids == ("Q001", "Q002")


def test_dimension_contribution_handles_appearing_and_disappearing_members() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    dimension = _task(
        "T2",
        TaskMethod.DIMENSION_CONTRIBUTION,
        dimensions=(AnalysisDimension.CATEGORY,),
    )
    query = _result(
        "Q002",
        dimension,
        "dimension_contribution:category",
        [
            {"period_role": "baseline", "dimension_value": "old", "gmv": "100"},
            {"period_role": "current", "dimension_value": "new", "gmv": "80"},
        ],
    )

    actual = DeterministicAnalyzer().analyze(
        _plan(period, dimension), [_period_result(period), query]
    )[1]

    assert isinstance(actual.values, DimensionContributionValues)
    assert [(item.dimension_value, item.absolute_delta) for item in actual.values.members] == [
        ("new", Decimal(80)),
        ("old", Decimal(-100)),
    ]


def test_dimension_mismatch_degrades_and_hides_ratios() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    dimension = _task(
        "T2",
        TaskMethod.DIMENSION_CONTRIBUTION,
        dimensions=(AnalysisDimension.REGION,),
    )
    query = _result(
        "Q002",
        dimension,
        "dimension_contribution:region",
        [
            {"period_role": "baseline", "dimension_value": "A", "gmv": "50"},
            {"period_role": "current", "dimension_value": "A", "gmv": "40"},
        ],
    )

    actual = DeterministicAnalyzer().analyze(
        _plan(period, dimension), [_period_result(period), query]
    )[1]

    assert isinstance(actual.values, DimensionContributionValues)
    assert actual.values.members[0].contribution is None
    assert actual.reconciliation is not None
    assert actual.reconciliation.status is ReconciliationStatus.DEGRADED
    assert actual.warnings == (AnalysisWarning.DIMENSION_TOTAL_MISMATCH,)


def test_dimension_near_zero_total_hides_ratios() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    dimension = _task(
        "T2",
        TaskMethod.DIMENSION_CONTRIBUTION,
        dimensions=(AnalysisDimension.REGION,),
    )
    query = _result(
        "Q002",
        dimension,
        "dimension_contribution:region",
        [
            {"period_role": "baseline", "dimension_value": "A", "gmv": "10"},
            {"period_role": "current", "dimension_value": "A", "gmv": "5"},
            {"period_role": "baseline", "dimension_value": "B", "gmv": "10"},
            {"period_role": "current", "dimension_value": "B", "gmv": "15"},
        ],
    )

    actual = DeterministicAnalyzer().analyze(
        _plan(period, dimension), [_period_result(period, "20", "20"), query]
    )[1]

    assert isinstance(actual.values, DimensionContributionValues)
    assert all(item.contribution is None for item in actual.values.members)
    assert actual.warnings == (AnalysisWarning.TOTAL_DELTA_NEAR_ZERO,)


def test_candidate_factors_compute_post_aggregation_ratios() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    candidate = _task(
        "T2",
        TaskMethod.CANDIDATE_VALIDATION,
        factors=(
            CandidateFactor.TRAFFIC,
            CandidateFactor.PROMOTION,
            CandidateFactor.INVENTORY,
        ),
    )
    query = _result(
        "Q002",
        candidate,
        "candidate_validation",
        [
            {
                "period_role": "baseline",
                "order_count": 50,
                "visitors": 100,
                "promoted_sku_count": 2,
                "active_sku_count": 10,
                "available_sku_count": 8,
                "required_sku_count": 10,
            },
            {
                "period_role": "current",
                "order_count": 45,
                "visitors": 120,
                "promoted_sku_count": 3,
                "active_sku_count": 10,
                "available_sku_count": 9,
                "required_sku_count": 10,
            },
        ],
    )

    actual = DeterministicAnalyzer().analyze(
        _plan(period, candidate), [_period_result(period), query]
    )[1]

    assert isinstance(actual.values, CandidateFactorValues)
    assert [factor.factor for factor in actual.values.factors] == list(candidate.factors)
    assert actual.values.factors[0].primary_change.change_rate == Decimal("0.200000")
    assert actual.values.factors[0].conversion_rate_change.absolute_delta == Decimal(
        "-0.125000"
    )
    assert actual.values.factors[1].primary_change.absolute_delta == Decimal("0.100000")
    assert actual.values.factors[2].primary_change.absolute_delta == Decimal("0.100000")
    assert actual.warnings == ()


def test_candidate_only_returns_requested_factor() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    candidate = _task(
        "T2",
        TaskMethod.CANDIDATE_VALIDATION,
        factors=(CandidateFactor.PROMOTION,),
    )
    query = _result(
        "Q002",
        candidate,
        "candidate_validation",
        [
            {
                "period_role": "baseline",
                "order_count": 10,
                "visitors": 20,
                "promoted_sku_count": 1,
                "active_sku_count": 5,
            },
            {
                "period_role": "current",
                "order_count": 10,
                "visitors": 20,
                "promoted_sku_count": 2,
                "active_sku_count": 5,
            },
        ],
    )

    actual = DeterministicAnalyzer().analyze(
        _plan(period, candidate), [_period_result(period), query]
    )[1]

    assert isinstance(actual.values, CandidateFactorValues)
    assert len(actual.values.factors) == 1
    assert actual.values.factors[0].factor is CandidateFactor.PROMOTION


def test_candidate_missing_visitors_returns_null_conversion() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    candidate = _task(
        "T2",
        TaskMethod.CANDIDATE_VALIDATION,
        factors=(CandidateFactor.TRAFFIC,),
    )
    query = _result(
        "Q002",
        candidate,
        "candidate_validation",
        [
            {"period_role": "baseline", "order_count": 10, "visitors": None},
            {"period_role": "current", "order_count": 8, "visitors": 0},
        ],
    )

    actual = DeterministicAnalyzer().analyze(
        _plan(period, candidate), [_period_result(period), query]
    )[1]

    assert isinstance(actual.values, CandidateFactorValues)
    factor = actual.values.factors[0]
    assert factor.primary_change.absolute_delta is None
    assert factor.conversion_rate_change.absolute_delta is None
    assert AnalysisWarning.RATIO_DENOMINATOR_ZERO_OR_MISSING in actual.warnings


def test_missing_query_result_fails_closed() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    decomposition = _task("T2", TaskMethod.METRIC_DECOMPOSITION)

    with pytest.raises(AnalysisError) as caught:
        DeterministicAnalyzer().analyze(
            _plan(period, decomposition), [_period_result(period)]
        )

    assert caught.value.code is AnalysisErrorCode.MISSING_QUERY_RESULT


def test_duplicate_query_id_fails_closed() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)

    with pytest.raises(AnalysisError) as caught:
        DeterministicAnalyzer().analyze(
            _plan(period), [_period_result(period), _period_result(period)]
        )

    assert caught.value.code is AnalysisErrorCode.DUPLICATE_QUERY_RESULT


def test_metric_version_mismatch_fails_closed() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    decomposition = _task("T2", TaskMethod.METRIC_DECOMPOSITION)
    query = _result(
        "Q002",
        decomposition,
        "metric_decomposition",
        [
            {"period_role": "baseline", "gmv": 100, "order_count": 10},
            {"period_role": "current", "gmv": 80, "order_count": 10},
        ],
        metric_versions=(MetricLineage(metric_id="gmv", version="v2"),),
    )

    with pytest.raises(AnalysisError) as caught:
        DeterministicAnalyzer().analyze(
            _plan(period, decomposition), [_period_result(period), query]
        )

    assert caught.value.code is AnalysisErrorCode.METRIC_VERSION_MISMATCH


def test_node_emits_serializable_results_without_query_trace() -> None:
    task = _task("T1", TaskMethod.PERIOD_COMPARISON)
    query = _period_result(task)

    actual = DeterministicAnalyzerNode()(
        {
            "analysis_plan": _plan(task).model_dump(mode="json"),
            "query_results": [query.model_dump(mode="json")],
        }
    )

    assert list(actual) == ["analysis_results"]
    serialized = actual["analysis_results"]
    assert isinstance(serialized, list)
    assert serialized[0]["values"]["change"]["absolute_delta"] == "-20"
    assert "sql_fingerprint" not in str(serialized)
    assert "validation" not in str(serialized)


def test_stopped_plan_returns_no_results() -> None:
    plan = AnalysisPlan(tasks=(), stop_reason="INSUFFICIENT_DATA")

    assert DeterministicAnalyzer().analyze(plan, ()) == ()
