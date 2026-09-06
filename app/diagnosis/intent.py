from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Mapping
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from app.metadata.catalog import MetadataCatalog


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


class IntentSignals(BaseModel):
    """Safe, serializable signals supplied to the bounded semantic classifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    has_domain_term: bool
    has_gmv: bool
    has_diagnosis_cue: bool
    has_factor_bundle: bool
    has_query_operation: bool


class SemanticIntentDecision(BaseModel):
    """The only classifier output accepted by the hybrid router."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: Intent
    confidence: float = Field(ge=0, le=1)


class IntentClassifier(Protocol):
    async def classify(
        self,
        question: str,
        signals: IntentSignals,
    ) -> SemanticIntentDecision: ...


def _compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^0-9a-z_\u4e00-\u9fff]+", "", normalized)


def _normalized_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(term for value in terms if (term := _compact(value))))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


class IntentRouter:
    """High-precision rules with a bounded semantic fallback for ambiguity."""

    _default_domain_terms = (
        "gmv",
        "成交总额",
        "商品交易总额",
        "销售额",
        "成交金额",
        "订单",
        "订单量",
        "订单数",
        "客单价",
        "aov",
        "销量",
        "件数",
        "评分",
        "星级",
        "商品",
        "产品",
        "品类",
        "分类",
        "客户",
        "用户",
        "买家",
        "卖家",
        "商家",
        "付款",
        "支付",
        "配送",
        "物流",
        "评价",
        "评论",
        "地区",
        "州",
        "region",
        "state",
        "category",
        "product",
        "customer",
        "seller",
        "order",
        "payment",
        "delivery",
        "review",
        "访客",
        "流量",
        "促销",
        "库存",
        "转化率",
    )
    _gmv_terms = _normalized_terms(("gmv", "成交总额", "商品交易总额", "销售额"))
    _diagnosis_terms = _normalized_terms(
        (
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
    )
    _factor_terms = _normalized_terms(
        ("流量", "访客", "traffic", "促销", "promotion", "库存", "inventory")
    )
    _factor_analysis_terms = _normalized_terms(
        ("发生了什么", "什么变化", "分别变化", "验证", "影响")
    )
    _query_terms = _normalized_terms(
        (
            "多少",
            "是多少",
            "查询",
            "查看",
            "列出",
            "展示",
            "统计",
            "排名",
            "排行",
            "最高",
            "最低",
            "最大",
            "最小",
            "最好",
            "最差",
            "热销",
            "趋势",
            "有哪些",
            "是什么",
            "对比",
            "相比",
            "变化了多少",
            "同比",
            "环比",
            "增长率",
            "增幅",
            "降幅",
            "平均",
            "中位数",
            "总数",
            "汇总",
            "合计",
            "总和",
            "一共有",
            "占比",
            "份额",
            "构成",
            "分布",
            "明细",
            "分别",
            "每月",
            "每日",
            "各州",
            "各品类",
            "按州",
            "按品类",
            "list",
            "show",
            "rank",
            "ranking",
            "trend",
            "average",
            "median",
            "total",
            "share",
        )
    )
    _strict_causal_terms = _normalized_terms(
        ("严格因果", "因果关系", "唯一原因", "证明", "证实")
    )
    _future_action_terms = _normalized_terms(
        (
            "预测",
            "明年",
            "自动调价",
            "自动补货",
            "自动投放",
            "执行营销",
            "替我下单",
        )
    )
    _query_patterns = (
        re.compile(r"(?:前|后|倒数)(?:\d+|[一二三四五六七八九十百]+)(?:名|个)?"),
        re.compile(r"(?:top|bottom)\d+"),
        re.compile(r"(?:超过|低于|大于|小于|不少于|不超过|至少|至多|介于)"),
    )
    _anaphora_patterns = (
        re.compile(r"^(那|那么|上一个).*(呢|怎么样|如何)?$"),
        re.compile(r"^这个(呢|怎么样|如何|情况)$"),
        re.compile(r"^继续(分析|看|查)?$"),
    )

    def __init__(
        self,
        domain_terms: tuple[str, ...] | None = None,
        classifier: IntentClassifier | None = None,
        semantic_timeout_seconds: float = 8.0,
    ) -> None:
        if semantic_timeout_seconds <= 0 or semantic_timeout_seconds > 8:
            raise ValueError("semantic timeout must be greater than zero and at most 8 seconds")
        self._domain_terms = _normalized_terms(domain_terms or self._default_domain_terms)
        self._classifier = classifier
        self._semantic_timeout_seconds = semantic_timeout_seconds

    @classmethod
    def from_catalog(
        cls,
        catalog: MetadataCatalog,
        classifier: IntentClassifier | None = None,
        semantic_timeout_seconds: float = 8.0,
    ) -> IntentRouter:
        terms = list(cls._default_domain_terms)
        for metric in catalog.metrics:
            terms.extend((metric.metric_id, metric.display_name, *metric.aliases))
        for table in catalog.tables:
            terms.extend((table.table_name, *table.aliases))
            for column in table.columns:
                terms.extend((column.name, *column.aliases))
        return cls(tuple(terms), classifier, semantic_timeout_seconds)

    def signals(self, question: str) -> IntentSignals:
        text = _compact(question)
        factor_count = sum(term in text for term in self._factor_terms)
        return IntentSignals(
            has_domain_term=_contains_any(text, self._domain_terms),
            has_gmv=_contains_any(text, self._gmv_terms),
            has_diagnosis_cue=_contains_any(text, self._diagnosis_terms),
            has_factor_bundle=(
                factor_count >= 2 and _contains_any(text, self._factor_analysis_terms)
            ),
            has_query_operation=(
                _contains_any(text, self._query_terms)
                or any(pattern.search(text) for pattern in self._query_patterns)
            ),
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

        signals = self.signals(question)
        if (signals.has_gmv and signals.has_diagnosis_cue) or signals.has_factor_bundle:
            return IntentDecision(
                intent=Intent.DIAGNOSIS,
                confidence=0.95,
                reason=(
                    "gmv_diagnosis_request"
                    if signals.has_gmv
                    else "candidate_factor_diagnosis_request"
                ),
            )
        if signals.has_diagnosis_cue and not signals.has_gmv:
            return IntentDecision(
                intent=Intent.UNSUPPORTED,
                confidence=0.96,
                reason="non_gmv_diagnosis_unsupported",
            )
        if signals.has_domain_term and signals.has_query_operation:
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

    async def aroute(self, question: str) -> IntentDecision:
        deterministic = self.route(question)
        if (
            deterministic.reason != "ambiguous_or_incomplete_question"
            or self._classifier is None
        ):
            return deterministic

        signals = self.signals(question)
        try:
            semantic = await asyncio.wait_for(
                self._classifier.classify(question, signals),
                timeout=self._semantic_timeout_seconds,
            )
            semantic = SemanticIntentDecision.model_validate(semantic)
        except Exception:  # noqa: BLE001 - semantic failure must fail closed
            return IntentDecision(
                intent=Intent.UNSUPPORTED,
                confidence=0.0,
                reason="semantic_classifier_unavailable",
            )
        if semantic.confidence < 0.80:
            return IntentDecision(
                intent=Intent.UNSUPPORTED,
                confidence=semantic.confidence,
                reason="semantic_low_confidence",
            )
        if semantic.intent is Intent.QUERY and not signals.has_domain_term:
            return IntentDecision(
                intent=Intent.UNSUPPORTED,
                confidence=semantic.confidence,
                reason="semantic_domain_mismatch",
            )
        if semantic.intent is Intent.DIAGNOSIS and not signals.has_gmv:
            return IntentDecision(
                intent=Intent.UNSUPPORTED,
                confidence=semantic.confidence,
                reason="non_gmv_diagnosis_unsupported",
            )
        reasons = {
            Intent.QUERY: "semantic_data_query",
            Intent.DIAGNOSIS: "semantic_gmv_diagnosis",
            Intent.UNSUPPORTED: "semantic_request_unsupported",
        }
        return IntentDecision(
            intent=semantic.intent,
            confidence=semantic.confidence,
            reason=reasons[semantic.intent],
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
