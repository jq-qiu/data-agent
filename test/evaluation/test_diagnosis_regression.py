from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.diagnosis.evidence import AnomalyStatus
from app.diagnosis.question import CandidateFactor
from app.diagnosis.report import ReportStatus
from app.evaluation.diagnosis import (
    DiagnosisCaseObservation,
    DiagnosisErrorCategory,
    RatioScore,
    score_diagnosis,
)


def _observation(
    index: int,
    expected: tuple[CandidateFactor, ...],
    predicted: tuple[CandidateFactor, ...] | None = None,
    *,
    degradation: bool = False,
    no_decline: bool = False,
    numeric: bool = True,
    successful: bool = True,
    error: DiagnosisErrorCategory | None = None,
) -> DiagnosisCaseObservation:
    predicted = expected if predicted is None else predicted
    return DiagnosisCaseObservation(
        case_id=f"D{index:02d}",
        expected_factors=expected,
        predicted_factors=predicted,
        supported_evidence_factors=predicted,
        expected_degradation=degradation,
        expected_no_decline=no_decline,
        anomaly_status=(
            AnomalyStatus.DECLINE_NOT_CONFIRMED
            if no_decline
            else AnomalyStatus.DECLINE_CONFIRMED
        ),
        report_status=(
            ReportStatus.DEGRADED
            if degradation
            else ReportStatus.NO_DECLINE
            if no_decline
            else ReportStatus.COMPLETE
        ),
        missing_evidence=("analysis_sales_region_daily.visitors",)
        if degradation
        else (),
        numeric_consistent=numeric,
        max_reconciliation_error=Decimal(0),
        unsupported_claim_count=0,
        causal_language_violation_count=0,
        elapsed_ms=Decimal(index),
        query_count=4,
        successful=successful,
        primary_error=error,
        error_type=None if successful else "ControlledFailure",
    )


def _perfect() -> tuple[DiagnosisCaseObservation, ...]:
    expected = (
        (CandidateFactor.TRAFFIC,),
        (CandidateFactor.TRAFFIC,),
        (CandidateFactor.PROMOTION,),
        (CandidateFactor.PROMOTION,),
        (CandidateFactor.INVENTORY,),
        (CandidateFactor.INVENTORY,),
        (CandidateFactor.TRAFFIC, CandidateFactor.PROMOTION),
        (CandidateFactor.TRAFFIC, CandidateFactor.INVENTORY),
        (),
        (),
    )
    return tuple(
        _observation(
            index,
            factors,
            degradation=index == 10,
            no_decline=index == 9,
        )
        for index, factors in enumerate(expected, 1)
    )


def test_perfect_regression_passes_gate_with_frozen_denominators() -> None:
    summary = score_diagnosis(_perfect())

    assert summary.single_cause_hit_at_1 == RatioScore(
        numerator=6, denominator=6, value=Decimal("1.000000")
    )
    assert summary.root_cause_recall_at_3.denominator == 10
    assert summary.root_cause_recall_at_3.numerator == 10
    assert summary.evidence_precision.numerator == 10
    assert summary.evidence_recall.denominator == 10
    assert summary.numeric_consistency.numerator == 10
    assert summary.correct_degradation.numerator == 1
    assert summary.no_decline_correctness.numerator == 1
    assert summary.gate_5_passed is True


def test_root_recall_below_eight_of_ten_fails_gate() -> None:
    observations = list(_perfect())
    for index in range(4):
        item = observations[index]
        observations[index] = item.model_copy(
            update={
                "predicted_factors": (),
                "supported_evidence_factors": (),
            }
        )

    summary = score_diagnosis(tuple(observations))

    assert summary.root_cause_recall_at_3.numerator == 6
    assert summary.gate_5_passed is False


def test_numeric_inconsistency_fails_gate() -> None:
    observations = list(_perfect())
    observations[0] = observations[0].model_copy(update={"numeric_consistent": False})

    summary = score_diagnosis(tuple(observations))

    assert summary.numeric_consistency.numerator == 9
    assert summary.gate_5_passed is False


def test_failed_degradation_fails_gate() -> None:
    observations = list(_perfect())
    observations[9] = observations[9].model_copy(
        update={"report_status": ReportStatus.COMPLETE}
    )

    summary = score_diagnosis(tuple(observations))

    assert summary.correct_degradation.numerator == 0
    assert summary.gate_5_passed is False


def test_one_primary_error_is_counted() -> None:
    observations = list(_perfect())
    observations[0] = _observation(
        1,
        (CandidateFactor.TRAFFIC,),
        predicted=(),
        numeric=False,
        successful=False,
        error=DiagnosisErrorCategory.SQL_EXECUTION,
    )

    summary = score_diagnosis(tuple(observations))

    assert summary.successful_cases == 9
    assert summary.error_counts[DiagnosisErrorCategory.SQL_EXECUTION] == 1
    assert sum(summary.error_counts.values()) == 1
    assert summary.gate_5_passed is False


def test_ratio_zero_denominator_is_null() -> None:
    assert RatioScore(numerator=0, denominator=0, value=None).value is None


def test_ratio_rejects_inconsistent_value() -> None:
    with pytest.raises(ValueError, match="must match"):
        RatioScore(numerator=1, denominator=2, value=Decimal(1))


def test_requires_exact_ordered_d01_d10() -> None:
    with pytest.raises(ValueError, match="ordered D01-D10"):
        score_diagnosis(_perfect()[:-1])


def test_versioned_live_report_recomputes_to_recorded_summary() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads(
        (root / "data" / "reports" / "EVAL-001_diagnosis_regression.json").read_text(
            encoding="utf-8"
        )
    )
    summary_payload = json.loads(
        (root / "eval_runs" / "EVAL-001_v1" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    observations = tuple(
        DiagnosisCaseObservation.model_validate(item) for item in payload["cases"]
    )

    actual = score_diagnosis(
        observations,
        evaluation_version=payload["summary"]["evaluation_version"],
    )

    assert actual.model_dump(mode="json") == payload["summary"]
    assert "cases" not in summary_payload
    assert summary_payload["summary"] == payload["summary"]
