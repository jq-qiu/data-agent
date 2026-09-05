from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum
from statistics import median

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.diagnosis.evidence import AnomalyStatus
from app.diagnosis.question import CandidateFactor
from app.diagnosis.report import ReportStatus


class DiagnosisErrorCategory(StrEnum):
    METADATA_RETRIEVAL = "Metadata Retrieval Error"
    METRIC_RECOGNITION = "Metric Recognition Error"
    SCHEMA_LINKING = "Schema Linking Error"
    SQL_GENERATION = "SQL Generation Error"
    SQL_EXECUTION = "SQL Execution Error"
    ANALYSIS_PLANNING = "Analysis Planning Error"
    QUERY_BUILDER = "Query Builder Error"
    NUMERIC_ANALYSIS = "Numeric Analysis Error"
    EVIDENCE_VALIDATION = "Evidence Validation Error"
    UNSUPPORTED_CLAIM = "Unsupported Claim"
    DEGRADATION = "Degradation Error"


class RatioScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    value: Decimal | None

    @model_validator(mode="after")
    def validate_ratio(self) -> RatioScore:
        if self.numerator > self.denominator:
            raise ValueError("ratio numerator cannot exceed denominator")
        expected = _ratio(self.numerator, self.denominator)
        if self.value != expected:
            raise ValueError("ratio value must match numerator and denominator")
        return self


class DiagnosisCaseObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^D(?:0[1-9]|10)$")
    expected_factors: tuple[CandidateFactor, ...]
    predicted_factors: tuple[CandidateFactor, ...]
    supported_evidence_factors: tuple[CandidateFactor, ...]
    expected_degradation: bool = False
    expected_no_decline: bool = False
    anomaly_status: AnomalyStatus | None = None
    report_status: ReportStatus | None = None
    missing_evidence: tuple[str, ...] = ()
    numeric_consistent: bool
    max_reconciliation_error: Decimal = Field(ge=0)
    unsupported_claim_count: int = Field(ge=0)
    causal_language_violation_count: int = Field(ge=0)
    elapsed_ms: Decimal = Field(ge=0)
    query_count: int = Field(ge=0, le=5)
    successful: bool
    primary_error: DiagnosisErrorCategory | None = None
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> DiagnosisCaseObservation:
        if self.successful == (self.primary_error is not None):
            raise ValueError("successful cases cannot have errors and failures require one")
        if self.successful and self.error_type is not None:
            raise ValueError("successful cases cannot expose an error type")
        if not self.successful and not self.error_type:
            raise ValueError("failed cases require an error type")
        return self


class LatencySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mean_ms: Decimal
    median_ms: Decimal
    max_ms: Decimal


class DiagnosisEvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluation_version: str
    case_count: int
    successful_cases: int
    single_cause_hit_at_1: RatioScore
    root_cause_recall_at_3: RatioScore
    evidence_precision: RatioScore
    evidence_recall: RatioScore
    numeric_consistency: RatioScore
    correct_degradation: RatioScore
    no_decline_correctness: RatioScore
    max_contribution_reconciliation_error: Decimal
    unsupported_claim_count: int
    causal_language_violation_count: int
    latency: LatencySummary
    token_usage: str
    cost: str
    error_counts: dict[DiagnosisErrorCategory, int]
    gate_5_passed: bool


def score_diagnosis(
    observations: tuple[DiagnosisCaseObservation, ...],
    *,
    evaluation_version: str = "diagnosis-regression-v1",
) -> DiagnosisEvaluationSummary:
    if tuple(item.case_id for item in observations) != tuple(
        f"D{index:02d}" for index in range(1, 11)
    ):
        raise ValueError("diagnosis evaluation requires ordered D01-D10")

    single = [item for item in observations if len(item.expected_factors) == 1]
    single_hits = sum(
        bool(item.predicted_factors)
        and item.predicted_factors[0] == item.expected_factors[0]
        for item in single
    )
    cause_denominator = sum(len(item.expected_factors) for item in observations)
    cause_hits = sum(
        len(set(item.expected_factors) & set(item.predicted_factors[:3]))
        for item in observations
    )
    supported_count = sum(len(item.supported_evidence_factors) for item in observations)
    supported_hits = sum(
        len(set(item.expected_factors) & set(item.supported_evidence_factors))
        for item in observations
    )
    numeric_hits = sum(item.numeric_consistent for item in observations)
    degradation = [item for item in observations if item.expected_degradation]
    degradation_hits = sum(
        item.successful
        and item.report_status is ReportStatus.DEGRADED
        and not item.predicted_factors
        and any("visitors" in value for value in item.missing_evidence)
        for item in degradation
    )
    no_decline = [item for item in observations if item.expected_no_decline]
    no_decline_hits = sum(
        item.successful
        and item.report_status is ReportStatus.NO_DECLINE
        and not item.predicted_factors
        for item in no_decline
    )
    unsupported = sum(item.unsupported_claim_count for item in observations)
    causal = sum(item.causal_language_violation_count for item in observations)
    latencies = [item.elapsed_ms for item in observations]
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        latency = LatencySummary(
            mean_ms=_decimal(sum(latencies, Decimal(0)) / len(latencies)),
            median_ms=_decimal(Decimal(median(latencies))),
            max_ms=_decimal(max(latencies)),
        )
    errors = {
        category: sum(item.primary_error is category for item in observations)
        for category in DiagnosisErrorCategory
    }
    root_score = RatioScore(
        numerator=cause_hits,
        denominator=cause_denominator,
        value=_ratio(cause_hits, cause_denominator),
    )
    numeric_score = RatioScore(
        numerator=numeric_hits,
        denominator=len(observations),
        value=_ratio(numeric_hits, len(observations)),
    )
    degradation_score = RatioScore(
        numerator=degradation_hits,
        denominator=len(degradation),
        value=_ratio(degradation_hits, len(degradation)),
    )
    gate = (
        len(observations) == 10
        and sum(item.successful for item in observations) == 10
        and numeric_score.numerator == numeric_score.denominator == 10
        and unsupported == 0
        and causal == 0
        and degradation_score.numerator == degradation_score.denominator == 1
        and root_score.numerator * 10 >= root_score.denominator * 8
    )
    return DiagnosisEvaluationSummary(
        evaluation_version=evaluation_version,
        case_count=len(observations),
        successful_cases=sum(item.successful for item in observations),
        single_cause_hit_at_1=RatioScore(
            numerator=single_hits,
            denominator=len(single),
            value=_ratio(single_hits, len(single)),
        ),
        root_cause_recall_at_3=root_score,
        evidence_precision=RatioScore(
            numerator=supported_hits,
            denominator=supported_count,
            value=_ratio(supported_hits, supported_count),
        ),
        evidence_recall=RatioScore(
            numerator=supported_hits,
            denominator=cause_denominator,
            value=_ratio(supported_hits, cause_denominator),
        ),
        numeric_consistency=numeric_score,
        correct_degradation=degradation_score,
        no_decline_correctness=RatioScore(
            numerator=no_decline_hits,
            denominator=len(no_decline),
            value=_ratio(no_decline_hits, len(no_decline)),
        ),
        max_contribution_reconciliation_error=max(
            item.max_reconciliation_error for item in observations
        ),
        unsupported_claim_count=unsupported,
        causal_language_violation_count=causal,
        latency=latency,
        token_usage="unavailable_no_llm_calls",
        cost="unavailable_no_llm_calls",
        error_counts=errors,
        gate_5_passed=gate,
    )


def _ratio(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return _decimal(Decimal(numerator) / Decimal(denominator))


def _decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
