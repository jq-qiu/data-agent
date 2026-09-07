"""根据问题、Registry、数据覆盖和质量状态评估当前请求实际可用的诊断方法。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.diagnosis.question import (
    AnalysisDimension,
    CandidateFactor,
    DatePeriod,
    ParsedAnalysisQuestion,
)
from app.metadata.catalog import MetadataCatalog


class CapabilityDataSource(StrEnum):
    WAREHOUSE = "warehouse"
    SYNTHETIC_CASE = "synthetic_case"


class DataQualityStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class AnalysisMethod(StrEnum):
    PERIOD_COMPARISON = "period_comparison"
    METRIC_DECOMPOSITION = "metric_decomposition"
    DIMENSION_CONTRIBUTION = "dimension_contribution"
    TRAFFIC_VALIDATION = "traffic_validation"
    PROMOTION_VALIDATION = "promotion_validation"
    INVENTORY_VALIDATION = "inventory_validation"
    CAUSAL_INFERENCE = "causal_inference"


class CapabilityLevel(StrEnum):
    UNSUPPORTED = "unsupported"
    PERIOD_COMPARISON = "period_comparison"
    METRIC_DECOMPOSITION = "metric_decomposition"
    DIMENSION_DIAGNOSIS = "dimension_diagnosis"
    ASSOCIATION_DIAGNOSIS = "association_diagnosis"


_METHOD_ORDER = {method: index for index, method in enumerate(AnalysisMethod)}
_DIMENSION_ORDER = {
    dimension: index for index, dimension in enumerate(AnalysisDimension)
}
_QUALIFIED_COLUMN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_STABLE_CODE = re.compile(r"^[a-z][a-z0-9_]*$")
_EVIDENCE_REFERENCE = re.compile(
    r"^(?:[a-z][a-z0-9_]*|[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)$"
)


class DataCapabilityProfile(BaseModel):
    """数据源在当前版本与时间范围内可提供的列、非空证据和质量状态。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: CapabilityDataSource
    available_period: DatePeriod
    available_columns: tuple[str, ...]
    non_empty_columns: tuple[str, ...]
    data_quality_status: DataQualityStatus
    data_quality_issues: tuple[str, ...] = ()
    experimental_design_present: bool = False

    @model_validator(mode="after")
    def validate_profile(self) -> DataCapabilityProfile:
        if len(self.available_columns) != len(set(self.available_columns)):
            raise ValueError("available columns must be unique")
        if len(self.non_empty_columns) != len(set(self.non_empty_columns)):
            raise ValueError("non-empty columns must be unique")
        if len(self.data_quality_issues) != len(set(self.data_quality_issues)):
            raise ValueError("data quality issues must be unique")
        if any(not _QUALIFIED_COLUMN.fullmatch(item) for item in self.available_columns):
            raise ValueError("available columns must use table.column identifiers")
        if not set(self.non_empty_columns).issubset(self.available_columns):
            raise ValueError("non-empty columns must be available")
        if any(not _STABLE_CODE.fullmatch(item) for item in self.data_quality_issues):
            raise ValueError("data quality issues must use stable codes")
        if self.data_quality_status is DataQualityStatus.PASS and self.data_quality_issues:
            raise ValueError("passing data quality cannot include issues")
        if self.data_quality_status is DataQualityStatus.FAIL and not self.data_quality_issues:
            raise ValueError("failed data quality requires at least one issue")
        return self


