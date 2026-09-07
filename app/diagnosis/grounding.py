"""将自然语言诊断问题绑定到规范指标、维度、取值与时间，并显式返回澄清或不支持状态。"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Iterable
from enum import StrEnum
from typing import Protocol

from elasticsearch import AsyncElasticsearch
from langchain_core.embeddings import Embeddings
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from qdrant_client import AsyncQdrantClient

from app.diagnosis.intent import Intent
from app.diagnosis.question import (
    AnalysisDimension,
    AnalysisParseError,
    AnalysisQuestionParser,
    AnalysisScope,
    ParsedAnalysisQuestion,
    ParserVocabulary,
)
from app.diagnosis.semantics import AnalysisSemanticRegistry
from app.metadata.catalog import MetadataCatalog
from app.metadata.retrieval import query_metadata_by_vector, retrieve_value


class SemanticBindingStatus(StrEnum):
    READY = "READY"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"


class BindingField(StrEnum):
    INTENT = "intent"
    METRIC = "metric"
    DIMENSION = "dimension"
    TIME = "time"
    BASELINE = "baseline"
    SCOPE = "scope"


class MetricGroundingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    score: float = Field(ge=-1.0, le=1.0)
    supported_for_diagnosis: bool


class DimensionGroundingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: AnalysisDimension
    score: float = Field(ge=-1.0, le=1.0)


class ValueGroundingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: AnalysisDimension
    canonical_value: str = Field(min_length=1, max_length=200)


class SemanticCandidateBundle(BaseModel):
    """一次检索返回的逻辑候选集合；候选必须能映射回 Catalog 中的规范对象。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metrics: tuple[MetricGroundingCandidate, ...] = ()
    dimensions: tuple[DimensionGroundingCandidate, ...] = ()
    values: tuple[ValueGroundingCandidate, ...] = ()

    @model_validator(mode="after")
    def unique_candidates(self) -> SemanticCandidateBundle:
        identities: tuple[tuple[str, object], ...] = (
            *(('metric', item.metric_id) for item in self.metrics),
            *(('dimension', item.dimension) for item in self.dimensions),
            *((f"value:{item.dimension.value}", item.canonical_value) for item in self.values),
        )
        if len(identities) != len(set(identities)):
            raise ValueError("semantic candidates must be unique")
        return self


class SemanticCandidateRetriever(Protocol):
    """语义候选检索边界，只返回有限候选，不负责决定最终绑定。"""

    async def retrieve(self, question: str) -> SemanticCandidateBundle: ...


class QdrantElasticsearchCandidateRetriever:
    """Reads bounded candidates and projects physical hits to logical semantics."""

    def __init__(
        self,
        qdrant_client: AsyncQdrantClient,
        elasticsearch_client: AsyncElasticsearch,
        embedding_client: Embeddings,
        catalog: MetadataCatalog,
        registry: AnalysisSemanticRegistry,
        *,
        score_threshold: float = 0.65,
        metric_limit: int = 5,
        column_limit: int = 10,
        value_limit: int = 5,
    ) -> None:
        if not 0.0 <= score_threshold <= 1.0:
            raise ValueError("score threshold must be between zero and one")
        if min(metric_limit, column_limit, value_limit) < 1:
            raise ValueError("retrieval limits must be positive")
        self._qdrant_client = qdrant_client
        self._elasticsearch_client = elasticsearch_client
        self._embedding_client = embedding_client
        self._catalog = catalog
        self._registry = registry
        self._score_threshold = score_threshold
        self._metric_limit = metric_limit
        self._column_limit = column_limit
        self._value_limit = value_limit

    async def retrieve(self, question: str) -> SemanticCandidateBundle:
        # 同一个问题向量并行查询指标、字段和值，三路结果随后统一映射到逻辑语义。
        embedding = await self._embedding_client.aembed_query(question)
        metric_hits, column_hits, value_hits = await asyncio.gather(
            query_metadata_by_vector(
                self._qdrant_client,
                embedding,
                "metric",
                self._metric_limit,
            ),
            query_metadata_by_vector(
                self._qdrant_client,
                embedding,
                "column",
                self._column_limit,
            ),
            retrieve_value(
                self._elasticsearch_client,
                question,
                self._value_limit,
            ),
        )

        # 低于阈值或 Catalog 中不存在的向量命中直接丢弃，检索不能创造新指标。
        catalog_metric_ids = {item.metric_id for item in self._catalog.metrics}
        metrics = _best_metric_candidates(
            [
                MetricGroundingCandidate(
                    metric_id=hit.object_id,
                    score=hit.score,
                    supported_for_diagnosis=hit.object_id in self._registry.metric_map,
                )
                for hit in metric_hits
                if hit.score >= self._score_threshold
                and hit.object_id in catalog_metric_ids
            ]
        )

        # 物理列先通过 Registry 映射成 region/category，Planner 不会看到真实列名。
        column_to_dimension = {
            column_id: definition.dimension
            for definition in self._registry.dimensions
            for column_id in definition.retrieval_column_ids
        }
        dimensions = _best_dimension_candidates(
            [
                DimensionGroundingCandidate(
                    dimension=column_to_dimension[hit.object_id],
                    score=hit.score,
                )
                for hit in column_hits
                if hit.score >= self._score_threshold
                and hit.object_id in column_to_dimension
            ]
        )

        # 值候选只有来自允许值列且通过业务格式检查，才可作为 Scope 候选。
        value_column_to_dimension = {
            column_id: definition.dimension
            for definition in self._registry.dimensions
            for column_id in definition.value_column_ids
        }
        values: list[ValueGroundingCandidate] = []
        for hit in value_hits:
            column_id = hit.get("column_id", "")
            dimension = value_column_to_dimension.get(column_id)
            canonical_value = hit.get("canonical_value", "")
            if dimension is None or not _valid_scope_value(dimension, canonical_value):
                continue
            candidate = ValueGroundingCandidate(
                dimension=dimension,
                canonical_value=canonical_value,
            )
            if candidate not in values:
                values.append(candidate)

        return SemanticCandidateBundle(
            metrics=metrics,
            dimensions=dimensions,
            values=tuple(values),
        )


