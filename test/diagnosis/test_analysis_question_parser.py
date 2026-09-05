import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.diagnosis.intent import Intent
from app.diagnosis.question import (
    AnalysisDimension,
    AnalysisParseError,
    AnalysisParseErrorCode,
    AnalysisQuestionParser,
    AnalysisQuestionParseResult,
    AnalysisQuestionParserNode,
    AnalysisScope,
    CandidateFactor,
    ComparisonType,
    DatePeriod,
    ParsedAnalysisQuestion,
)
from app.metadata.catalog import load_catalog
from app.scripts.evaluate_analysis_question_parser_v1 import evaluate

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def parser() -> AnalysisQuestionParser:
    return AnalysisQuestionParser.from_catalog(load_catalog(ROOT / "conf/meta_config.yaml"))


def test_schema_rejects_invalid_period_extra_fields_and_mixed_outcome() -> None:
    with pytest.raises(ValidationError, match="period end"):
        DatePeriod(start=date(2018, 5, 31), end=date(2018, 5, 1))
    with pytest.raises(ValidationError):
        AnalysisScope(region="SÃO")
    with pytest.raises(ValidationError):
        ParsedAnalysisQuestion(
            target_metric="gmv",
            current_period={"start": "2018-05-01", "end": "2018-05-31"},
            baseline_period={"start": "2018-04-01", "end": "2018-04-30"},
            comparison_type=ComparisonType.PREVIOUS_PERIOD,
            scope={},
            requested_dimensions=["region", "region"],
            requested_factors=[],
        )
    with pytest.raises(ValidationError, match="exactly one"):
        AnalysisQuestionParseResult()
    with pytest.raises(ValidationError, match="exactly one"):
        AnalysisQuestionParseResult(
            parsed_question={
                "target_metric": "gmv",
                "current_period": {"start": "2018-05-01", "end": "2018-05-31"},
                "baseline_period": {"start": "2018-04-01", "end": "2018-04-30"},
                "comparison_type": "previous_period",
                "scope": {},
            },
            error={
                "code": "UNKNOWN_METRIC",
                "field": "metric",
                "reason": "gmv_target_required",
            },
        )


def test_general_reason_defaults_to_previous_month_dimensions_and_factors(
    parser: AnalysisQuestionParser,
) -> None:
    result = parser.parse("为什么2018年5月GMV下降？", Intent.DIAGNOSIS)

    assert result.error is None
    assert result.parsed_question is not None
    parsed = result.parsed_question
    assert parsed.target_metric == "gmv"
    assert parsed.current_period == DatePeriod(
        start=date(2018, 5, 1), end=date(2018, 5, 31)
    )
    assert parsed.baseline_period == DatePeriod(
        start=date(2018, 4, 1), end=date(2018, 4, 30)
    )
    assert parsed.scope == AnalysisScope()
    assert parsed.requested_dimensions == (
        AnalysisDimension.REGION,
        AnalysisDimension.CATEGORY,
    )
    assert parsed.requested_factors == tuple(CandidateFactor)


def test_registered_metric_alias_and_iso_month_are_supported(
    parser: AnalysisQuestionParser,
) -> None:
    result = parser.parse("分析2018-05成交总额下降的原因", "DIAGNOSIS")

    assert result.error is None
    assert result.parsed_question is not None
    assert result.parsed_question.target_metric == "gmv"


def test_explicit_adjacent_baseline_and_partial_month_are_normalized(
    parser: AnalysisQuestionParser,
) -> None:
    result = parser.parse("拆解2018年5月相对4月的GMV变化", Intent.DIAGNOSIS)

    assert result.error is None
    assert result.parsed_question is not None
    assert result.parsed_question.baseline_period.start == date(2018, 4, 1)
    assert result.parsed_question.current_period.end == date(2018, 5, 31)
    assert result.parsed_question.requested_dimensions == ()
    assert result.parsed_question.requested_factors == ()


def test_cross_year_previous_month_uses_calendar_boundaries(
    parser: AnalysisQuestionParser,
) -> None:
    result = parser.parse("为什么2019-01 GMV下降", Intent.DIAGNOSIS)

    assert result.error is None
    assert result.parsed_question is not None
    assert result.parsed_question.baseline_period == DatePeriod(
        start=date(2018, 12, 1), end=date(2018, 12, 31)
    )


def test_registered_region_scope_removes_fixed_dimension(
    parser: AnalysisQuestionParser,
) -> None:
    result = parser.parse(
        "进一步分析2018年5月圣保罗州GMV下降的原因", Intent.DIAGNOSIS
    )

    assert result.error is None
    assert result.parsed_question is not None
    assert result.parsed_question.scope.region == "SP"
    assert result.parsed_question.requested_dimensions == (AnalysisDimension.CATEGORY,)


def test_registered_category_scope_is_canonicalized(
    parser: AnalysisQuestionParser,
) -> None:
    result = parser.parse(
        "为什么2018年5月电脑配件品类GMV下降", Intent.DIAGNOSIS
    )

    assert result.error is None
    assert result.parsed_question is not None
    assert result.parsed_question.scope.category == "informatica_acessorios"
    assert result.parsed_question.requested_dimensions == (AnalysisDimension.REGION,)


