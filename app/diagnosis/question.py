from __future__ import annotations

import calendar
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.diagnosis.intent import Intent
from app.metadata.catalog import MetadataCatalog


class ComparisonType(StrEnum):
    PREVIOUS_PERIOD = "previous_period"


class AnalysisDimension(StrEnum):
    REGION = "region"
    CATEGORY = "category"


class CandidateFactor(StrEnum):
    TRAFFIC = "traffic"
    PROMOTION = "promotion"
    INVENTORY = "inventory"


class AnalysisParseErrorCode(StrEnum):
    UNSUPPORTED_INTENT = "UNSUPPORTED_INTENT"
    UNKNOWN_METRIC = "UNKNOWN_METRIC"
    INVALID_TIME_RANGE = "INVALID_TIME_RANGE"
    MISSING_BASELINE = "MISSING_BASELINE"


class DatePeriod(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: date
    end: date

    @model_validator(mode="after")
    def ordered_period(self) -> DatePeriod:
        if self.end < self.start:
            raise ValueError("period end must not precede start")
        return self


class AnalysisScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    region: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    category: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")


class ParsedAnalysisQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_metric: Literal["gmv"]
    current_period: DatePeriod
    baseline_period: DatePeriod
    comparison_type: ComparisonType
    scope: AnalysisScope
    requested_dimensions: tuple[AnalysisDimension, ...] = ()
    requested_factors: tuple[CandidateFactor, ...] = ()

    @model_validator(mode="after")
    def validate_contract(self) -> ParsedAnalysisQuestion:
        if self.baseline_period.end >= self.current_period.start:
            raise ValueError("baseline period must precede current period")
        if len(self.requested_dimensions) != len(set(self.requested_dimensions)):
            raise ValueError("requested dimensions must be unique")
        if len(self.requested_factors) != len(set(self.requested_factors)):
            raise ValueError("requested factors must be unique")
        return self


class AnalysisParseError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: AnalysisParseErrorCode
    field: Literal["intent", "metric", "time", "baseline", "scope"]
    reason: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")


class AnalysisQuestionParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parsed_question: ParsedAnalysisQuestion | None = None
    error: AnalysisParseError | None = None

    @model_validator(mode="after")
    def exactly_one_result(self) -> AnalysisQuestionParseResult:
        if (self.parsed_question is None) == (self.error is None):
            raise ValueError("exactly one of parsed_question or error is required")
        return self


@dataclass(frozen=True)
class ParserVocabulary:
    metric_aliases: tuple[tuple[str, tuple[str, ...]], ...]
    region_aliases: tuple[tuple[str, tuple[str, ...]], ...]
    category_aliases: tuple[tuple[str, tuple[str, ...]], ...]

    @classmethod
    def from_catalog(cls, catalog: MetadataCatalog) -> ParserVocabulary:
        metric_aliases = tuple(
            (
                metric.metric_id,
                tuple(
                    dict.fromkeys((metric.metric_id, metric.display_name, *metric.aliases))
                ),
            )
            for metric in catalog.metrics
        )
        return cls(
            metric_aliases=metric_aliases,
            region_aliases=_catalog_value_aliases(catalog, "dim_region", "state_code"),
            category_aliases=_catalog_value_aliases(catalog, "dim_category", "category_id"),
        )


@dataclass(frozen=True, order=True)
class _Month:
    year: int
    month: int


@dataclass(frozen=True)
class _MonthExtraction:
    months: tuple[_Month, ...] = ()
    error: AnalysisParseError | None = None


def _catalog_value_aliases(
    catalog: MetadataCatalog,
    table_name: str,
    column_name: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    table = catalog.table_map.get(table_name)
    if table is None:
        return ()
    column = next((item for item in table.columns if item.name == column_name), None)
    if column is None:
        return ()
    return tuple(
        (canonical, tuple(dict.fromkeys((canonical, *aliases))))
        for canonical, aliases in sorted(column.value_aliases.items())
    )


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _compact(value: str) -> str:
    return re.sub(r"[^0-9a-z_\u4e00-\u9fff]+", "", _normalized(value))


def _alias_present(question: str, alias: str) -> bool:
    normalized_question = _normalized(question)
    normalized_alias = _normalized(alias).strip()
    if not normalized_alias:
        return False
    if re.fullmatch(r"[a-z0-9_]+", normalized_alias):
        return bool(
            re.search(
                rf"(?<![a-z0-9_]){re.escape(normalized_alias)}(?![a-z0-9_])",
                normalized_question,
            )
        )
    return _compact(normalized_alias) in _compact(normalized_question)


def _matched_values(
    question: str,
    aliases: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[str, ...]:
    return tuple(
        canonical
        for canonical, terms in aliases
        if any(_alias_present(question, term) for term in terms)
    )


def _error(
    code: AnalysisParseErrorCode,
    field: Literal["intent", "metric", "time", "baseline", "scope"],
    reason: str,
) -> AnalysisQuestionParseResult:
    return AnalysisQuestionParseResult(
        error=AnalysisParseError(code=code, field=field, reason=reason)
    )


def _previous_month(month: _Month) -> _Month:
    if month.month == 1:
        return _Month(month.year - 1, 12)
    return _Month(month.year, month.month - 1)


def _period(month: _Month) -> DatePeriod:
    last_day = calendar.monthrange(month.year, month.month)[1]
    return DatePeriod(
        start=date(month.year, month.month, 1),
        end=date(month.year, month.month, last_day),
    )


_CHINESE_MONTH = re.compile(r"(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月")
_ISO_MONTH = re.compile(r"(?<!\d)(?P<year>\d{4})-(?P<month>\d{1,2})(?![-\d])")
_PARTIAL_MONTH = re.compile(r"(?<!\d)(?P<month>\d{1,2})\s*月")
_COMPARE_MARKERS = ("相比", "相对", "对比", "比较", "基期")
_PREVIOUS_MARKERS = ("上月", "上个月", "前一个月", "前月")


def _extract_months(question: str) -> _MonthExtraction:
    normalized = _normalized(question)
    full_matches = sorted(
        [*_CHINESE_MONTH.finditer(normalized), *_ISO_MONTH.finditer(normalized)],
        key=lambda item: item.start(),
    )
    months: list[_Month] = []
    occupied: list[tuple[int, int]] = []
    for match in full_matches:
        candidate = _validated_month(match.group("year"), match.group("month"))
        if candidate is None:
            return _MonthExtraction(
                error=AnalysisParseError(
                    code=AnalysisParseErrorCode.INVALID_TIME_RANGE,
                    field="time",
                    reason="invalid_calendar_month",
                )
            )
        months.append(candidate)
        occupied.append(match.span())

    partials = [
        match
        for match in _PARTIAL_MONTH.finditer(normalized)
        if not any(start <= match.start() and match.end() <= end for start, end in occupied)
    ]
    if partials:
        if len(months) != 1 or len(partials) != 1:
            return _MonthExtraction(
                error=AnalysisParseError(
                    code=AnalysisParseErrorCode.INVALID_TIME_RANGE,
                    field="time",
                    reason="ambiguous_calendar_months",
                )
            )
        partial_number = int(partials[0].group("month"))
        if not 1 <= partial_number <= 12:
            return _MonthExtraction(
                error=AnalysisParseError(
                    code=AnalysisParseErrorCode.INVALID_TIME_RANGE,
                    field="time",
                    reason="invalid_calendar_month",
                )
            )
        current = months[0]
        inferred_year = current.year if partial_number < current.month else current.year - 1
        months.append(_Month(inferred_year, partial_number))

    unique_months = tuple(sorted(set(months)))
    if not unique_months:
        return _MonthExtraction(
            error=AnalysisParseError(
                code=AnalysisParseErrorCode.INVALID_TIME_RANGE,
                field="time",
                reason="missing_current_period",
            )
        )
    if len(unique_months) > 2:
        return _MonthExtraction(
            error=AnalysisParseError(
                code=AnalysisParseErrorCode.INVALID_TIME_RANGE,
                field="time",
                reason="too_many_calendar_months",
            )
        )
    if len(unique_months) == 1:
        has_explicit_comparison = any(marker in normalized for marker in _COMPARE_MARKERS)
        has_previous_marker = any(marker in normalized for marker in _PREVIOUS_MARKERS)
        if has_explicit_comparison and not has_previous_marker:
            return _MonthExtraction(
                error=AnalysisParseError(
                    code=AnalysisParseErrorCode.MISSING_BASELINE,
                    field="baseline",
                    reason="explicit_baseline_incomplete",
                )
            )
        current = unique_months[0]
        return _MonthExtraction((_previous_month(current), current))

    baseline, current = unique_months
    if _previous_month(current) != baseline:
        return _MonthExtraction(
            error=AnalysisParseError(
                code=AnalysisParseErrorCode.INVALID_TIME_RANGE,
                field="time",
                reason="non_adjacent_calendar_months",
            )
        )
    return _MonthExtraction((baseline, current))


def _validated_month(year_text: str, month_text: str) -> _Month | None:
    year = int(year_text)
    month = int(month_text)
    if not 1 <= year <= 9999 or not 1 <= month <= 12:
        return None
    return _Month(year, month)


_REGION_DIMENSION_PATTERNS = (
    re.compile(r"哪些.*(?:州|地区)"),
    re.compile(r"各(?:州|地区)"),
    re.compile(r"按(?:州|地区)"),
    re.compile(r"(?:州|地区)(?:变化)?贡献"),
)
_CATEGORY_DIMENSION_PATTERNS = (
    re.compile(r"哪些.*(?:品类|分类)"),
    re.compile(r"各(?:品类|分类)"),
    re.compile(r"按(?:品类|分类)"),
    re.compile(r"(?:品类|分类)(?:变化)?贡献"),
)
_REASON_TERMS = ("为什么", "原因", "根因", "归因", "异动", "进一步分析")
_FACTOR_TERMS = {
    CandidateFactor.TRAFFIC: ("traffic", "流量", "访客"),
    CandidateFactor.PROMOTION: ("promotion", "促销"),
    CandidateFactor.INVENTORY: ("inventory", "库存"),
}
_FACTOR_METRIC_IDS = {"visitors", "promotion_coverage", "inventory_fill_rate"}


class AnalysisQuestionParser:
    """Deterministic V1 parser backed by an injected Metadata Catalog vocabulary."""

    def __init__(self, vocabulary: ParserVocabulary) -> None:
        self._vocabulary = vocabulary

    @classmethod
    def from_catalog(cls, catalog: MetadataCatalog) -> AnalysisQuestionParser:
        return cls(ParserVocabulary.from_catalog(catalog))

    def parse(self, question: str, intent: Intent | str) -> AnalysisQuestionParseResult:
        try:
            parsed_intent = Intent(intent)
        except ValueError:
            parsed_intent = Intent.UNSUPPORTED
        if parsed_intent is not Intent.DIAGNOSIS:
            return _error(
                AnalysisParseErrorCode.UNSUPPORTED_INTENT,
                "intent",
                "diagnosis_intent_required",
            )

        factors = self._requested_factors(question)
        metric_matches = _matched_values(question, self._vocabulary.metric_aliases)
        non_factor_metrics = set(metric_matches) - _FACTOR_METRIC_IDS
        can_infer_v1_target = (
            set(factors) == set(CandidateFactor) and not non_factor_metrics
        )
        if "gmv" not in metric_matches and not can_infer_v1_target:
            return _error(
                AnalysisParseErrorCode.UNKNOWN_METRIC,
                "metric",
                "gmv_target_required",
            )

        month_extraction = _extract_months(question)
        if month_extraction.error is not None:
            return AnalysisQuestionParseResult(error=month_extraction.error)
        baseline_month, current_month = month_extraction.months

        scope_result = self._scope(question)
        if isinstance(scope_result, AnalysisParseError):
            return AnalysisQuestionParseResult(error=scope_result)

        dimensions = self._requested_dimensions(question, scope_result)
        if not factors and self._is_general_reason_request(question):
            factors = tuple(CandidateFactor)

        return AnalysisQuestionParseResult(
            parsed_question=ParsedAnalysisQuestion(
                target_metric="gmv",
                current_period=_period(current_month),
                baseline_period=_period(baseline_month),
                comparison_type=ComparisonType.PREVIOUS_PERIOD,
                scope=scope_result,
                requested_dimensions=dimensions,
                requested_factors=factors,
            )
        )

    def _scope(self, question: str) -> AnalysisScope | AnalysisParseError:
        regions = _matched_values(question, self._vocabulary.region_aliases)
        categories = _matched_values(question, self._vocabulary.category_aliases)
        if len(regions) > 1 or len(categories) > 1:
            return AnalysisParseError(
                code=AnalysisParseErrorCode.UNSUPPORTED_INTENT,
                field="scope",
                reason="multiple_scope_values_unsupported",
            )

        dimensions = self._explicit_dimensions(question)
        compact = _compact(question)
        if not regions and "州" in compact and AnalysisDimension.REGION not in dimensions:
            return AnalysisParseError(
                code=AnalysisParseErrorCode.UNSUPPORTED_INTENT,
                field="scope",
                reason="unregistered_region_scope",
            )
        if (
            not categories
            and "品类" in compact
            and AnalysisDimension.CATEGORY not in dimensions
        ):
            return AnalysisParseError(
                code=AnalysisParseErrorCode.UNSUPPORTED_INTENT,
                field="scope",
                reason="unregistered_category_scope",
            )
        return AnalysisScope(
            region=regions[0] if regions else None,
            category=categories[0] if categories else None,
        )

    def _requested_dimensions(
        self,
        question: str,
        scope: AnalysisScope,
    ) -> tuple[AnalysisDimension, ...]:
        explicit = self._explicit_dimensions(question)
        if explicit:
            return explicit
        if not self._is_general_reason_request(question):
            return ()
        return tuple(
            dimension
            for dimension in AnalysisDimension
            if getattr(scope, dimension.value) is None
        )

    @staticmethod
    def _explicit_dimensions(question: str) -> tuple[AnalysisDimension, ...]:
        compact = _compact(question)
        requested: list[AnalysisDimension] = []
        if any(pattern.search(compact) for pattern in _REGION_DIMENSION_PATTERNS):
            requested.append(AnalysisDimension.REGION)
        if any(pattern.search(compact) for pattern in _CATEGORY_DIMENSION_PATTERNS):
            requested.append(AnalysisDimension.CATEGORY)
        return tuple(requested)

    @staticmethod
    def _requested_factors(question: str) -> tuple[CandidateFactor, ...]:
        return tuple(
            factor
            for factor, terms in _FACTOR_TERMS.items()
            if any(_alias_present(question, term) for term in terms)
        )

    @staticmethod
    def _is_general_reason_request(question: str) -> bool:
        compact = _compact(question)
        return any(term in compact for term in _REASON_TERMS)


class AnalysisQuestionParserNode:
    """Injects parser dependencies outside Agent State and emits only JSON state."""

    def __init__(self, parser: AnalysisQuestionParser) -> None:
        self._parser = parser

    async def __call__(self, state: Mapping[str, Any]) -> dict[str, Any]:
        question = str(state.get("question") or state.get("query") or "")
        intent = str(state.get("intent") or "")
        return self._parser.parse(question, intent).model_dump(mode="json")