def _best_metric_candidates(
    candidates: Iterable[MetricGroundingCandidate],
) -> tuple[MetricGroundingCandidate, ...]:
    best: dict[str, MetricGroundingCandidate] = {}
    for candidate in candidates:
        previous = best.get(candidate.metric_id)
        if previous is None or candidate.score > previous.score:
            best[candidate.metric_id] = candidate
    return tuple(sorted(best.values(), key=lambda item: (-item.score, item.metric_id)))


def _best_dimension_candidates(
    candidates: Iterable[DimensionGroundingCandidate],
) -> tuple[DimensionGroundingCandidate, ...]:
    best: dict[AnalysisDimension, DimensionGroundingCandidate] = {}
    for candidate in candidates:
        previous = best.get(candidate.dimension)
        if previous is None or candidate.score > previous.score:
            best[candidate.dimension] = candidate
    return tuple(
        sorted(best.values(), key=lambda item: (-item.score, item.dimension.value))
    )


def _valid_scope_value(dimension: AnalysisDimension, value: str) -> bool:
    try:
        if dimension is AnalysisDimension.REGION:
            AnalysisScope(region=value)
        else:
            AnalysisScope(category=value)
    except ValidationError:
        return False
    return True


class SemanticBindingResult(BaseModel):
    """语义绑定终态：READY、需要澄清或不支持三者之一，并携带稳定原因。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SemanticBindingStatus
    parsed_question: ParsedAnalysisQuestion | None = None
    reason: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    missing_fields: tuple[BindingField, ...] = ()
    ambiguous_fields: tuple[BindingField, ...] = ()
    candidates: SemanticCandidateBundle = SemanticCandidateBundle()
    suggested_question: str | None = None
    retrieval_used: bool = False
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_outcome(self) -> SemanticBindingResult:
        if self.status is SemanticBindingStatus.READY:
            if self.parsed_question is None or self.reason is not None:
                raise ValueError("READY requires only a parsed question")
            if self.missing_fields or self.ambiguous_fields:
                raise ValueError("READY cannot contain unresolved fields")
        elif self.parsed_question is not None or self.reason is None:
            raise ValueError("non-ready binding requires only a stable reason")
        if len(self.missing_fields) != len(set(self.missing_fields)):
            raise ValueError("missing fields must be unique")
        if len(self.ambiguous_fields) != len(set(self.ambiguous_fields)):
            raise ValueError("ambiguous fields must be unique")
        if set(self.missing_fields) & set(self.ambiguous_fields):
            raise ValueError("a field cannot be both missing and ambiguous")
        if len(self.limitations) != len(set(self.limitations)):
            raise ValueError("limitations must be unique")
        return self


class SemanticGrounder:
    """Runs deterministic parsing first and bounded semantic retrieval only as fallback."""

    def __init__(
        self,
        catalog: MetadataCatalog,
        registry: AnalysisSemanticRegistry,
        retriever: SemanticCandidateRetriever | None = None,
        *,
        minimum_score_gap: float = 0.05,
    ) -> None:
        if not 0.0 <= minimum_score_gap <= 1.0:
            raise ValueError("minimum score gap must be between zero and one")
        self._catalog = catalog
        self._registry = registry
        self._retriever = retriever
        self._minimum_score_gap = minimum_score_gap
        self._parser = AnalysisQuestionParser.from_catalog(catalog)

    async def bind(self, question: str, intent: Intent | str) -> SemanticBindingResult:
        """优先确定性解析；仅在可补全字段上检索，并拒绝低分差或歧义候选。"""

        # 确定性 Parser 成功时直接使用，避免已经明确的问题再受检索排序波动影响。
        deterministic = self._parser.parse(question, intent)
        if deterministic.parsed_question is not None:
            if not _needs_dimension_retrieval(question, deterministic.parsed_question):
                return SemanticBindingResult(
                    status=SemanticBindingStatus.READY,
                    parsed_question=deterministic.parsed_question,
                )
            return await self._resolve_explicit_dimension(
                question,
                deterministic.parsed_question,
            )

        error = deterministic.error
        if error is None:
            raise RuntimeError("parser returned neither question nor error")
        if not _retrieval_can_help(error):
            return _result_from_parse_error(error)
        if self._retriever is None:
            return _result_from_parse_error(error)

        # 外部检索不可用时关闭失败，不把连接错误当成可靠的业务绑定。
        try:
            candidates = await self._retriever.retrieve(question)
        except Exception:  # noqa: BLE001 - external retrieval must fail closed
            return SemanticBindingResult(
                status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
                reason="semantic_retrieval_unavailable",
                missing_fields=(_binding_field(error.field),),
                suggested_question=_suggested_question(),
                retrieval_used=True,
                limitations=("retrieval_unavailable",),
            )

        # 自动绑定要求唯一高分候选且与第二名拉开最小分差，否则返回澄清而不是猜测。
        selected_metric: str | None = None
        if error.field == "metric":
            selected_metric, metric_error = self._select_metric(candidates.metrics)
            if metric_error is not None:
                return metric_error.model_copy(
                    update={"candidates": candidates, "retrieval_used": True}
                )

        selected_values: dict[AnalysisDimension, str] = {}
        if error.field == "scope" or _scope_retrieval_requested(question):
            scope_dimensions = _requested_scope_dimensions(question)
            selected_values, value_error = _select_values(
                tuple(
                    candidate
                    for candidate in candidates.values
                    if candidate.dimension in scope_dimensions
                )
            )
            if value_error is not None:
                return SemanticBindingResult(
                    status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
                    reason="ambiguous_scope_value",
                    ambiguous_fields=(BindingField.SCOPE,),
                    candidates=candidates,
                    suggested_question=_suggested_question(),
                    retrieval_used=True,
                )

        # 检索结果只扩充受控词表，最终仍由同一个确定性 Parser 复核完整契约。
        retry_parser = _parser_with_candidates(
            self._catalog,
            question,
            selected_metric,
            selected_values,
        )
        retried = retry_parser.parse(question, intent)
        if retried.parsed_question is None:
            if retried.error is None:
                raise RuntimeError("parser returned neither question nor error")
            mapped = _result_from_parse_error(retried.error)
            return mapped.model_copy(
                update={"candidates": candidates, "retrieval_used": True}
            )
        parsed = retried.parsed_question
        if _needs_dimension_retrieval(question, parsed):
            dimension_result = self._apply_dimension_candidates(
                parsed,
                candidates,
                retrieval_used=True,
            )
            return dimension_result
        return SemanticBindingResult(
            status=SemanticBindingStatus.READY,
            parsed_question=parsed,
            candidates=candidates,
            retrieval_used=True,
        )

    async def _resolve_explicit_dimension(
        self,
        question: str,
        parsed: ParsedAnalysisQuestion,
    ) -> SemanticBindingResult:
        if self._retriever is None:
            return SemanticBindingResult(
                status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
                reason="unknown_dimension",
                missing_fields=(BindingField.DIMENSION,),
                suggested_question=_suggested_question(),
            )
        try:
            candidates = await self._retriever.retrieve(question)
        except Exception:  # noqa: BLE001 - external retrieval must fail closed
            return SemanticBindingResult(
                status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
                reason="semantic_retrieval_unavailable",
                missing_fields=(BindingField.DIMENSION,),
                suggested_question=_suggested_question(),
                retrieval_used=True,
                limitations=("retrieval_unavailable",),
            )
        return self._apply_dimension_candidates(parsed, candidates, retrieval_used=True)

    def _apply_dimension_candidates(
        self,
        parsed: ParsedAnalysisQuestion,
        candidates: SemanticCandidateBundle,
        *,
        retrieval_used: bool,
    ) -> SemanticBindingResult:
        ordered_candidates = tuple(
            sorted(
                candidates.dimensions,
                key=lambda item: (-item.score, item.dimension.value),
            )
        )
        selected = _select_dimension_ranked(
            ordered_candidates,
            self._minimum_score_gap,
        )
        if selected is None:
            field_kind = (
                "ambiguous"
                if len(ordered_candidates) > 1
                else "missing"
            )
            return SemanticBindingResult(
                status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
                reason=(
                    "ambiguous_dimension"
                    if field_kind == "ambiguous"
                    else "unknown_dimension"
                ),
                missing_fields=(BindingField.DIMENSION,) if field_kind == "missing" else (),
                ambiguous_fields=(
                    (BindingField.DIMENSION,) if field_kind == "ambiguous" else ()
                ),
                candidates=candidates,
                suggested_question=_suggested_question(),
                retrieval_used=retrieval_used,
            )
        updated = parsed.model_copy(update={"requested_dimensions": (selected.dimension,)})
        return SemanticBindingResult(
            status=SemanticBindingStatus.READY,
            parsed_question=updated,
            candidates=candidates,
            retrieval_used=retrieval_used,
        )

    def _select_metric(
        self,
        candidates: tuple[MetricGroundingCandidate, ...],
    ) -> tuple[str | None, SemanticBindingResult | None]:
        ordered_candidates = tuple(
            sorted(candidates, key=lambda item: (-item.score, item.metric_id))
        )
        selected = _select_ranked(ordered_candidates, self._minimum_score_gap)
        if selected is None:
            if len(ordered_candidates) > 1:
                return None, SemanticBindingResult(
                    status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
                    reason="ambiguous_metric",
                    ambiguous_fields=(BindingField.METRIC,),
                    suggested_question=_suggested_question(),
                )
            return None, SemanticBindingResult(
                status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
                reason="missing_or_unknown_metric",
                missing_fields=(BindingField.METRIC,),
                suggested_question=_suggested_question(),
            )
        if not selected.supported_for_diagnosis:
            return None, SemanticBindingResult(
                status=SemanticBindingStatus.UNSUPPORTED,
                reason="metric_not_supported",
            )
        return selected.metric_id, None


def _select_ranked(
    candidates: tuple[MetricGroundingCandidate, ...],
    score_gap: float,
) -> MetricGroundingCandidate | None:
    if not candidates:
        return None
    first = candidates[0]
    if len(candidates) == 1:
        return first
    if first.score - candidates[1].score < score_gap:
        return None
    return first


def _select_dimension_ranked(
    candidates: tuple[DimensionGroundingCandidate, ...],
    score_gap: float,
) -> DimensionGroundingCandidate | None:
    if not candidates:
        return None
    first = candidates[0]
    if len(candidates) == 1:
        return first
    if first.score - candidates[1].score < score_gap:
        return None
    return first


def _select_values(
    candidates: tuple[ValueGroundingCandidate, ...],
) -> tuple[dict[AnalysisDimension, str], AnalysisDimension | None]:
    grouped: dict[AnalysisDimension, list[str]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.dimension, []).append(candidate.canonical_value)
    ambiguous = next(
        (dimension for dimension, values in grouped.items() if len(set(values)) > 1),
        None,
    )
    if ambiguous is not None:
        return {}, ambiguous
    return {dimension: values[0] for dimension, values in grouped.items()}, None


def _parser_with_candidates(
    catalog: MetadataCatalog,
    question: str,
    metric_id: str | None,
    values: dict[AnalysisDimension, str],
) -> AnalysisQuestionParser:
    vocabulary = ParserVocabulary.from_catalog(catalog)
    metric_aliases = _append_alias(
        vocabulary.metric_aliases,
        metric_id,
        question,
    )
    region_aliases = _append_alias(
        vocabulary.region_aliases,
        values.get(AnalysisDimension.REGION),
        question,
    )
    category_aliases = _append_alias(
        vocabulary.category_aliases,
        values.get(AnalysisDimension.CATEGORY),
        question,
    )
    return AnalysisQuestionParser(
        ParserVocabulary(
            metric_aliases=metric_aliases,
            region_aliases=region_aliases,
            category_aliases=category_aliases,
        )
    )


def _append_alias(
    aliases: tuple[tuple[str, tuple[str, ...]], ...],
    canonical: str | None,
    question: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if canonical is None:
        return aliases
    updated: list[tuple[str, tuple[str, ...]]] = []
    found = False
    for existing_canonical, terms in aliases:
        if existing_canonical == canonical:
            updated.append((existing_canonical, tuple(dict.fromkeys((*terms, question)))))
            found = True
        else:
            updated.append((existing_canonical, terms))
    if not found:
        updated.append((canonical, (canonical, question)))
    return tuple(updated)


def _retrieval_can_help(error: AnalysisParseError) -> bool:
    return error.field in {"metric", "scope"} and error.reason not in {
        "multiple_scope_values_unsupported"
    }


def _result_from_parse_error(error: AnalysisParseError) -> SemanticBindingResult:
    if error.field == "intent":
        return SemanticBindingResult(
            status=SemanticBindingStatus.UNSUPPORTED,
            reason=error.reason,
        )
    if error.field == "metric":
        return SemanticBindingResult(
            status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
            reason="missing_or_unknown_metric",
            missing_fields=(BindingField.METRIC,),
            suggested_question=_suggested_question(),
        )
    if error.field == "baseline":
        return SemanticBindingResult(
            status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
            reason=error.reason,
            missing_fields=(BindingField.BASELINE,),
            suggested_question=_suggested_question(),
        )
    if error.field == "scope":
        return SemanticBindingResult(
            status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
            reason=error.reason,
            ambiguous_fields=(BindingField.SCOPE,)
            if error.reason == "multiple_scope_values_unsupported"
            else (),
            missing_fields=()
            if error.reason == "multiple_scope_values_unsupported"
            else (BindingField.SCOPE,),
            suggested_question=_suggested_question(),
        )
    if error.reason in {"missing_current_period", "ambiguous_calendar_months"}:
        return SemanticBindingResult(
            status=SemanticBindingStatus.CLARIFICATION_REQUIRED,
            reason=error.reason,
            missing_fields=(BindingField.TIME,)
            if error.reason == "missing_current_period"
            else (),
            ambiguous_fields=(BindingField.TIME,)
            if error.reason == "ambiguous_calendar_months"
            else (),
            suggested_question=_suggested_question(),
        )
    return SemanticBindingResult(
        status=SemanticBindingStatus.UNSUPPORTED,
        reason=error.reason,
    )


def _binding_field(field: str) -> BindingField:
    return BindingField(field)


_DIMENSION_INTENT = re.compile(r"(?:按|各|贡献|下钻|维度)")
_SCOPE_MARKER = re.compile(r"(?:州|地区|品类|分类)")


def _needs_dimension_retrieval(
    question: str,
    parsed: ParsedAnalysisQuestion,
) -> bool:
    normalized = unicodedata.normalize("NFKC", question).casefold()
    return not parsed.requested_dimensions and bool(_DIMENSION_INTENT.search(normalized))


def _scope_retrieval_requested(question: str) -> bool:
    normalized = unicodedata.normalize("NFKC", question).casefold()
    return bool(_SCOPE_MARKER.search(normalized))


def _requested_scope_dimensions(question: str) -> set[AnalysisDimension]:
    normalized = unicodedata.normalize("NFKC", question).casefold()
    dimensions: set[AnalysisDimension] = set()
    if "州" in normalized or "地区" in normalized:
        dimensions.add(AnalysisDimension.REGION)
    if "品类" in normalized or "分类" in normalized:
        dimensions.add(AnalysisDimension.CATEGORY)
    return dimensions


def _suggested_question() -> str:
    return "为什么 2018 年 5 月 GMV 相比 2018 年 4 月下降？"
