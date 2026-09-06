from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.diagnosis.analyzer import (
    AnalysisMethod,
    AnalysisResult,
    CandidateFactorAnalysis,
    CandidateFactorValues,
    DimensionContributionValues,
    GmvShapleyValues,
    PeriodComparisonValues,
    ReconciliationStatus,
)
from app.diagnosis.planner import AnalysisPlan, AnalysisTask, TaskMethod
from app.diagnosis.query import MetricLineage
from app.diagnosis.question import (
    AnalysisDimension,
    AnalysisScope,
    CandidateFactor,
    DatePeriod,
)

AnalysisResultId = Annotated[str, Field(pattern=r"^A\d{3}$")]
QueryId = Annotated[str, Field(pattern=r"^Q\d{3}$")]


class EvidenceSupportLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNSUPPORTED = "unsupported"


class EvidenceType(StrEnum):
    ANOMALY_CONFIRMATION = "anomaly_confirmation"
    METRIC_DECOMPOSITION = "metric_decomposition"
    DIMENSION_CONTRIBUTION = "dimension_contribution"
    CANDIDATE_FACTOR = "candidate_factor"


class EvidenceClaim(StrEnum):
    GMV_DECLINE_CONFIRMED = "GMV_DECLINE_CONFIRMED"
    GMV_DECLINE_NOT_CONFIRMED = "GMV_DECLINE_NOT_CONFIRMED"
    GMV_CHANGE_UNAVAILABLE = "GMV_CHANGE_UNAVAILABLE"
    GMV_DECOMPOSITION_RECONCILED = "GMV_DECOMPOSITION_RECONCILED"
    GMV_DECOMPOSITION_INCOMPLETE = "GMV_DECOMPOSITION_INCOMPLETE"
    DIMENSION_CONTRIBUTION_RECONCILED = "DIMENSION_CONTRIBUTION_RECONCILED"
    DIMENSION_DELTA_ONLY = "DIMENSION_DELTA_ONLY"
    CANDIDATE_FACTOR_ASSOCIATED = "CANDIDATE_FACTOR_ASSOCIATED"
    CANDIDATE_FACTOR_LIMITED = "CANDIDATE_FACTOR_LIMITED"
    CANDIDATE_FACTOR_UNSUPPORTED = "CANDIDATE_FACTOR_UNSUPPORTED"


class EvidenceLimitation(StrEnum):
    BASELINE_RATE_UNAVAILABLE = "BASELINE_RATE_UNAVAILABLE"
    AOV_DENOMINATOR_ZERO = "AOV_DENOMINATOR_ZERO"
    DIMENSION_TOTAL_MISMATCH = "DIMENSION_TOTAL_MISMATCH"
    TOTAL_DELTA_NEAR_ZERO = "TOTAL_DELTA_NEAR_ZERO"
    PRIMARY_METRIC_MISSING = "PRIMARY_METRIC_MISSING"
    PRIMARY_METRIC_NOT_DECREASING = "PRIMARY_METRIC_NOT_DECREASING"
    ORDER_COUNT_NOT_DECREASING = "ORDER_COUNT_NOT_DECREASING"
    CONVERSION_RATE_MISSING = "CONVERSION_RATE_MISSING"
    CONVERSION_RATE_NOT_DECREASING = "CONVERSION_RATE_NOT_DECREASING"
    CONVERSION_RATE_OPPOSES = "CONVERSION_RATE_OPPOSES"
    SYNTHETIC_CANDIDATE_DATA = "SYNTHETIC_CANDIDATE_DATA"
    NO_CAUSAL_DESIGN = "NO_CAUSAL_DESIGN"
    DECLINE_NOT_CONFIRMED = "DECLINE_NOT_CONFIRMED"


class AnomalyStatus(StrEnum):
    DECLINE_CONFIRMED = "DECLINE_CONFIRMED"
    DECLINE_NOT_CONFIRMED = "DECLINE_NOT_CONFIRMED"
    UNAVAILABLE = "UNAVAILABLE"