@pytest.mark.parametrize(
    ("question", "expected_scope"),
    (
        ("为什么2018年5月SC州GMV下降", AnalysisScope(region="SC")),
        ("为什么2018年5月PA州GMV下降", AnalysisScope(region="PA")),
        ("为什么2018年5月ES州GMV下降", AnalysisScope(region="ES")),
        (
            "为什么2018年5月SP州eletrodomesticos品类GMV下降",
            AnalysisScope(region="SP", category="eletrodomesticos"),
        ),
        (
            "为什么2018年5月SP州cool_stuff品类GMV下降",
            AnalysisScope(region="SP", category="cool_stuff"),
        ),
    ),
)
def test_gate_five_scope_values_are_canonicalized(
    parser: AnalysisQuestionParser,
    question: str,
    expected_scope: AnalysisScope,
) -> None:
    result = parser.parse(question, Intent.DIAGNOSIS)

    assert result.error is None
    assert result.parsed_question is not None
    assert result.parsed_question.scope == expected_scope


def test_dimension_contribution_only_requests_explicit_dimensions(
    parser: AnalysisQuestionParser,
) -> None:
    result = parser.parse(
        "2018年5月哪些品类和州对GMV下降贡献最大？", Intent.DIAGNOSIS
    )

    assert result.error is None
    assert result.parsed_question is not None
    assert result.parsed_question.requested_dimensions == (
        AnalysisDimension.REGION,
        AnalysisDimension.CATEGORY,
    )
    assert result.parsed_question.requested_factors == ()


def test_all_factor_request_safely_uses_v1_gmv_target(
    parser: AnalysisQuestionParser,
) -> None:
    result = parser.parse(
        "2018年5月流量、促销和库存分别发生了什么变化？", Intent.DIAGNOSIS
    )

    assert result.error is None
    assert result.parsed_question is not None
    assert result.parsed_question.target_metric == "gmv"
    assert result.parsed_question.requested_dimensions == ()
    assert result.parsed_question.requested_factors == tuple(CandidateFactor)


@pytest.mark.parametrize(
    "question,intent,code,field,reason",
    (
        (
            "为什么2018年5月GMV下降",
            "QUERY",
            AnalysisParseErrorCode.UNSUPPORTED_INTENT,
            "intent",
            "diagnosis_intent_required",
        ),
        (
            "为什么2018年5月订单量下降",
            "DIAGNOSIS",
            AnalysisParseErrorCode.UNKNOWN_METRIC,
            "metric",
            "gmv_target_required",
        ),
        (
            "为什么GMV下降",
            "DIAGNOSIS",
            AnalysisParseErrorCode.INVALID_TIME_RANGE,
            "time",
            "missing_current_period",
        ),
        (
            "为什么2018年13月GMV下降",
            "DIAGNOSIS",
            AnalysisParseErrorCode.INVALID_TIME_RANGE,
            "time",
            "invalid_calendar_month",
        ),
        (
            "为什么2018年5月相比基期GMV下降",
            "DIAGNOSIS",
            AnalysisParseErrorCode.MISSING_BASELINE,
            "baseline",
            "explicit_baseline_incomplete",
        ),
        (
            "对比2018年2月和2018年5月的GMV下降原因",
            "DIAGNOSIS",
            AnalysisParseErrorCode.INVALID_TIME_RANGE,
            "time",
            "non_adjacent_calendar_months",
        ),
        (
            "为什么2018年5月圣保罗州和里约热内卢州GMV下降",
            "DIAGNOSIS",
            AnalysisParseErrorCode.UNSUPPORTED_INTENT,
            "scope",
            "multiple_scope_values_unsupported",
        ),
        (
            "为什么2018年5月火星州GMV下降",
            "DIAGNOSIS",
            AnalysisParseErrorCode.UNSUPPORTED_INTENT,
            "scope",
            "unregistered_region_scope",
        ),
    ),
)
def test_error_paths_are_structured(
    parser: AnalysisQuestionParser,
    question: str,
    intent: str,
    code: AnalysisParseErrorCode,
    field: str,
    reason: str,
) -> None:
    result = parser.parse(question, intent)

    assert result.parsed_question is None
    assert result.error == AnalysisParseError(code=code, field=field, reason=reason)


@pytest.mark.asyncio
async def test_injected_node_emits_only_json_serializable_state(
    parser: AnalysisQuestionParser,
) -> None:
    update = await AnalysisQuestionParserNode(parser)(
        {"question": "为什么2018年5月SP的GMV下降", "intent": "DIAGNOSIS"}
    )

    assert json.loads(json.dumps(update)) == update
    assert update["parsed_question"]["scope"] == {"region": "SP", "category": None}
    assert update["error"] is None


def test_fixed_evaluation_matches_all_parsed_and_error_cases() -> None:
    result = evaluate()

    assert result["case_count"] == 18
    assert result["metrics"]["exact_match_count"] == 18
    assert result["metrics"]["successful_parse_match_count"] == 10
    assert result["metrics"]["structured_error_match_count"] == 8
    assert result["failure_count"] == 0
