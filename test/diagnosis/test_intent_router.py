import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.diagnosis.intent import (
    Intent,
    IntentDecision,
    IntentRouter,
    intent_router_node,
    route_after_intent,
)
from app.scripts.evaluate_intent_router_v1 import evaluate

ROOT = Path(__file__).parents[2]


def test_intent_schema_rejects_unknown_and_low_confidence_non_degraded_values() -> None:
    with pytest.raises(ValidationError):
        IntentDecision(intent="OTHER", confidence=0.9, reason="unknown")
    with pytest.raises(ValidationError, match="low-confidence"):
        IntentDecision(intent=Intent.DIAGNOSIS, confidence=0.69, reason="ambiguous")
    with pytest.raises(ValidationError):
        IntentDecision(intent=Intent.QUERY, confidence=1.1, reason="explicit_data_query")


@pytest.mark.parametrize(
    "question",
    (
        "2018 年 5 月 GMV 是多少？",
        "2018年5月GMV相比4月变化了多少？",
        "2018年5月各品类GMV排名",
        "这个月GMV是多少",
    ),
)
def test_query_rewrites_route_consistently(question: str) -> None:
    decision = IntentRouter().route(question)

    assert decision.intent is Intent.QUERY
    assert decision.reason == "explicit_data_query"


@pytest.mark.parametrize(
    "question",
    (
        "为什么2018年5月GMV下降？",
        "分析2018年5月成交总额下降的原因",
        "2018年5月哪些品类和州对GMV下降贡献最大？",
        "2018年5月流量、促销和库存分别发生了什么变化？",
    ),
)
def test_diagnosis_rewrites_route_consistently(question: str) -> None:
    decision = IntentRouter().route(question)

    assert decision.intent is Intent.DIAGNOSIS
    assert decision.confidence >= 0.70


@pytest.mark.parametrize(
    "question,reason",
    (
        ("预测明年销量并自动调价", "future_or_external_action_unsupported"),
        ("证明促销结束导致了GMV下降", "strict_causal_request_unsupported"),
        ("那圣保罗州呢？", "multi_turn_anaphora_unsupported"),
        ("为什么2018年5月订单量下降？", "non_gmv_diagnosis_unsupported"),
        ("帮我看看这个情况", "ambiguous_or_incomplete_question"),
        ("", "empty_question"),
    ),
)
def test_unsupported_requests_degrade_without_diagnosis(question: str, reason: str) -> None:
    decision = IntentRouter().route(question)

    assert decision.intent is Intent.UNSUPPORTED
    assert decision.reason == reason


@pytest.mark.asyncio
async def test_router_node_emits_serializable_state_and_stable_branch() -> None:
    update = await intent_router_node({"query": "为什么2018年5月GMV下降"})

    assert json.loads(json.dumps(update)) == update
    assert route_after_intent(update) == "analysis_question_parser"
    assert route_after_intent(
        {"intent": "QUERY", "confidence": 0.94, "reason": "explicit_data_query"}
    ) == "existing_nl2sql"
    assert route_after_intent(
        {"intent": "UNSUPPORTED", "confidence": 0.45, "reason": "ambiguous_question"}
    ) == "unsupported"


def test_fixed_evaluation_has_no_mismatch_or_diagnosis_false_positive() -> None:
    result = evaluate(ROOT / "data" / "evaluation" / "intent_router_golden_v1.json")

    assert result["case_count"] == 18
    assert result["metrics"]["intent_accuracy"] == 1
    assert result["metrics"]["reason_accuracy"] == 1
    assert result["metrics"]["diagnosis_false_positive_count"] == 0
    assert result["metrics"]["low_confidence_diagnosis_count"] == 0
    assert result["metrics"]["correct_degradation_count"] == 6
    assert result["failure_count"] == 0
