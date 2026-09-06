from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.diagnosis.analyzer import (
    AnalysisResult,
    DeterministicAnalyzer,
)
from app.diagnosis.evidence import (
    AnomalyStatus,
    EvidenceChecker,
    EvidenceCheckerNode,
    EvidenceClaim,
    EvidenceLimitation,
    EvidenceSupportLevel,
    EvidenceType,
    EvidenceValidationError,
    ValidatedEvidenceBundle,
    evidence_limitation_label,
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
from app.diagnosis.report import (
    ReportGenerator,
    ReportGeneratorNode,
    ReportSectionId,
    ReportStatement,
    ReportStatementKind,
    ReportStatus,
)


def _task(
    task_id: str,
    method: TaskMethod,
    *,
    dimensions: tuple[AnalysisDimension, ...] = (),
    factors: tuple[CandidateFactor, ...] = (),
    scope: AnalysisScope | None = None,
) -> AnalysisTask:
    return AnalysisTask(
        task_id=task_id,
        method=method,
        metric="gmv",
        current_period=DatePeriod(start=date(2018, 5, 1), end=date(2018, 5, 31)),
        baseline_period=DatePeriod(start=date(2018, 4, 1), end=date(2018, 4, 30)),
        scope=scope or AnalysisScope(region="SP"),
        dimensions=dimensions,
        factors=factors,
        depends_on=() if task_id == "T1" else ("T1",),
    )


def _query(
    query_id: str,
    task: AnalysisTask,
    role: str,
    rows: list[dict[str, Any]],
    *,
    versions: tuple[MetricLineage, ...] | None = None,
) -> AnalysisQueryResult:
    return AnalysisQueryResult(
        query_id=query_id,
        task_id=task.task_id,
        method=task.method,
        query_role=role,
        sql_fingerprint="c" * 64,
        catalog_version="metadata-v1",
        metric_versions=versions
        or (MetricLineage(metric_id="gmv", version="v1"),),
        validation=QueryValidationTrace(
            tables=("fixture",),
            columns=("fixture.value",),
            join_relations=(),
            grain_warnings=(),
            policy_version="sql-policy-v1",
            max_rows=100,
            timeout_seconds=5,
        ),
        rows=tuple(rows),
    )


def _period_query(
    task: AnalysisTask, baseline: Any = "1000", current: Any = "800"
) -> AnalysisQueryResult:
    return _query(
        "Q001",
        task,
        "period_comparison",
        [
            {"period_role": "baseline", "gmv": baseline},
            {"period_role": "current", "gmv": current},
        ],
    )


def _candidate_contract(
    rows: list[dict[str, Any]],
    *,
    factors: tuple[CandidateFactor, ...] = (CandidateFactor.TRAFFIC,),
    baseline_gmv: Any = "1000",
    current_gmv: Any = "800",
    missing_evidence: tuple[str, ...] = (),
    scope: AnalysisScope | None = None,
) -> tuple[AnalysisPlan, tuple[AnalysisResult, ...]]:
    effective_scope = scope or AnalysisScope(region="SP")
    period = _task(
        "T1", TaskMethod.PERIOD_COMPARISON, scope=effective_scope
    )
    candidate = _task(
        "T2",
        TaskMethod.CANDIDATE_VALIDATION,
        factors=factors,
        scope=effective_scope,
    )
    plan = AnalysisPlan(
        tasks=(period, candidate), missing_evidence=missing_evidence
    )
    candidate_metrics = (
        MetricLineage(
            metric_id=(
                "category_order_count"
                if effective_scope.category is not None
                else "order_count"
            ),
            version="v1",
        ),
        MetricLineage(metric_id="visitors", version="v1"),
        MetricLineage(metric_id="conversion_rate", version="v1"),
        MetricLineage(metric_id="promotion_coverage", version="v1"),
        MetricLineage(metric_id="inventory_fill_rate", version="v1"),
    )
    queries = (
        _period_query(period, baseline_gmv, current_gmv),
        _query(
            "Q002",
            candidate,
            "candidate_validation",
            rows,
            versions=candidate_metrics,
        ),
    )
    return plan, DeterministicAnalyzer().analyze(plan, queries)


def _traffic_rows(
    *,
    baseline_orders: int = 100,
    current_orders: int = 80,
    baseline_visitors: int | None = 1000,
    current_visitors: int | None = 800,
) -> list[dict[str, Any]]:
    return [
        {
            "period_role": "baseline",
            "order_count": baseline_orders,
            "visitors": baseline_visitors,
        },
        {
            "period_role": "current",
            "order_count": current_orders,
            "visitors": current_visitors,
        },
    ]


def _candidate_evidence(bundle: ValidatedEvidenceBundle, factor: CandidateFactor):
    return next(item for item in bundle.evidence if item.factor is factor)


def test_supported_traffic_produces_complete_traceable_report() -> None:
    plan, results = _candidate_contract(_traffic_rows())

    bundle = EvidenceChecker().check(plan, results)
    report = ReportGenerator().generate(bundle)

    traffic = _candidate_evidence(bundle, CandidateFactor.TRAFFIC)
    assert bundle.anomaly_status is AnomalyStatus.DECLINE_CONFIRMED
    assert traffic.claim is EvidenceClaim.CANDIDATE_FACTOR_ASSOCIATED
    assert traffic.support_level is EvidenceSupportLevel.HIGH
    assert traffic.analysis_result_ids == ("A002",)
    assert traffic.query_ids == ("Q002",)
    assert report.status is ReportStatus.COMPLETE
    assert report.candidate_ranking == (traffic.evidence_id,)
    assert tuple(section.section_id for section in report.sections) == tuple(
        ReportSectionId
    )
    assert "delta=-200" in report.markdown
    assert "Evidence:" in report.markdown
    assert "Analysis:" in report.markdown
    assert "Query:" in report.markdown


def test_category_candidate_uses_category_order_evidence_lineage() -> None:
    plan, results = _candidate_contract(
        _traffic_rows(),
        scope=AnalysisScope(region="SP", category="informatica_acessorios"),
    )

    bundle = EvidenceChecker().check(plan, results)
    traffic = _candidate_evidence(bundle, CandidateFactor.TRAFFIC)
    report = ReportGenerator().generate(bundle)

    lineage_metric_ids = {item.metric_id for item in traffic.metric_versions}
    assert "category_order_count" in lineage_metric_ids
    assert "order_count" not in lineage_metric_ids
    assert {fact.metric_id for fact in traffic.facts} == {
        "category_order_count",
        "visitors",
        "conversion_rate",
    }
    assert report.status is ReportStatus.COMPLETE
    assert report.candidate_ranking == (traffic.evidence_id,)


def test_category_candidate_rejects_overall_order_lineage() -> None:
    plan, results = _candidate_contract(
        _traffic_rows(),
        scope=AnalysisScope(region="SP", category="informatica_acessorios"),
    )
    changed_lineage = tuple(
        MetricLineage(metric_id="order_count", version=item.version)
        if item.metric_id == "category_order_count"
        else item
        for item in results[1].metric_versions
    )
    changed = (
        results[0],
        results[1].model_copy(update={"metric_versions": changed_lineage}),
    )

    with pytest.raises(
        EvidenceValidationError,
        match="candidate_metric_lineage_scope_mismatch",
    ):
        EvidenceChecker().check(plan, changed)


def test_no_decline_blocks_candidate_conclusions() -> None:
    plan, results = _candidate_contract(
        _traffic_rows(current_orders=110, current_visitors=1100),
        baseline_gmv="1000",
        current_gmv="1100",
    )

    bundle = EvidenceChecker().check(plan, results)
    report = ReportGenerator().generate(bundle)

    traffic = _candidate_evidence(bundle, CandidateFactor.TRAFFIC)
    assert bundle.anomaly_status is AnomalyStatus.DECLINE_NOT_CONFIRMED
    assert traffic.support_level is EvidenceSupportLevel.UNSUPPORTED
    assert EvidenceLimitation.DECLINE_NOT_CONFIRMED in traffic.limitations
    assert report.status is ReportStatus.NO_DECLINE
    assert report.candidate_ranking == ()
    conclusions = [
        statement
        for section in report.sections
        for statement in section.statements
        if statement.kind is ReportStatementKind.CONCLUSION
    ]
    assert conclusions == []


def test_missing_traffic_primary_metric_degrades() -> None:
    plan, results = _candidate_contract(
        _traffic_rows(baseline_visitors=None, current_visitors=None),
        missing_evidence=("visitors",),
    )

    bundle = EvidenceChecker().check(plan, results)
    report = ReportGenerator().generate(bundle)

    traffic = _candidate_evidence(bundle, CandidateFactor.TRAFFIC)
    assert traffic.support_level is EvidenceSupportLevel.UNSUPPORTED
    assert EvidenceLimitation.PRIMARY_METRIC_MISSING in traffic.limitations
    assert traffic.facts[0].available is False
    assert report.status is ReportStatus.DEGRADED
    assert report.candidate_ranking == ()
    assert "visitors" in report.markdown


def test_traffic_with_conversion_increase_is_medium() -> None:
    plan, results = _candidate_contract(
        _traffic_rows(current_orders=90, current_visitors=600)
    )

    bundle = EvidenceChecker().check(plan, results)

    traffic = _candidate_evidence(bundle, CandidateFactor.TRAFFIC)
    assert traffic.support_level is EvidenceSupportLevel.MEDIUM
    assert traffic.claim is EvidenceClaim.CANDIDATE_FACTOR_LIMITED
    assert EvidenceLimitation.CONVERSION_RATE_OPPOSES in traffic.limitations


def test_promotion_requires_conversion_direction() -> None:
    factors = (CandidateFactor.PROMOTION,)
    aligned = [
        {
            "period_role": "baseline",
            "order_count": 100,
            "visitors": 1000,
            "promoted_sku_count": 50,
            "active_sku_count": 100,
        },
        {
            "period_role": "current",
            "order_count": 80,
            "visitors": 1000,
            "promoted_sku_count": 20,
            "active_sku_count": 100,
        },
    ]
    plan, results = _candidate_contract(aligned, factors=factors)

    supported = EvidenceChecker().check(plan, results)

    assert (
        _candidate_evidence(supported, CandidateFactor.PROMOTION).support_level
        is EvidenceSupportLevel.HIGH
    )

    conflicting = [
        aligned[0],
        {
            **aligned[1],
            "order_count": 90,
            "visitors": 600,
        },
    ]
    plan, results = _candidate_contract(conflicting, factors=factors)
    unsupported = EvidenceChecker().check(plan, results)
    promotion = _candidate_evidence(unsupported, CandidateFactor.PROMOTION)
    assert promotion.support_level is EvidenceSupportLevel.UNSUPPORTED
    assert EvidenceLimitation.CONVERSION_RATE_OPPOSES in promotion.limitations

    stable_conversion = [
        aligned[0],
        {
            **aligned[1],
            "visitors": 800,
        },
    ]
    plan, results = _candidate_contract(stable_conversion, factors=factors)
    unsupported = EvidenceChecker().check(plan, results)
    promotion = _candidate_evidence(unsupported, CandidateFactor.PROMOTION)
    assert promotion.support_level is EvidenceSupportLevel.UNSUPPORTED
    assert (
        EvidenceLimitation.CONVERSION_RATE_NOT_DECREASING in promotion.limitations
    )


def test_inventory_aligned_chain_is_high() -> None:
    rows = [
        {
            "period_role": "baseline",
            "order_count": 100,
            "visitors": 1000,
            "available_sku_count": 95,
            "required_sku_count": 100,
        },
        {
            "period_role": "current",
            "order_count": 80,
            "visitors": 1000,
            "available_sku_count": 60,
            "required_sku_count": 100,
        },
    ]
    plan, results = _candidate_contract(
        rows, factors=(CandidateFactor.INVENTORY,)
    )

    inventory = _candidate_evidence(
        EvidenceChecker().check(plan, results), CandidateFactor.INVENTORY
    )

    assert inventory.support_level is EvidenceSupportLevel.HIGH
    assert EvidenceLimitation.SYNTHETIC_CANDIDATE_DATA in inventory.limitations
    assert EvidenceLimitation.NO_CAUSAL_DESIGN in inventory.limitations


def test_candidate_ranking_uses_support_then_magnitude_then_factor_order() -> None:
    factors = tuple(CandidateFactor)
    rows = [
        {
            "period_role": "baseline",
            "order_count": 100,
            "visitors": 1000,
            "promoted_sku_count": 50,
            "active_sku_count": 100,
            "available_sku_count": 100,
            "required_sku_count": 100,
        },
        {
            "period_role": "current",
            "order_count": 70,
            "visitors": 800,
            "promoted_sku_count": 25,
            "active_sku_count": 100,
            "available_sku_count": 90,
            "required_sku_count": 100,
        },
    ]
    plan, results = _candidate_contract(rows, factors=factors)
    bundle = EvidenceChecker().check(plan, results)

    report = ReportGenerator().generate(bundle)

    ranked_factors = [
        next(item.factor for item in bundle.evidence if item.evidence_id == evidence_id)
        for evidence_id in report.candidate_ranking
    ]
    assert ranked_factors == [
        CandidateFactor.PROMOTION,
        CandidateFactor.TRAFFIC,
        CandidateFactor.INVENTORY,
    ]


def _dimension_contract(
    rows: list[dict[str, Any]],
    *,
    overall_baseline: str = "100",
    overall_current: str = "80",
) -> tuple[AnalysisPlan, tuple[AnalysisResult, ...]]:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    dimension = _task(
        "T2",
        TaskMethod.DIMENSION_CONTRIBUTION,
        dimensions=(AnalysisDimension.REGION,),
    )
    plan = AnalysisPlan(tasks=(period, dimension))
    queries = (
        _period_query(period, overall_baseline, overall_current),
        _query("Q002", dimension, "dimension_contribution:region", rows),
    )
    return plan, DeterministicAnalyzer().analyze(plan, queries)


def test_reconciled_dimension_becomes_high_evidence() -> None:
    rows = [
        {"period_role": "baseline", "dimension_value": "A", "gmv": 60},
        {"period_role": "current", "dimension_value": "A", "gmv": 20},
        {"period_role": "baseline", "dimension_value": "B", "gmv": 40},
        {"period_role": "current", "dimension_value": "B", "gmv": 60},
    ]
    plan, results = _dimension_contract(rows)

    bundle = EvidenceChecker().check(plan, results)
    dimension = bundle.evidence[1]
    report = ReportGenerator().generate(bundle)

    assert dimension.evidence_type is EvidenceType.DIMENSION_CONTRIBUTION
    assert dimension.support_level is EvidenceSupportLevel.HIGH
    assert [fact.contribution for fact in dimension.facts] == [
        Decimal("2.000000"),
        Decimal("-1.000000"),
    ]
    assert "contribution=2.000000" in report.markdown


def test_incomplete_dimension_only_reports_deltas() -> None:
    rows = [
        {"period_role": "baseline", "dimension_value": "A", "gmv": 50},
        {"period_role": "current", "dimension_value": "A", "gmv": 40},
    ]
    plan, results = _dimension_contract(rows)

    bundle = EvidenceChecker().check(plan, results)
    dimension = bundle.evidence[1]
    report = ReportGenerator().generate(bundle)

    assert dimension.support_level is EvidenceSupportLevel.LOW
    assert dimension.claim is EvidenceClaim.DIMENSION_DELTA_ONLY
    assert EvidenceLimitation.DIMENSION_TOTAL_MISMATCH in dimension.limitations
    assert dimension.facts[0].contribution is None
    assert "完整贡献率不可用" in report.markdown


def _decomposition_contract(
    baseline_gmv: int,
    current_gmv: int,
    baseline_orders: int,
    current_orders: int,
    *,
    scope: AnalysisScope | None = None,
    versions: tuple[MetricLineage, ...] | None = None,
) -> tuple[AnalysisPlan, tuple[AnalysisResult, ...]]:
    effective_scope = scope or AnalysisScope(region="SP")
    period = _task(
        "T1", TaskMethod.PERIOD_COMPARISON, scope=effective_scope
    )
    decomposition = _task(
        "T2", TaskMethod.METRIC_DECOMPOSITION, scope=effective_scope
    )
    plan = AnalysisPlan(tasks=(period, decomposition))
    queries = (
        _period_query(period, baseline_gmv, current_gmv),
        _query(
            "Q002",
            decomposition,
            "metric_decomposition",
            [
                {
                    "period_role": "baseline",
                    "gmv": baseline_gmv,
                    "order_count": baseline_orders,
                },
                {
                    "period_role": "current",
                    "gmv": current_gmv,
                    "order_count": current_orders,
                },
            ],
            versions=versions
            or (
                MetricLineage(metric_id="gmv", version="v1"),
                MetricLineage(metric_id="order_count", version="v1"),
                MetricLineage(metric_id="aov", version="v1"),
            ),
        ),
    )
    return plan, DeterministicAnalyzer().analyze(plan, queries)


def test_reconciled_shapley_becomes_high_evidence() -> None:
    plan, results = _decomposition_contract(100, 80, 10, 8)

    bundle = EvidenceChecker().check(plan, results)
    decomposition = bundle.evidence[1]

    assert decomposition.support_level is EvidenceSupportLevel.HIGH
    assert decomposition.claim is EvidenceClaim.GMV_DECOMPOSITION_RECONCILED
    assert decomposition.facts[1].absolute_delta == Decimal("-20.000000")
    assert decomposition.facts[2].absolute_delta == Decimal("0.000000")


def test_category_shapley_accepts_category_order_lineage() -> None:
    category_lineage = (
        MetricLineage(metric_id="gmv", version="v1"),
        MetricLineage(metric_id="category_order_count", version="v1"),
    )
    plan, results = _decomposition_contract(
        100,
        80,
        10,
        8,
        scope=AnalysisScope(region="SP", category="informatica_acessorios"),
        versions=category_lineage,
    )

    bundle = EvidenceChecker().check(plan, results)

    assert bundle.evidence[1].metric_versions == category_lineage
    assert bundle.evidence[1].support_level is EvidenceSupportLevel.HIGH


@pytest.mark.parametrize(
    ("scope", "versions"),
    (
        (
            AnalysisScope(region="SP"),
            (
                MetricLineage(metric_id="gmv", version="v1"),
                MetricLineage(metric_id="category_order_count", version="v1"),
            ),
        ),
        (
            AnalysisScope(region="SP", category="informatica_acessorios"),
            (
                MetricLineage(metric_id="gmv", version="v1"),
                MetricLineage(metric_id="order_count", version="v1"),
                MetricLineage(metric_id="aov", version="v1"),
            ),
        ),
    ),
)
def test_shapley_rejects_cross_grain_lineage(
    scope: AnalysisScope,
    versions: tuple[MetricLineage, ...],
) -> None:
    plan, results = _decomposition_contract(
        100,
        80,
        10,
        8,
        scope=scope,
        versions=versions,
    )

    with pytest.raises(
        EvidenceValidationError,
        match="decomposition_metric_lineage_scope_mismatch",
    ):
        EvidenceChecker().check(plan, results)


def test_zero_order_shapley_becomes_low_evidence() -> None:
    plan, results = _decomposition_contract(0, 100, 0, 10)

    bundle = EvidenceChecker().check(plan, results)
    decomposition = bundle.evidence[1]
    report = ReportGenerator().generate(bundle)

    assert decomposition.support_level is EvidenceSupportLevel.LOW
    assert decomposition.facts[1].available is False
    assert EvidenceLimitation.AOV_DENOMINATOR_ZERO in decomposition.limitations
    assert "不可完整计算" in report.markdown


def test_full_plan_produces_bounded_seven_item_evidence_bundle() -> None:
    period = _task("T1", TaskMethod.PERIOD_COMPARISON)
    decomposition = _task("T2", TaskMethod.METRIC_DECOMPOSITION)
    dimensions = _task(
        "T3",
        TaskMethod.DIMENSION_CONTRIBUTION,
        dimensions=(AnalysisDimension.REGION, AnalysisDimension.CATEGORY),
    )
    candidates = _task(
        "T4",
        TaskMethod.CANDIDATE_VALIDATION,
        factors=tuple(CandidateFactor),
    )
    plan = AnalysisPlan(tasks=(period, decomposition, dimensions, candidates))
    decomposition_versions = (
        MetricLineage(metric_id="gmv", version="v1"),
        MetricLineage(metric_id="order_count", version="v1"),
        MetricLineage(metric_id="aov", version="v1"),
    )
    candidate_versions = (
        MetricLineage(metric_id="order_count", version="v1"),
        MetricLineage(metric_id="visitors", version="v1"),
        MetricLineage(metric_id="conversion_rate", version="v1"),
        MetricLineage(metric_id="promotion_coverage", version="v1"),
        MetricLineage(metric_id="inventory_fill_rate", version="v1"),
    )
    results = DeterministicAnalyzer().analyze(
        plan,
        (
            _period_query(period, 1000, 700),
            _query(
                "Q002",
                decomposition,
                "metric_decomposition",
                [
                    {"period_role": "baseline", "gmv": 1000, "order_count": 100},
                    {"period_role": "current", "gmv": 700, "order_count": 70},
                ],
                versions=decomposition_versions,
            ),
            _query(
                "Q003",
                dimensions,
                "dimension_contribution:region",
                [
                    {"period_role": "baseline", "dimension_value": "A", "gmv": 600},
                    {"period_role": "current", "dimension_value": "A", "gmv": 300},
                    {"period_role": "baseline", "dimension_value": "B", "gmv": 400},
                    {"period_role": "current", "dimension_value": "B", "gmv": 400},
                ],
            ),
            _query(
                "Q004",
                dimensions,
                "dimension_contribution:category",
                [
                    {"period_role": "baseline", "dimension_value": "C", "gmv": 1000},
                    {"period_role": "current", "dimension_value": "C", "gmv": 700},
                ],
            ),
            _query(
                "Q005",
                candidates,
                "candidate_validation",
                [
                    {
                        "period_role": "baseline",
                        "order_count": 100,
                        "visitors": 1000,
                        "promoted_sku_count": 50,
                        "active_sku_count": 100,
                        "available_sku_count": 95,
                        "required_sku_count": 100,
                    },
                    {
                        "period_role": "current",
                        "order_count": 70,
                        "visitors": 800,
                        "promoted_sku_count": 20,
                        "active_sku_count": 100,
                        "available_sku_count": 60,
                        "required_sku_count": 100,
                    },
                ],
                versions=candidate_versions,
            ),
        ),
    )

    bundle = EvidenceChecker().check(plan, results)
    report = ReportGenerator().generate(bundle)

    assert len(bundle.evidence) == 7
    assert [item.evidence_id for item in bundle.evidence] == [
        "E001",
        "E002",
        "E003",
        "E004",
        "E005",
        "E006",
        "E007",
    ]
    assert report.status is ReportStatus.COMPLETE
    assert len(report.candidate_ranking) == 3


def test_checker_rejects_result_method_mismatch() -> None:
    plan, results = _candidate_contract(_traffic_rows())

    with pytest.raises(EvidenceValidationError) as caught:
        EvidenceChecker().check(plan, results[:1])

    assert caught.value.code == "EVIDENCE_VALIDATION_FAILED"


def test_checker_rejects_nonconsecutive_analysis_ids() -> None:
    plan, results = _candidate_contract(_traffic_rows())
    changed = (results[0], results[1].model_copy(update={"analysis_result_id": "A003"}))

    with pytest.raises(EvidenceValidationError, match="analysis_result_ids_not_consecutive"):
        EvidenceChecker().check(plan, changed)


def test_checker_rejects_metric_version_conflict() -> None:
    plan, results = _candidate_contract(_traffic_rows())
    conflicting_lineage = results[1].metric_versions + (
        MetricLineage(metric_id="gmv", version="v2"),
    )
    changed = (
        results[0],
        results[1].model_copy(update={"metric_versions": conflicting_lineage}),
    )

    with pytest.raises(EvidenceValidationError, match="metric_version_mismatch"):
        EvidenceChecker().check(plan, changed)


def test_report_statement_rejects_forbidden_causal_language() -> None:
    with pytest.raises(ValidationError, match="forbidden causal language"):
        ReportStatement(
            kind=ReportStatementKind.CONCLUSION,
            text="流量下降导致 GMV 下降。",
            evidence_ids=("E001",),
            analysis_result_ids=("A001",),
            query_ids=("Q001",),
        )


def test_report_validation_rejects_unsupported_candidate_ranking() -> None:
    plan, results = _candidate_contract(
        _traffic_rows(baseline_visitors=None, current_visitors=None)
    )
    bundle = EvidenceChecker().check(plan, results)
    report = ReportGenerator().generate(bundle)
    unsupported = _candidate_evidence(bundle, CandidateFactor.TRAFFIC)
    changed = report.model_copy(update={"candidate_ranking": (unsupported.evidence_id,)})

    with pytest.raises(EvidenceValidationError, match="candidate_ranking_invalid"):
        ReportGenerator.validate(changed, bundle)


def test_report_validation_rejects_unknown_evidence_reference() -> None:
    plan, results = _candidate_contract(_traffic_rows())
    bundle = EvidenceChecker().check(plan, results)
    report = ReportGenerator().generate(bundle)
    statement = report.sections[0].statements[0].model_copy(
        update={"evidence_ids": ("E999",)}
    )
    section = report.sections[0].model_copy(update={"statements": (statement,)})
    changed = report.model_copy(update={"sections": (section, *report.sections[1:])})

    with pytest.raises(EvidenceValidationError, match="unknown_evidence"):
        ReportGenerator.validate(changed, bundle)


def test_evidence_checker_node_emits_only_validated_evidence() -> None:
    plan, results = _candidate_contract(_traffic_rows())

    output = EvidenceCheckerNode()(
        {
            "analysis_plan": plan.model_dump(mode="json"),
            "analysis_results": [result.model_dump(mode="json") for result in results],
        }
    )

    assert list(output) == ["validated_evidence"]
    serialized = str(output)
    assert "sql_fingerprint" not in serialized
    assert "validation" not in serialized
    assert "ground_truth" not in serialized


def test_report_generator_node_consumes_validated_bundle() -> None:
    plan, results = _candidate_contract(_traffic_rows())
    bundle = EvidenceChecker().check(plan, results)

    output = ReportGeneratorNode()(
        {
            "validated_evidence": bundle.model_dump(mode="json"),
            "query_results": "must not be read",
            "analysis_results": "must not be read",
        }
    )

    assert list(output) == ["final_report", "final_answer"]
    assert isinstance(output["final_report"], dict)
    assert isinstance(output["final_answer"], str)


@pytest.mark.parametrize(
    "forbidden",
    ["导致", "造成", "证明", "唯一原因", "一定能够", "必然提升"],
)
def test_generated_report_contains_no_forbidden_claim(forbidden: str) -> None:
    plan, results = _candidate_contract(_traffic_rows())
    report = ReportGenerator().generate(EvidenceChecker().check(plan, results))

    assert forbidden not in report.markdown


def test_evidence_limitation_labels_include_chinese_and_code() -> None:
    label = evidence_limitation_label(EvidenceLimitation.SYNTHETIC_CANDIDATE_DATA)

    assert label == "合成候选因素数据（SYNTHETIC_CANDIDATE_DATA）"
    assert "NO_CAUSAL_DESIGN" in evidence_limitation_label(
        EvidenceLimitation.NO_CAUSAL_DESIGN
    )


def test_report_states_most_likely_associated_candidate() -> None:
    plan, results = _candidate_contract(_traffic_rows())
    report = ReportGenerator().generate(EvidenceChecker().check(plan, results))

    assert "本次 GMV 下降更可能主要与流量变化相关" in report.markdown
    assert "导致" not in report.markdown
