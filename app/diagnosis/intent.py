from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Intent(StrEnum):
    QUERY = "QUERY"
    DIAGNOSIS = "DIAGNOSIS"
    UNSUPPORTED = "UNSUPPORTED"


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: Intent
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def low_confidence_must_degrade(self) -> IntentDecision:
        if self.confidence < 0.70 and self.intent is not Intent.UNSUPPORTED:
            raise ValueError("low-confidence intent must degrade to UNSUPPORTED")
        return self


def _compact(question: str) -> str:
    normalized = unicodedata.normalize("NFKC", question).casefold()
    return re.sub(r"[^0-9a-z_\u4e00-\u9fff]+", "", normalized)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


class IntentRouter:
    """High-precision V1 router with explicit unsupported degradation."""

    _metric_terms = (
        "gmv",
        "成交总额",
        "商品交易总额",
        "销售额",
        "订单",
        "客单价",
        "aov",
        "评分",
        "商品",
        "品类",
        "付款",
        "支付",
        "配送",
        "访客",
        "流量",
        "促销",
        "库存",
    )
    _gmv_terms = ("gmv", "成交总额", "商品交易总额", "销售额")
    _diagnosis_terms = (
        "为什么",
        "原因",
        "根因",
        "驱动",
        "归因",
        "异动",
        "拆解",
        "贡献最大",
        "贡献度",
        "贡献了",
    )
    _factor_terms = ("流量", "访客", "traffic", "促销", "promotion", "库存", "inventory")
    _factor_analysis_terms = ("发生了什么", "什么变化", "分别变化", "验证", "影响")
    _query_terms = (
        "多少",
        "列出",
        "统计",
        "排名",
        "最高",
        "最低",
        "趋势",
        "有哪些",
        "是什么",
        "对比",
        "相比",
        "变化了多少",
        "平均",
        "总数",
        "一共有",
    )
    _strict_causal_terms = ("严格因果", "因果关系", "唯一原因", "证明", "证实")
    _future_action_terms = (
        "预测",
        "明年",
        "自动调价",
        "自动补货",
        "自动投放",
        "执行营销",
        "替我下单",
    )
    _anaphora_patterns = (
        re.compile(r"^(那|那么|上一个).*(呢|怎么样|如何)?$"),
        re.compile(r"^这个(呢|怎么样|如何|情况)$"),
        re.compile(r"^继续(分析|看|查)?$"),
    )

    def route(self, question: str) -> IntentDecision:
        text = _compact(question)
        if not text:
            return IntentDecision(
                intent=Intent.UNSUPPORTED,
                confidence=0.0,
                reason="empty_question",
            )
        if any(pattern.match(text) for pattern in self._anaphora_patterns):
            return IntentDecision(
                intent=Intent.UNSUPPORTED,
                confidence=0.99,
                reason="multi_turn_anaphora_unsupported",
            )
        if _contains_any(text, self._future_action_terms):
            return IntentDecision(
                intent=Intent.UNSUPPORTED,
                confidence=0.99,
                reason="future_or_external_action_unsupported",
            )
        if _contains_any(text, self._strict_causal_terms):
            return IntentDecision(
                intent=Intent.UNSUPPORTED,
                confidence=0.99,
                reason="strict_causal_request_unsupported",
            )

        has_gmv = _contains_any(text, self._gmv_terms)
        has_diagnosis_cue = _contains_any(text, self._diagnosis_terms)
        factor_count = sum(term in text for term in self._factor_terms)
        has_factor_analysis = _contains_any(text, self._factor_analysis_terms)
        if (has_gmv and has_diagnosis_cue) or (factor_count >= 2 and has_factor_analysis):
            return IntentDecision(
                intent=Intent.DIAGNOSIS,
                confidence=0.95,
                reason=(
                    "gmv_diagnosis_request"
                    if has_gmv
                    else "candidate_factor_diagnosis_request"
                ),
            )
        if has_diagnosis_cue and not has_gmv:
            return IntentDecision(
                intent=Intent.UNSUPPORTED,
                confidence=0.96,
                reason="non_gmv_diagnosis_unsupported",
            )
        if _contains_any(text, self._metric_terms) and _contains_any(text, self._query_terms):
            return IntentDecision(
                intent=Intent.QUERY,
                confidence=0.94,
                reason="explicit_data_query",
            )
        return IntentDecision(
            intent=Intent.UNSUPPORTED,
            confidence=0.45,
            reason="ambiguous_or_incomplete_question",
        )


DEFAULT_INTENT_ROUTER = IntentRouter()


async def intent_router_node(state: Mapping[str, Any]) -> dict[str, Any]:
    question = str(state.get("question") or state.get("query") or "")
    return DEFAULT_INTENT_ROUTER.route(question).model_dump(mode="json")


def route_after_intent(
    state: Mapping[str, Any],
) -> Literal["existing_nl2sql", "analysis_question_parser", "unsupported"]:
    decision = IntentDecision.model_validate(
        {
            "intent": state.get("intent"),
            "confidence": state.get("confidence"),
            "reason": state.get("reason"),
        }
    )
    if decision.intent is Intent.QUERY:
        return "existing_nl2sql"
    if decision.intent is Intent.DIAGNOSIS:
        return "analysis_question_parser"
    return "unsupported"