_EVIDENCE_LIMITATION_LABELS = {
    EvidenceLimitation.BASELINE_RATE_UNAVAILABLE: "基线率不可用",
    EvidenceLimitation.AOV_DENOMINATOR_ZERO: "AOV 分母为零",
    EvidenceLimitation.DIMENSION_TOTAL_MISMATCH: "维度合计不匹配",
    EvidenceLimitation.TOTAL_DELTA_NEAR_ZERO: "总变化接近零",
    EvidenceLimitation.PRIMARY_METRIC_MISSING: "主指标缺失",
    EvidenceLimitation.PRIMARY_METRIC_NOT_DECREASING: "主指标未下降",
    EvidenceLimitation.ORDER_COUNT_NOT_DECREASING: "订单量未下降",
    EvidenceLimitation.CONVERSION_RATE_MISSING: "转化率缺失",
    EvidenceLimitation.CONVERSION_RATE_NOT_DECREASING: "转化率未下降",
    EvidenceLimitation.CONVERSION_RATE_OPPOSES: "转化率变化方向相反",
    EvidenceLimitation.SYNTHETIC_CANDIDATE_DATA: "合成候选因素数据",
    EvidenceLimitation.NO_CAUSAL_DESIGN: "无因果实验或准实验设计",
    EvidenceLimitation.DECLINE_NOT_CONFIRMED: "未确认下降",
}


def evidence_limitation_label(value: EvidenceLimitation | str) -> str:
    name = value.value if isinstance(value, EvidenceLimitation) else str(value)
    label = _EVIDENCE_LIMITATION_LABELS.get(
        EvidenceLimitation(name), name
    )
    return f"{label}（{name}）"


_OVERALL_DECOMPOSITION_LINEAGE = frozenset({"gmv", "order_count", "aov"})
_CATEGORY_DECOMPOSITION_LINEAGE = frozenset({"gmv", "category_order_count"})


class EvidenceValidationError(ValueError):
    code: Literal["EVIDENCE_VALIDATION_FAILED"] = "EVIDENCE_VALIDATION_FAILED"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"{self.code}: {reason}")


class EvidenceFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str = Field(pattern=r"^F\d{3}$")
    metric_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    available: bool = True
    baseline_value: Decimal | None = None
    current_value: Decimal | None = None
    absolute_delta: Decimal | None = None
    change_rate: Decimal | None = None
    contribution: Decimal | None = None
    dimension_value: str | None = None

    @model_validator(mode="after")
    def contains_numeric_fact(self) -> EvidenceFact:
        values = (
            self.baseline_value,
            self.current_value,
            self.absolute_delta,
            self.change_rate,
            self.contribution,
        )
        has_value = any(value is not None for value in values)
        if self.available != has_value:
            raise ValueError("Evidence availability must match its numeric values")
        if any(value is not None and not value.is_finite() for value in values):
            raise ValueError("Evidence numeric values must be finite")
        return self


class ValidatedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(pattern=r"^E\d{3}$")
    evidence_type: EvidenceType
    claim: EvidenceClaim
    support_level: EvidenceSupportLevel
    analysis_result_ids: tuple[AnalysisResultId, ...] = Field(min_length=1)
    query_ids: tuple[QueryId, ...] = Field(min_length=1)
    metric_versions: tuple[MetricLineage, ...] = Field(min_length=1)
    facts: tuple[EvidenceFact, ...] = Field(min_length=1)
    limitations: tuple[EvidenceLimitation, ...] = ()
    factor: CandidateFactor | None = None
    dimension: AnalysisDimension | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> ValidatedEvidence:
        is_candidate = self.evidence_type is EvidenceType.CANDIDATE_FACTOR
        is_dimension = self.evidence_type is EvidenceType.DIMENSION_CONTRIBUTION
        if is_candidate != (self.factor is not None):
            raise ValueError("candidate Evidence requires exactly one factor")
        if is_dimension != (self.dimension is not None):
            raise ValueError("dimension Evidence requires exactly one dimension")
        if len(self.analysis_result_ids) != len(set(self.analysis_result_ids)):
            raise ValueError("Evidence analysis lineage must be unique")
        if len(self.query_ids) != len(set(self.query_ids)):
            raise ValueError("Evidence query lineage must be unique")
        if len(self.limitations) != len(set(self.limitations)):
            raise ValueError("Evidence limitations must be unique")
        lineage_metric_ids = frozenset(
            item.metric_id for item in self.metric_versions
        )
        required_metric_ids = {
            EvidenceType.ANOMALY_CONFIRMATION: {"gmv"},
            EvidenceType.DIMENSION_CONTRIBUTION: {"gmv"},
            EvidenceType.CANDIDATE_FACTOR: {
                fact.metric_id for fact in self.facts
            },
        }.get(self.evidence_type)
        decomposition_lineage_valid = (
            self.evidence_type is EvidenceType.METRIC_DECOMPOSITION
            and lineage_metric_ids
            in {
                _OVERALL_DECOMPOSITION_LINEAGE,
                _CATEGORY_DECOMPOSITION_LINEAGE,
            }
        )
        if not decomposition_lineage_valid and (
            required_metric_ids is None
            or not required_metric_ids <= lineage_metric_ids
        ):
            raise ValueError("Evidence facts require matching Metric lineage")
        allowed_claims = {
            EvidenceType.ANOMALY_CONFIRMATION: {
                EvidenceClaim.GMV_DECLINE_CONFIRMED,
                EvidenceClaim.GMV_DECLINE_NOT_CONFIRMED,
                EvidenceClaim.GMV_CHANGE_UNAVAILABLE,
            },
            EvidenceType.METRIC_DECOMPOSITION: {
                EvidenceClaim.GMV_DECOMPOSITION_RECONCILED,
                EvidenceClaim.GMV_DECOMPOSITION_INCOMPLETE,
            },
            EvidenceType.DIMENSION_CONTRIBUTION: {
                EvidenceClaim.DIMENSION_CONTRIBUTION_RECONCILED,
                EvidenceClaim.DIMENSION_DELTA_ONLY,
            },
            EvidenceType.CANDIDATE_FACTOR: {
                EvidenceClaim.CANDIDATE_FACTOR_ASSOCIATED,
                EvidenceClaim.CANDIDATE_FACTOR_LIMITED,
                EvidenceClaim.CANDIDATE_FACTOR_UNSUPPORTED,
            },
        }
        if self.claim not in allowed_claims[self.evidence_type]:
            raise ValueError("Evidence claim does not match its type")
        if self.evidence_type is EvidenceType.CANDIDATE_FACTOR:
            expected_claim = {
                EvidenceSupportLevel.HIGH: EvidenceClaim.CANDIDATE_FACTOR_ASSOCIATED,
                EvidenceSupportLevel.MEDIUM: EvidenceClaim.CANDIDATE_FACTOR_LIMITED,
                EvidenceSupportLevel.LOW: EvidenceClaim.CANDIDATE_FACTOR_LIMITED,
                EvidenceSupportLevel.UNSUPPORTED: EvidenceClaim.CANDIDATE_FACTOR_UNSUPPORTED,
            }[self.support_level]
            if self.claim is not expected_claim:
                raise ValueError("candidate Evidence claim does not match support level")
        return self


class ValidatedEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_version: Literal["validated-evidence-v1"] = "validated-evidence-v1"
    target_metric: Literal["gmv"] = "gmv"
    current_period: DatePeriod
    baseline_period: DatePeriod
    scope: AnalysisScope
    anomaly_status: AnomalyStatus
    evidence: tuple[ValidatedEvidence, ...] = Field(min_length=1, max_length=7)
    missing_evidence: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_bundle(self) -> ValidatedEvidenceBundle:
        expected_ids = tuple(f"E{index:03d}" for index in range(1, len(self.evidence) + 1))
        if tuple(item.evidence_id for item in self.evidence) != expected_ids:
            raise ValueError("Evidence IDs must be consecutive and ordered")
        if self.evidence[0].evidence_type is not EvidenceType.ANOMALY_CONFIRMATION:
            raise ValueError("anomaly Evidence must be first")
        anomaly_claims = {
            AnomalyStatus.DECLINE_CONFIRMED: EvidenceClaim.GMV_DECLINE_CONFIRMED,
            AnomalyStatus.DECLINE_NOT_CONFIRMED: EvidenceClaim.GMV_DECLINE_NOT_CONFIRMED,
            AnomalyStatus.UNAVAILABLE: EvidenceClaim.GMV_CHANGE_UNAVAILABLE,
        }
        if self.evidence[0].claim is not anomaly_claims[self.anomaly_status]:
            raise ValueError("anomaly status and Evidence claim must match")
        identities = [
            (item.evidence_type, item.factor, item.dimension) for item in self.evidence
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("Evidence identities must be unique")
        fact_ids = [fact.fact_id for item in self.evidence for fact in item.facts]
        expected_fact_ids = [f"F{index:03d}" for index in range(1, len(fact_ids) + 1)]
        if fact_ids != expected_fact_ids:
            raise ValueError("Evidence fact IDs must be consecutive and ordered")
        versions: dict[str, str] = {}
        for item in self.evidence:
            for lineage in item.metric_versions:
                previous = versions.setdefault(lineage.metric_id, lineage.version)
                if previous != lineage.version:
                    raise ValueError("Evidence Metric versions must be consistent")
        if len(self.missing_evidence) != len(set(self.missing_evidence)):
            raise ValueError("missing Evidence identifiers must be unique")
        if self.anomaly_status is not AnomalyStatus.DECLINE_CONFIRMED and any(
            item.evidence_type is EvidenceType.CANDIDATE_FACTOR
            and item.support_level is not EvidenceSupportLevel.UNSUPPORTED
            for item in self.evidence
        ):
            raise ValueError("candidate Evidence requires a confirmed decline")
        return self


class EvidenceChecker:
    """Validates numeric Analysis Results without consulting Ground Truth or an LLM."""

    def check(
        self, plan: AnalysisPlan, analysis_results: Sequence[AnalysisResult]
    ) -> ValidatedEvidenceBundle:
        if not plan.tasks:
            raise EvidenceValidationError("executable_analysis_plan_required")
        self._validate_result_contract(plan, analysis_results)
        task = plan.tasks[0]
        evidence: list[ValidatedEvidence] = []
        fact_index = 1

        period_result = analysis_results[0]
        if not isinstance(period_result.values, PeriodComparisonValues):
            raise EvidenceValidationError("period_result_values_invalid")
        period_change = period_result.values.change
        if period_change.absolute_delta is None:
            anomaly_status = AnomalyStatus.UNAVAILABLE
            anomaly_claim = EvidenceClaim.GMV_CHANGE_UNAVAILABLE
            anomaly_support = EvidenceSupportLevel.UNSUPPORTED
        elif period_change.absolute_delta < 0:
            anomaly_status = AnomalyStatus.DECLINE_CONFIRMED
            anomaly_claim = EvidenceClaim.GMV_DECLINE_CONFIRMED
            anomaly_support = EvidenceSupportLevel.HIGH
        else:
            anomaly_status = AnomalyStatus.DECLINE_NOT_CONFIRMED
            anomaly_claim = EvidenceClaim.GMV_DECLINE_NOT_CONFIRMED
            anomaly_support = EvidenceSupportLevel.HIGH
        anomaly_limitations = (
            (EvidenceLimitation.BASELINE_RATE_UNAVAILABLE,)
            if period_change.change_rate is None
            else ()
        )
        anomaly_fact = _change_fact(fact_index, period_change)
        fact_index += 1
        evidence.append(
            _evidence(
                evidence,
                EvidenceType.ANOMALY_CONFIRMATION,
                anomaly_claim,
                anomaly_support,
                (period_result,),
                (anomaly_fact,),
                anomaly_limitations,
            )
        )

        result_index = 1
        for plan_task in plan.tasks[1:]:
            if plan_task.method is TaskMethod.METRIC_DECOMPOSITION:
                result = analysis_results[result_index]
                result_index += 1
                facts, limitations, support, claim = self._decomposition_evidence(
                    result, fact_index
                )
                fact_index += len(facts)
                evidence.append(
                    _evidence(
                        evidence,
                        EvidenceType.METRIC_DECOMPOSITION,
                        claim,
                        support,
                        (result,),
                        facts,
                        limitations,
                    )
                )
            elif plan_task.method is TaskMethod.DIMENSION_CONTRIBUTION:
                for dimension in plan_task.dimensions:
                    result = analysis_results[result_index]
                    result_index += 1
                    facts, limitations, support, claim = self._dimension_evidence(
                        result, dimension, fact_index
                    )
                    fact_index += len(facts)
                    evidence.append(
                        _evidence(
                            evidence,
                            EvidenceType.DIMENSION_CONTRIBUTION,
                            claim,
                            support,
                            (result,),
                            facts,
                            limitations,
                            dimension=dimension,
                        )
                    )
            else:
                result = analysis_results[result_index]
                result_index += 1
                if not isinstance(result.values, CandidateFactorValues):
                    raise EvidenceValidationError("candidate_result_values_invalid")
                if tuple(item.factor for item in result.values.factors) != plan_task.factors:
                    raise EvidenceValidationError("candidate_factors_do_not_match_plan")
                for factor_values in result.values.factors:
                    facts, limitations, support, claim = self._candidate_evidence(
                        factor_values,
                        anomaly_status,
                        fact_index,
                        order_metric_id=(
                            "category_order_count"
                            if plan_task.scope.category is not None
                            else "order_count"
                        ),
                    )
                    fact_index += len(facts)
                    evidence.append(
                        _evidence(
                            evidence,
                            EvidenceType.CANDIDATE_FACTOR,
                            claim,
                            support,
                            (result,),
                            facts,
                            limitations,
                            factor=factor_values.factor,
                        )
                    )

        try:
            return ValidatedEvidenceBundle(
                current_period=task.current_period,
                baseline_period=task.baseline_period,
                scope=task.scope,
                anomaly_status=anomaly_status,
                evidence=tuple(evidence),
                missing_evidence=plan.missing_evidence,
            )
        except ValidationError as error:
            raise EvidenceValidationError("validated_evidence_contract_invalid") from error

    @staticmethod
    def _validate_result_contract(
        plan: AnalysisPlan, analysis_results: Sequence[AnalysisResult]
    ) -> None:
        expected_results: list[tuple[AnalysisMethod, AnalysisTask]] = []
        for task in plan.tasks:
            if task.method is TaskMethod.PERIOD_COMPARISON:
                expected_results.append((AnalysisMethod.PERIOD_COMPARISON, task))
            elif task.method is TaskMethod.METRIC_DECOMPOSITION:
                expected_results.append((AnalysisMethod.GMV_SHAPLEY, task))
            elif task.method is TaskMethod.DIMENSION_CONTRIBUTION:
                expected_results.extend(
                    (AnalysisMethod.DIMENSION_CONTRIBUTION, task)
                    for _ in task.dimensions
                )
            else:
                expected_results.append((AnalysisMethod.CANDIDATE_FACTORS, task))
        if tuple(result.method for result in analysis_results) != tuple(
            method for method, _ in expected_results
        ):
            raise EvidenceValidationError("analysis_result_methods_do_not_match_plan")
        expected_ids = tuple(
            f"A{index:03d}" for index in range(1, len(analysis_results) + 1)
        )
        if tuple(result.analysis_result_id for result in analysis_results) != expected_ids:
            raise EvidenceValidationError("analysis_result_ids_not_consecutive")
        versions: dict[str, str] = {}
        for result, (_, task) in zip(
            analysis_results, expected_results, strict=True
        ):
            if not result.input_query_ids or not result.metric_versions:
                raise EvidenceValidationError("analysis_result_lineage_missing")
            if len(result.input_query_ids) != len(set(result.input_query_ids)):
                raise EvidenceValidationError("analysis_result_query_lineage_duplicate")
            lineage_keys = [
                (item.metric_id, item.version) for item in result.metric_versions
            ]
            if len(lineage_keys) != len(set(lineage_keys)):
                raise EvidenceValidationError("analysis_result_metric_lineage_duplicate")
            if result.method is AnalysisMethod.GMV_SHAPLEY:
                expected_lineage = (
                    _CATEGORY_DECOMPOSITION_LINEAGE
                    if task.scope.category is not None
                    else _OVERALL_DECOMPOSITION_LINEAGE
                )
                if {item.metric_id for item in result.metric_versions} != expected_lineage:
                    raise EvidenceValidationError(
                        "decomposition_metric_lineage_scope_mismatch"
                    )
            if result.method is AnalysisMethod.CANDIDATE_FACTORS:
                lineage_metric_ids = {
                    item.metric_id for item in result.metric_versions
                }
                expected_order_metric = (
                    "category_order_count"
                    if task.scope.category is not None
                    else "order_count"
                )
                forbidden_order_metric = (
                    "order_count"
                    if task.scope.category is not None
                    else "category_order_count"
                )
                if (
                    expected_order_metric not in lineage_metric_ids
                    or forbidden_order_metric in lineage_metric_ids
                ):
                    raise EvidenceValidationError(
                        "candidate_metric_lineage_scope_mismatch"
                    )
            for lineage in result.metric_versions:
                previous = versions.setdefault(lineage.metric_id, lineage.version)
                if previous != lineage.version:
                    raise EvidenceValidationError("analysis_result_metric_version_mismatch")

    @staticmethod
    def _decomposition_evidence(
        result: AnalysisResult, fact_index: int
    ) -> tuple[
        tuple[EvidenceFact, ...],
        tuple[EvidenceLimitation, ...],
        EvidenceSupportLevel,
        EvidenceClaim,
    ]:
        values = result.values
        if not isinstance(values, GmvShapleyValues):
            raise EvidenceValidationError("decomposition_result_values_invalid")
        facts = (
            EvidenceFact(
                fact_id=f"F{fact_index:03d}",
                metric_id="gmv",
                baseline_value=values.baseline_gmv,
                current_value=values.current_gmv,
                absolute_delta=values.total_delta,
            ),
            EvidenceFact(
                fact_id=f"F{fact_index + 1:03d}",
                metric_id="order_count_contribution",
                available=values.order_count_contribution is not None,
                absolute_delta=values.order_count_contribution,
            ),
            EvidenceFact(
                fact_id=f"F{fact_index + 2:03d}",
                metric_id="aov_contribution",
                available=values.aov_contribution is not None,
                absolute_delta=values.aov_contribution,
            ),
        )
        if (
            result.reconciliation is not None
            and result.reconciliation.status is ReconciliationStatus.PASS
            and values.order_count_contribution is not None
            and values.aov_contribution is not None
        ):
            return (
                facts,
                (),
                EvidenceSupportLevel.HIGH,
                EvidenceClaim.GMV_DECOMPOSITION_RECONCILED,
            )
        return (
            facts,
            (EvidenceLimitation.AOV_DENOMINATOR_ZERO,),
            EvidenceSupportLevel.LOW,
            EvidenceClaim.GMV_DECOMPOSITION_INCOMPLETE,
        )

    @staticmethod
    def _dimension_evidence(
        result: AnalysisResult,
        dimension: AnalysisDimension,
        fact_index: int,
    ) -> tuple[
        tuple[EvidenceFact, ...],
        tuple[EvidenceLimitation, ...],
        EvidenceSupportLevel,
        EvidenceClaim,
    ]:
        values = result.values
        if not isinstance(values, DimensionContributionValues):
            raise EvidenceValidationError("dimension_result_values_invalid")
        if values.dimension is not dimension:
            raise EvidenceValidationError("dimension_result_identity_mismatch")
        if not values.members:
            raise EvidenceValidationError("dimension_result_members_empty")
        facts = tuple(
            EvidenceFact(
                fact_id=f"F{fact_index + index:03d}",
                metric_id="gmv",
                baseline_value=member.baseline_value,
                current_value=member.current_value,
                absolute_delta=member.absolute_delta,
                contribution=member.contribution,
                dimension_value=member.dimension_value,
            )
            for index, member in enumerate(values.members)
        )
        complete = (
            result.reconciliation is not None
            and result.reconciliation.status is ReconciliationStatus.PASS
            and bool(facts)
            and all(fact.contribution is not None for fact in facts)
        )
        if complete:
            return (
                facts,
                (),
                EvidenceSupportLevel.HIGH,
                EvidenceClaim.DIMENSION_CONTRIBUTION_RECONCILED,
            )
        limitations: list[EvidenceLimitation] = []
        if result.reconciliation is None or result.reconciliation.status is ReconciliationStatus.DEGRADED:
            limitations.append(EvidenceLimitation.DIMENSION_TOTAL_MISMATCH)
        if any(warning.value == "TOTAL_DELTA_NEAR_ZERO" for warning in result.warnings):
            limitations.append(EvidenceLimitation.TOTAL_DELTA_NEAR_ZERO)
        return (
            facts,
            tuple(limitations),
            EvidenceSupportLevel.LOW,
            EvidenceClaim.DIMENSION_DELTA_ONLY,
        )

    @staticmethod
    def _candidate_evidence(
        values: CandidateFactorAnalysis,
        anomaly_status: AnomalyStatus,
        fact_index: int,
        *,
        order_metric_id: Literal["order_count", "category_order_count"],
    ) -> tuple[
        tuple[EvidenceFact, ...],
        tuple[EvidenceLimitation, ...],
        EvidenceSupportLevel,
        EvidenceClaim,
    ]:
        facts = (
            _change_fact(fact_index, values.primary_change),
            _change_fact(fact_index + 1, values.conversion_rate_change),
            _change_fact(
                fact_index + 2,
                values.order_count_change,
                metric_id=order_metric_id,
            ),
        )
        limitations = [
            EvidenceLimitation.SYNTHETIC_CANDIDATE_DATA,
            EvidenceLimitation.NO_CAUSAL_DESIGN,
        ]
        primary_delta = values.primary_change.absolute_delta
        order_delta = values.order_count_change.absolute_delta
        conversion_delta = values.conversion_rate_change.absolute_delta
        if anomaly_status is not AnomalyStatus.DECLINE_CONFIRMED:
            limitations.append(EvidenceLimitation.DECLINE_NOT_CONFIRMED)
            return (
                facts,
                tuple(limitations),
                EvidenceSupportLevel.UNSUPPORTED,
                EvidenceClaim.CANDIDATE_FACTOR_UNSUPPORTED,
            )
        if primary_delta is None:
            limitations.append(EvidenceLimitation.PRIMARY_METRIC_MISSING)
            return (
                facts,
                tuple(limitations),
                EvidenceSupportLevel.UNSUPPORTED,
                EvidenceClaim.CANDIDATE_FACTOR_UNSUPPORTED,
            )
        if primary_delta >= 0:
            limitations.append(EvidenceLimitation.PRIMARY_METRIC_NOT_DECREASING)
            return (
                facts,
                tuple(limitations),
                EvidenceSupportLevel.UNSUPPORTED,
                EvidenceClaim.CANDIDATE_FACTOR_UNSUPPORTED,
            )
        if order_delta is None or order_delta >= 0:
            limitations.append(EvidenceLimitation.ORDER_COUNT_NOT_DECREASING)
            return (
                facts,
                tuple(limitations),
                EvidenceSupportLevel.UNSUPPORTED,
                EvidenceClaim.CANDIDATE_FACTOR_UNSUPPORTED,
            )
        if conversion_delta is None:
            limitations.append(EvidenceLimitation.CONVERSION_RATE_MISSING)
            return (
                facts,
                tuple(limitations),
                EvidenceSupportLevel.MEDIUM,
                EvidenceClaim.CANDIDATE_FACTOR_LIMITED,
            )
        if values.factor is CandidateFactor.TRAFFIC:
            if conversion_delta > 0:
                limitations.append(EvidenceLimitation.CONVERSION_RATE_OPPOSES)
                return (
                    facts,
                    tuple(limitations),
                    EvidenceSupportLevel.MEDIUM,
                    EvidenceClaim.CANDIDATE_FACTOR_LIMITED,
                )
        elif conversion_delta >= 0:
            limitations.append(
                EvidenceLimitation.CONVERSION_RATE_OPPOSES
                if conversion_delta > 0
                else EvidenceLimitation.CONVERSION_RATE_NOT_DECREASING
            )
            return (
                facts,
                tuple(limitations),
                EvidenceSupportLevel.UNSUPPORTED,
                EvidenceClaim.CANDIDATE_FACTOR_UNSUPPORTED,
            )
        return (
            facts,
            tuple(limitations),
            EvidenceSupportLevel.HIGH,
            EvidenceClaim.CANDIDATE_FACTOR_ASSOCIATED,
        )


class EvidenceCheckerNode:
    def __init__(self, checker: EvidenceChecker | None = None) -> None:
        self._checker = checker or EvidenceChecker()

    def __call__(self, state: Mapping[str, Any]) -> dict[str, object]:
        try:
            plan = AnalysisPlan.model_validate(state.get("analysis_plan"))
            raw_results = state.get("analysis_results")
            if not isinstance(raw_results, (list, tuple)):
                raise EvidenceValidationError("analysis_results_not_a_sequence")
            results = tuple(AnalysisResult.model_validate(item) for item in raw_results)
        except ValidationError as error:
            raise EvidenceValidationError("evidence_checker_input_invalid") from error
        bundle = self._checker.check(plan, results)
        return {"validated_evidence": bundle.model_dump(mode="json")}


def _change_fact(
    index: int,
    change: Any,
    *,
    metric_id: str | None = None,
) -> EvidenceFact:
    numeric_values = (
        change.baseline_value,
        change.current_value,
        change.absolute_delta,
        change.change_rate,
    )
    return EvidenceFact(
        fact_id=f"F{index:03d}",
        metric_id=metric_id or change.metric_id,
        available=any(value is not None for value in numeric_values),
        baseline_value=change.baseline_value,
        current_value=change.current_value,
        absolute_delta=change.absolute_delta,
        change_rate=change.change_rate,
    )


def _evidence(
    existing: Sequence[ValidatedEvidence],
    evidence_type: EvidenceType,
    claim: EvidenceClaim,
    support_level: EvidenceSupportLevel,
    results: Sequence[AnalysisResult],
    facts: tuple[EvidenceFact, ...],
    limitations: tuple[EvidenceLimitation, ...],
    *,
    factor: CandidateFactor | None = None,
    dimension: AnalysisDimension | None = None,
) -> ValidatedEvidence:
    query_ids: list[str] = []
    lineage: list[MetricLineage] = []
    seen_queries: set[str] = set()
    seen_lineage: set[tuple[str, str]] = set()
    for result in results:
        for query_id in result.input_query_ids:
            if query_id not in seen_queries:
                seen_queries.add(query_id)
                query_ids.append(query_id)
        for item in result.metric_versions:
            key = (item.metric_id, item.version)
            if key not in seen_lineage:
                seen_lineage.add(key)
                lineage.append(item)
    return ValidatedEvidence(
        evidence_id=f"E{len(existing) + 1:03d}",
        evidence_type=evidence_type,
        claim=claim,
        support_level=support_level,
        analysis_result_ids=tuple(result.analysis_result_id for result in results),
        query_ids=tuple(query_ids),
        metric_versions=tuple(lineage),
        facts=facts,
        limitations=tuple(dict.fromkeys(limitations)),
        factor=factor,
        dimension=dimension,
    )
