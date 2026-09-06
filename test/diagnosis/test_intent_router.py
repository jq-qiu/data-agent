import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.diagnosis.intent import (
    Intent,
    IntentDecision,
    IntentRouter,
    IntentSignals,
    SemanticIntentDecision,
    intent_router_node,
    route_after_intent,
)
from app.scripts.evaluate_intent_router_v1 import evaluate
from app.scripts.evaluate_intent_router_v2 import evaluate as evaluate_v2

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
        "2018 年各州前三的销售额的商品",
        "列出2018年每个州销售额前3名的商品",
        "2018年各州销售额倒数三名商品",
        "Top 10 categories by GMV in 2018",
        "2018年销售额最高和最低的商品",
        "2018年订单量总和",
        "各州订单数分布",
        "商品评分中位数",
        "2018年销售额同比和环比",
        "各品类GMV占比",
        "销售额超过10万的卖家",
        "分别统计每个客户的订单数",
    ),
)
def test_expanded_data_query_language_routes_deterministically(question: str) -> None:
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


def test_v2_evaluation_has_no_mismatch_or_diagnosis_false_positive() -> None:
    result = evaluate_v2(
        ROOT / "data" / "evaluation" / "intent_router_golden_v2.json"
    )

    assert result["case_count"] == 48
    assert result["metrics"]["intent_accuracy"] == 1
    assert result["metrics"]["reason_accuracy"] == 1
    assert result["metrics"]["diagnosis_false_positive_count"] == 0
    assert result["metrics"]["classifier_eligible_count"] == 3
    assert result["failure_count"] == 0


class StubClassifier:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def classify(
        self,
        question: str,
        signals: IntentSignals,
    ) -> Any:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_explicit_query_and_strong_boundary_never_call_classifier() -> None:
    classifier = StubClassifier(
        SemanticIntentDecision(intent=Intent.QUERY, confidence=0.99)
    )
    router = IntentRouter(classifier=classifier)

    query = await router.aroute("2018 年各州前三的销售额的商品")
    boundary = await router.aroute("预测明年GMV并自动调价")

    assert query.intent is Intent.QUERY
    assert boundary.reason == "future_or_external_action_unsupported"
    assert classifier.calls == 0


@pytest.mark.asyncio
async def test_semantic_fallback_accepts_only_valid_domain_decisions() -> None:
    classifier = StubClassifier(
        SemanticIntentDecision(intent=Intent.QUERY, confidence=0.91)
    )
    router = IntentRouter(classifier=classifier)

    accepted = await router.aroute("销售额帮我盘点一下")
    rejected = await router.aroute("帮我盘点一下")

    assert accepted == IntentDecision(
        intent=Intent.QUERY,
        confidence=0.91,
        reason="semantic_data_query",
    )
    assert rejected.reason == "semantic_domain_mismatch"
    assert classifier.calls == 2


@pytest.mark.asyncio
async def test_semantic_fallback_rejects_non_gmv_diagnosis_and_low_confidence() -> None:
    diagnosis = StubClassifier(
        SemanticIntentDecision(intent=Intent.DIAGNOSIS, confidence=0.93)
    )
    low_confidence = StubClassifier(
        SemanticIntentDecision(intent=Intent.QUERY, confidence=0.79)
    )

    non_gmv = await IntentRouter(classifier=diagnosis).aroute("订单量帮我分析下")
    low = await IntentRouter(classifier=low_confidence).aroute("销售额帮我盘点下")

    assert non_gmv.reason == "non_gmv_diagnosis_unsupported"
    assert low.reason == "semantic_low_confidence"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "classifier",
    (
        StubClassifier(error=RuntimeError("private provider detail")),
        StubClassifier(result={"intent": "QUERY", "confidence": 2}),
    ),
)
async def test_semantic_failure_and_invalid_schema_fail_closed(
    classifier: StubClassifier,
) -> None:
    decision = await IntentRouter(classifier=classifier).aroute("销售额帮我盘点下")

    assert decision.intent is Intent.UNSUPPORTED
    assert decision.reason == "semantic_classifier_unavailable"


@pytest.mark.asyncio
async def test_semantic_fallback_has_hard_timeout() -> None:
    class SlowClassifier:
        async def classify(
            self,
            question: str,
            signals: IntentSignals,
        ) -> SemanticIntentDecision:
            await asyncio.sleep(0.05)
            return SemanticIntentDecision(intent=Intent.QUERY, confidence=0.99)

    decision = await IntentRouter(
        classifier=SlowClassifier(),
        semantic_timeout_seconds=0.001,
    ).aroute("销售额帮我盘点下")

    assert decision.reason == "semantic_classifier_unavailable"