class CapabilityAssessment(BaseModel):
    """针对单个已解析问题的能力结论，Planner 只能选择 supported_methods。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: CapabilityLevel
    supported_methods: tuple[AnalysisMethod, ...]
    unsupported_methods: tuple[AnalysisMethod, ...]
    available_dimensions: tuple[AnalysisDimension, ...]
    missing_evidence: tuple[str, ...]
    data_quality_status: DataQualityStatus

    @model_validator(mode="after")
    def validate_assessment(self) -> CapabilityAssessment:
        if len(self.supported_methods) != len(set(self.supported_methods)):
            raise ValueError("supported methods must be unique")
        if len(self.unsupported_methods) != len(set(self.unsupported_methods)):
            raise ValueError("unsupported methods must be unique")
        if set(self.supported_methods) & set(self.unsupported_methods):
            raise ValueError("supported and unsupported methods must be disjoint")
        if self.supported_methods != _ordered_methods(self.supported_methods):
            raise ValueError("supported methods must use frozen order")
        if self.unsupported_methods != _ordered_methods(self.unsupported_methods):
            raise ValueError("unsupported methods must use frozen order")
        if self.available_dimensions != _ordered_dimensions(self.available_dimensions):
            raise ValueError("available dimensions must use frozen order")
        if len(self.missing_evidence) != len(set(self.missing_evidence)):
            raise ValueError("missing evidence entries must be unique")
        if any(not _EVIDENCE_REFERENCE.fullmatch(item) for item in self.missing_evidence):
            raise ValueError("missing evidence must use stable references")
        if AnalysisMethod.CAUSAL_INFERENCE in self.supported_methods:
            raise ValueError("causal inference is outside V1")
        if AnalysisMethod.CAUSAL_INFERENCE not in self.unsupported_methods:
            raise ValueError("causal inference must remain unsupported in V1")
        if self.data_quality_status is DataQualityStatus.FAIL and self.supported_methods:
            raise ValueError("failed data quality cannot support analysis methods")
        return self


def _ordered_methods(methods: tuple[AnalysisMethod, ...]) -> tuple[AnalysisMethod, ...]:
    return tuple(sorted(methods, key=_METHOD_ORDER.__getitem__))


def _ordered_dimensions(
    dimensions: tuple[AnalysisDimension, ...],
) -> tuple[AnalysisDimension, ...]:
    return tuple(sorted(dimensions, key=_DIMENSION_ORDER.__getitem__))


_WAREHOUSE_BASE = frozenset(
    {
        "dws_sales_region_daily.date_id",
        "dws_sales_region_daily.region_id",
        "dws_sales_region_daily.gmv",
    }
)
_WAREHOUSE_DECOMPOSITION = _WAREHOUSE_BASE | {
    "dws_sales_region_daily.order_count"
}
_WAREHOUSE_SCOPED_CATEGORY_BASE = frozenset(
    {
        "dws_sales_category_daily.date_id",
        "dws_sales_category_daily.region_id",
        "dws_sales_category_daily.category_id",
        "dws_sales_category_daily.gmv",
    }
)
_WAREHOUSE_SCOPED_CATEGORY_DECOMPOSITION = _WAREHOUSE_SCOPED_CATEGORY_BASE | {
    "dws_sales_category_daily.category_order_count"
}
_WAREHOUSE_DIMENSIONS = {
    AnalysisDimension.REGION: _WAREHOUSE_BASE,
    AnalysisDimension.CATEGORY: frozenset(
        {
            "dws_sales_category_daily.date_id",
            "dws_sales_category_daily.region_id",
            "dws_sales_category_daily.category_id",
            "dws_sales_category_daily.gmv",
        }
    ),
}
_WAREHOUSE_REGION_FACTORS = {
    CandidateFactor.TRAFFIC: _WAREHOUSE_DECOMPOSITION
    | {"dws_sales_region_daily.visitors"},
    CandidateFactor.PROMOTION: _WAREHOUSE_DECOMPOSITION
    | {
        "dws_sales_region_daily.visitors",
        "dws_sales_region_daily.promoted_sku_count",
        "dws_sales_region_daily.active_sku_count",
    },
    CandidateFactor.INVENTORY: _WAREHOUSE_DECOMPOSITION
    | {
        "dws_sales_region_daily.visitors",
        "dws_sales_region_daily.available_sku_count",
        "dws_sales_region_daily.required_sku_count",
    },
}
_WAREHOUSE_CATEGORY_BASE = frozenset(
    {
        "dws_sales_category_daily.date_id",
        "dws_sales_category_daily.region_id",
        "dws_sales_category_daily.category_id",
        "dws_sales_category_daily.category_order_count",
        "dws_sales_category_daily.category_visitors",
    }
)
_WAREHOUSE_CATEGORY_FACTORS = {
    CandidateFactor.TRAFFIC: _WAREHOUSE_CATEGORY_BASE,
    CandidateFactor.PROMOTION: _WAREHOUSE_CATEGORY_BASE
    | {
        "dws_sales_category_daily.promoted_sku_count",
        "dws_sales_category_daily.active_sku_count",
    },
    CandidateFactor.INVENTORY: _WAREHOUSE_CATEGORY_BASE
    | {
        "dws_sales_category_daily.available_sku_count",
        "dws_sales_category_daily.required_sku_count",
    },
}

_SYNTHETIC_BASE = frozenset(
    {
        "analysis_sales_region_daily.case_id",
        "analysis_sales_region_daily.date_id",
        "analysis_sales_region_daily.region_id",
        "analysis_sales_region_daily.period_role",
        "analysis_sales_region_daily.analysis_gmv",
    }
)
_SYNTHETIC_DECOMPOSITION = _SYNTHETIC_BASE | {
    "analysis_sales_region_daily.analysis_order_count"
}
_SYNTHETIC_SCOPED_CATEGORY_BASE = frozenset(
    {
        "analysis_sales_category_daily.case_id",
        "analysis_sales_category_daily.date_id",
        "analysis_sales_category_daily.region_id",
        "analysis_sales_category_daily.category_id",
        "analysis_sales_category_daily.period_role",
        "analysis_sales_category_daily.analysis_gmv",
    }
)
_SYNTHETIC_SCOPED_CATEGORY_DECOMPOSITION = _SYNTHETIC_SCOPED_CATEGORY_BASE | {
    "analysis_sales_category_daily.analysis_order_count"
}
_SYNTHETIC_DIMENSIONS = {
    AnalysisDimension.REGION: _SYNTHETIC_BASE,
    AnalysisDimension.CATEGORY: frozenset(
        {
            "analysis_sales_category_daily.case_id",
            "analysis_sales_category_daily.date_id",
            "analysis_sales_category_daily.region_id",
            "analysis_sales_category_daily.category_id",
            "analysis_sales_category_daily.period_role",
            "analysis_sales_category_daily.analysis_gmv",
        }
    ),
}
_SYNTHETIC_REGION_FACTORS = {
    CandidateFactor.TRAFFIC: _SYNTHETIC_DECOMPOSITION
    | {"analysis_sales_region_daily.visitors"},
    CandidateFactor.PROMOTION: _SYNTHETIC_DECOMPOSITION
    | {
        "analysis_sales_region_daily.visitors",
        "analysis_sales_region_daily.promoted_sku_count",
        "analysis_sales_region_daily.active_sku_count",
    },
    CandidateFactor.INVENTORY: _SYNTHETIC_DECOMPOSITION
    | {
        "analysis_sales_region_daily.visitors",
        "analysis_sales_region_daily.available_sku_count",
        "analysis_sales_region_daily.required_sku_count",
    },
}
_SYNTHETIC_CATEGORY_BASE = frozenset(
    {
        "analysis_sales_category_daily.case_id",
        "analysis_sales_category_daily.date_id",
        "analysis_sales_category_daily.region_id",
        "analysis_sales_category_daily.category_id",
        "analysis_sales_category_daily.period_role",
        "analysis_sales_category_daily.analysis_order_count",
        "analysis_sales_category_daily.visitors",
    }
)
_SYNTHETIC_CATEGORY_FACTORS = {
    CandidateFactor.TRAFFIC: _SYNTHETIC_CATEGORY_BASE,
    CandidateFactor.PROMOTION: _SYNTHETIC_CATEGORY_BASE
    | {
        "analysis_sales_category_daily.promoted_sku_count",
        "analysis_sales_category_daily.active_sku_count",
    },
    CandidateFactor.INVENTORY: _SYNTHETIC_CATEGORY_BASE
    | {
        "analysis_sales_category_daily.available_sku_count",
        "analysis_sales_category_daily.required_sku_count",
    },
}

_REQUIRED_RELATIONSHIPS = frozenset(
    {
        "region_daily_to_date",
        "region_daily_to_region",
        "category_daily_to_date",
        "category_daily_to_region",
        "category_daily_to_category",
        "analysis_region_to_date",
        "analysis_region_to_region",
        "analysis_category_to_date",
        "analysis_category_to_region",
        "analysis_category_to_category",
    }
)

_FACTOR_METHOD = {
    CandidateFactor.TRAFFIC: AnalysisMethod.TRAFFIC_VALIDATION,
    CandidateFactor.PROMOTION: AnalysisMethod.PROMOTION_VALIDATION,
    CandidateFactor.INVENTORY: AnalysisMethod.INVENTORY_VALIDATION,
}


class CapabilityAssessor:
    """Allows only methods backed by registered, non-empty, in-range data."""

    def __init__(self, catalog: MetadataCatalog) -> None:
        self._catalog = catalog
        self._validate_catalog_contract()

    def assess(
        self,
        question: ParsedAnalysisQuestion,
        profile: DataCapabilityProfile,
    ) -> CapabilityAssessment:
        """校验期间、数据质量、字段和证据非空性，再返回实际可执行方法集合。"""

        # 先拒绝 Profile 中 Catalog 未登记的列，防止能力判断建立在未知 Schema 上。
        self._validate_profile_columns(profile)
        desired = self._desired_methods(question)
        available_dimensions = self._available_dimensions(question, profile)

        # 数据质量失败是硬停止条件：即使字段齐全，也不能继续生成诊断任务。
        if profile.data_quality_status is DataQualityStatus.FAIL:
            return CapabilityAssessment(
                level=CapabilityLevel.UNSUPPORTED,
                supported_methods=(),
                unsupported_methods=_ordered_methods(
                    (*desired, AnalysisMethod.CAUSAL_INFERENCE)
                ),
                available_dimensions=available_dimensions,
                missing_evidence=("data_quality_failed", *profile.data_quality_issues),
                data_quality_status=profile.data_quality_status,
            )

        # 期间覆盖和基础 GMV 列是所有诊断方法的公共前置 Gate。
        missing_periods = self._missing_periods(question, profile)
        base_required = self._base_requirements(question, profile.source)
        missing_base = self._missing_columns(profile, base_required)
        if missing_periods or missing_base:
            return CapabilityAssessment(
                level=CapabilityLevel.UNSUPPORTED,
                supported_methods=(),
                unsupported_methods=_ordered_methods(
                    (*desired, AnalysisMethod.CAUSAL_INFERENCE)
                ),
                available_dimensions=available_dimensions,
                missing_evidence=tuple(dict.fromkeys((*missing_periods, *missing_base))),
                data_quality_status=profile.data_quality_status,
            )

        supported: list[AnalysisMethod] = [AnalysisMethod.PERIOD_COMPARISON]
        unsupported: list[AnalysisMethod] = [AnalysisMethod.CAUSAL_INFERENCE]
        missing: list[str] = []

        # 公共 Gate 通过后逐项开放能力；某一方法缺列不会错误关闭其他独立方法。
        decomposition_missing = self._missing_columns(
            profile, self._decomposition_requirements(question, profile.source)
        )
        if decomposition_missing:
            unsupported.append(AnalysisMethod.METRIC_DECOMPOSITION)
            missing.extend(decomposition_missing)
        else:
            supported.append(AnalysisMethod.METRIC_DECOMPOSITION)

        if question.requested_dimensions:
            missing_dimensions = [
                dimension
                for dimension in question.requested_dimensions
                if dimension not in available_dimensions
            ]
            if len(missing_dimensions) < len(question.requested_dimensions):
                supported.append(AnalysisMethod.DIMENSION_CONTRIBUTION)
            else:
                unsupported.append(AnalysisMethod.DIMENSION_CONTRIBUTION)
            for dimension in missing_dimensions:
                missing.extend(
                    self._missing_columns(
                        profile,
                        self._dimension_requirements(question, profile.source)[dimension],
                    )
                )

        # 真实 DWS 与 Synthetic 表的物理字段不同，由 source 选择对应的固定需求集合。
        factor_requirements = self._factor_requirements(question, profile.source)
        for factor in question.requested_factors:
            method = _FACTOR_METHOD[factor]
            factor_missing = self._missing_columns(profile, factor_requirements[factor])
            if factor_missing:
                unsupported.append(method)
                missing.extend(factor_missing)
            else:
                supported.append(method)

        supported_tuple = _ordered_methods(tuple(supported))
        return CapabilityAssessment(
            level=self._level(supported_tuple),
            supported_methods=supported_tuple,
            unsupported_methods=_ordered_methods(tuple(unsupported)),
            available_dimensions=available_dimensions,
            missing_evidence=tuple(dict.fromkeys(missing)),
            data_quality_status=profile.data_quality_status,
        )

    def _validate_catalog_contract(self) -> None:
        metric_map = {metric.metric_id: metric for metric in self._catalog.metrics}
        gmv = metric_map.get("gmv")
        if gmv is None or not {"region", "category"}.issubset(gmv.allowed_dimensions):
            raise ValueError("Catalog must register GMV with region and category dimensions")
        required_columns = set().union(
            _WAREHOUSE_BASE,
            _WAREHOUSE_DECOMPOSITION,
            _WAREHOUSE_SCOPED_CATEGORY_BASE,
            _WAREHOUSE_SCOPED_CATEGORY_DECOMPOSITION,
            *_WAREHOUSE_DIMENSIONS.values(),
            *_WAREHOUSE_REGION_FACTORS.values(),
            *_WAREHOUSE_CATEGORY_FACTORS.values(),
            _SYNTHETIC_BASE,
            _SYNTHETIC_DECOMPOSITION,
            _SYNTHETIC_SCOPED_CATEGORY_BASE,
            _SYNTHETIC_SCOPED_CATEGORY_DECOMPOSITION,
            *_SYNTHETIC_DIMENSIONS.values(),
            *_SYNTHETIC_REGION_FACTORS.values(),
            *_SYNTHETIC_CATEGORY_FACTORS.values(),
        )
        missing_columns = required_columns - self._catalog.column_ids
        if missing_columns:
            raise ValueError(f"Catalog is missing capability columns: {sorted(missing_columns)}")
        allowed_relationships = {
            item.relation_id for item in self._catalog.relationships if item.allowed
        }
        missing_relationships = _REQUIRED_RELATIONSHIPS - allowed_relationships
        if missing_relationships:
            raise ValueError(
                "Catalog is missing capability relationships: "
                f"{sorted(missing_relationships)}"
            )

    def _validate_profile_columns(self, profile: DataCapabilityProfile) -> None:
        unknown = set(profile.available_columns) - self._catalog.column_ids
        if unknown:
            raise ValueError(f"Data profile contains unknown Catalog columns: {sorted(unknown)}")

    @staticmethod
    def _desired_methods(question: ParsedAnalysisQuestion) -> tuple[AnalysisMethod, ...]:
        methods = [
            AnalysisMethod.PERIOD_COMPARISON,
            AnalysisMethod.METRIC_DECOMPOSITION,
        ]
        if question.requested_dimensions:
            methods.append(AnalysisMethod.DIMENSION_CONTRIBUTION)
        methods.extend(_FACTOR_METHOD[factor] for factor in question.requested_factors)
        return _ordered_methods(tuple(methods))

    @staticmethod
    def _missing_periods(
        question: ParsedAnalysisQuestion,
        profile: DataCapabilityProfile,
    ) -> tuple[str, ...]:
        missing: list[str] = []
        available = profile.available_period
        if not (
            available.start <= question.baseline_period.start
            and question.baseline_period.end <= available.end
        ):
            missing.append("baseline_period")
        if not (
            available.start <= question.current_period.start
            and question.current_period.end <= available.end
        ):
            missing.append("current_period")
        return tuple(missing)

    @staticmethod
    def _missing_columns(
        profile: DataCapabilityProfile,
        required: frozenset[str] | set[str],
    ) -> tuple[str, ...]:
        usable = set(profile.available_columns) & set(profile.non_empty_columns)
        return tuple(sorted(set(required) - usable))

    def _available_dimensions(
        self,
        question: ParsedAnalysisQuestion,
        profile: DataCapabilityProfile,
    ) -> tuple[AnalysisDimension, ...]:
        requirements = self._dimension_requirements(question, profile.source)
        return tuple(
            dimension
            for dimension in AnalysisDimension
            if not self._missing_columns(profile, requirements[dimension])
        )

    @staticmethod
    def _base_requirements(
        question: ParsedAnalysisQuestion,
        source: CapabilityDataSource,
    ) -> frozenset[str]:
        category_scope = question.scope.category is not None
        if source is CapabilityDataSource.WAREHOUSE:
            return (
                _WAREHOUSE_SCOPED_CATEGORY_BASE if category_scope else _WAREHOUSE_BASE
            )
        return _SYNTHETIC_SCOPED_CATEGORY_BASE if category_scope else _SYNTHETIC_BASE

    @staticmethod
    def _decomposition_requirements(
        question: ParsedAnalysisQuestion,
        source: CapabilityDataSource,
    ) -> frozenset[str]:
        category_scope = question.scope.category is not None
        if source is CapabilityDataSource.WAREHOUSE:
            return frozenset(
                _WAREHOUSE_SCOPED_CATEGORY_DECOMPOSITION
                if category_scope
                else _WAREHOUSE_DECOMPOSITION
            )
        return frozenset(
            _SYNTHETIC_SCOPED_CATEGORY_DECOMPOSITION
            if category_scope
            else _SYNTHETIC_DECOMPOSITION
        )

    @staticmethod
    def _dimension_requirements(
        question: ParsedAnalysisQuestion,
        source: CapabilityDataSource,
    ) -> dict[AnalysisDimension, frozenset[str]]:
        category_scope = question.scope.category is not None
        if source is CapabilityDataSource.WAREHOUSE:
            if category_scope:
                return {
                    AnalysisDimension.REGION: _WAREHOUSE_SCOPED_CATEGORY_BASE,
                    AnalysisDimension.CATEGORY: _WAREHOUSE_SCOPED_CATEGORY_BASE,
                }
            return _WAREHOUSE_DIMENSIONS
        if category_scope:
            return {
                AnalysisDimension.REGION: _SYNTHETIC_SCOPED_CATEGORY_BASE,
                AnalysisDimension.CATEGORY: _SYNTHETIC_SCOPED_CATEGORY_BASE,
            }
        return _SYNTHETIC_DIMENSIONS

    @staticmethod
    def _factor_requirements(
        question: ParsedAnalysisQuestion,
        source: CapabilityDataSource,
    ) -> dict[CandidateFactor, frozenset[str]]:
        category_scope = question.scope.category is not None
        if source is CapabilityDataSource.WAREHOUSE:
            return (
                _WAREHOUSE_CATEGORY_FACTORS
                if category_scope
                else _WAREHOUSE_REGION_FACTORS
            )
        return (
            _SYNTHETIC_CATEGORY_FACTORS
            if category_scope
            else _SYNTHETIC_REGION_FACTORS
        )

    @staticmethod
    def _level(supported: tuple[AnalysisMethod, ...]) -> CapabilityLevel:
        if any(
            method
            in {
                AnalysisMethod.TRAFFIC_VALIDATION,
                AnalysisMethod.PROMOTION_VALIDATION,
                AnalysisMethod.INVENTORY_VALIDATION,
            }
            for method in supported
        ):
            return CapabilityLevel.ASSOCIATION_DIAGNOSIS
        if AnalysisMethod.DIMENSION_CONTRIBUTION in supported:
            return CapabilityLevel.DIMENSION_DIAGNOSIS
        if AnalysisMethod.METRIC_DECOMPOSITION in supported:
            return CapabilityLevel.METRIC_DECOMPOSITION
        if AnalysisMethod.PERIOD_COMPARISON in supported:
            return CapabilityLevel.PERIOD_COMPARISON
        return CapabilityLevel.UNSUPPORTED


class CapabilityAssessmentNode:
    """Keeps Catalog/profile dependencies outside State and emits JSON capability."""

    def __init__(
        self,
        assessor: CapabilityAssessor,
        profile: DataCapabilityProfile,
    ) -> None:
        self._assessor = assessor
        self._profile = profile

    async def __call__(self, state: Mapping[str, Any]) -> dict[str, Any]:
        question = ParsedAnalysisQuestion.model_validate(state.get("parsed_question"))
        assessment = self._assessor.assess(question, self._profile)
        return {"capability": assessment.model_dump(mode="json")}
