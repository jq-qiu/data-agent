from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.diagnosis.capability import (
    AnalysisMethod,
    CapabilityAssessment,
    DataQualityStatus,
)
from app.diagnosis.planner import TaskMethod
from app.diagnosis.question import (
    AnalysisDimension,
    CandidateFactor,
    ParsedAnalysisQuestion,
)
from app.metadata.catalog import MetadataCatalog


class ClaimType(StrEnum):
    FACT = "FACT"
    ASSOCIATION = "ASSOCIATION"


class MetricAnalysisDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=1)
    analysis_identity: str = Field(min_length=1)
    decomposition_metrics: tuple[str, ...]
    dimensions: tuple[AnalysisDimension, ...]
    candidate_factors: tuple[CandidateFactor, ...]
    metric_version: str = Field(min_length=1)


class DimensionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: AnalysisDimension
    display_name: str = Field(min_length=1)
    business_role: str = Field(min_length=1)
    retrieval_column_ids: tuple[str, ...]
    value_column_ids: tuple[str, ...]
    mutually_exclusive: bool
    complete_for_contribution: bool

    @model_validator(mode="after")
    def validate_columns(self) -> DimensionDefinition:
        if not self.retrieval_column_ids:
            raise ValueError("dimension requires retrieval columns")
        if len(self.retrieval_column_ids) != len(set(self.retrieval_column_ids)):
            raise ValueError("dimension retrieval columns must be unique")
        if len(self.value_column_ids) != len(set(self.value_column_ids)):
            raise ValueError("dimension value columns must be unique")
        if not set(self.value_column_ids).issubset(self.retrieval_column_ids):
            raise ValueError("value columns must be retrieval columns")
        return self


class CandidateFactorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    factor: CandidateFactor
    display_name: str = Field(min_length=1)
    primary_metric_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    supporting_metric_ids: tuple[str, ...]
    capability_method: AnalysisMethod
    minimum_evidence: tuple[str, ...]
    claim_type: ClaimType = ClaimType.ASSOCIATION


class AnalysisToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: TaskMethod
    display_name: str = Field(min_length=1)
    capability_methods: tuple[AnalysisMethod, ...]
    requires_period_comparison: bool


class AnalysisSemanticRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    version: str = Field(min_length=1)
    metrics: tuple[MetricAnalysisDefinition, ...]
    dimensions: tuple[DimensionDefinition, ...]
    factors: tuple[CandidateFactorDefinition, ...]
    tools: tuple[AnalysisToolDefinition, ...]

    @model_validator(mode="after")
    def validate_unique_ids(self) -> AnalysisSemanticRegistry:
        groups = (
            ("metric", tuple(item.metric_id for item in self.metrics)),
            ("dimension", tuple(item.dimension for item in self.dimensions)),
            ("factor", tuple(item.factor for item in self.factors)),
            ("tool", tuple(item.method for item in self.tools)),
        )
        for label, values in groups:
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} semantic definitions")
        return self

    @property
    def metric_map(self) -> dict[str, MetricAnalysisDefinition]:
        return {item.metric_id: item for item in self.metrics}

    @property
    def dimension_map(self) -> dict[AnalysisDimension, DimensionDefinition]:
        return {item.dimension: item for item in self.dimensions}

    @property
    def factor_map(self) -> dict[CandidateFactor, CandidateFactorDefinition]:
        return {item.factor: item for item in self.factors}

    @property
    def tool_map(self) -> dict[TaskMethod, AnalysisToolDefinition]:
        return {item.method: item for item in self.tools}

    @classmethod
    def from_catalog(cls, catalog: MetadataCatalog) -> AnalysisSemanticRegistry:
        catalog_metrics = {item.metric_id: item for item in catalog.metrics}
        gmv = catalog_metrics.get("gmv")
        if gmv is None:
            raise ValueError("analysis semantics require the registered gmv metric")

        registry = cls(
            version="analysis-semantics-v1",
            metrics=(
                MetricAnalysisDefinition(
                    metric_id="gmv",
                    display_name=gmv.display_name,
                    analysis_identity="GMV = Order Count × AOV",
                    decomposition_metrics=("order_count", "aov"),
                    dimensions=tuple(AnalysisDimension),
                    candidate_factors=tuple(CandidateFactor),
                    metric_version=gmv.version,
                ),
            ),
            dimensions=(
                DimensionDefinition(
                    dimension=AnalysisDimension.REGION,
                    display_name="客户所在州",
                    business_role="customer_brazilian_state",
                    retrieval_column_ids=(
                        "dim_region.state_code",
                        "dim_customer.state",
                        "dws_sales_region_daily.region_id",
                        "dws_sales_category_daily.region_id",
                        "analysis_sales_region_daily.region_id",
                        "analysis_sales_category_daily.region_id",
                    ),
                    value_column_ids=("dim_region.state_code",),
                    mutually_exclusive=True,
                    complete_for_contribution=True,
                ),
                DimensionDefinition(
                    dimension=AnalysisDimension.CATEGORY,
                    display_name="商品品类",
                    business_role="normalized_product_category",
                    retrieval_column_ids=(
                        "dim_category.category_id",
                        "dim_category.category_name_pt",
                        "dim_category.category_name_en",
                        "dim_product.category_id",
                        "dws_sales_category_daily.category_id",
                        "analysis_sales_category_daily.category_id",
                    ),
                    value_column_ids=("dim_category.category_id",),
                    mutually_exclusive=True,
                    complete_for_contribution=True,
                ),
            ),
            factors=(
                CandidateFactorDefinition(
                    factor=CandidateFactor.TRAFFIC,
                    display_name="流量",
                    primary_metric_id="visitors",
                    supporting_metric_ids=("conversion_rate", "order_count"),
                    capability_method=AnalysisMethod.TRAFFIC_VALIDATION,
                    minimum_evidence=(
                        "same_period",
                        "same_scope",
                        "directionally_consistent_metric_chain",
                    ),
                ),
                CandidateFactorDefinition(
                    factor=CandidateFactor.PROMOTION,
                    display_name="促销",
                    primary_metric_id="promotion_coverage",
                    supporting_metric_ids=("conversion_rate", "order_count"),
                    capability_method=AnalysisMethod.PROMOTION_VALIDATION,
                    minimum_evidence=(
                        "same_period",
                        "same_scope",
                        "directionally_consistent_metric_chain",
                    ),
                ),
                CandidateFactorDefinition(
                    factor=CandidateFactor.INVENTORY,
                    display_name="库存",
                    primary_metric_id="inventory_fill_rate",
                    supporting_metric_ids=("conversion_rate", "order_count"),
                    capability_method=AnalysisMethod.INVENTORY_VALIDATION,
                    minimum_evidence=(
                        "same_period",
                        "same_scope",
                        "directionally_consistent_metric_chain",
                    ),
                ),
            ),
            tools=(
                AnalysisToolDefinition(
                    method=TaskMethod.PERIOD_COMPARISON,
                    display_name="期间对比",
                    capability_methods=(AnalysisMethod.PERIOD_COMPARISON,),
                    requires_period_comparison=False,
                ),
                AnalysisToolDefinition(
                    method=TaskMethod.METRIC_DECOMPOSITION,
                    display_name="指标拆解",
                    capability_methods=(AnalysisMethod.METRIC_DECOMPOSITION,),
                    requires_period_comparison=True,
                ),
                AnalysisToolDefinition(
                    method=TaskMethod.DIMENSION_CONTRIBUTION,
                    display_name="维度贡献",
                    capability_methods=(AnalysisMethod.DIMENSION_CONTRIBUTION,),
                    requires_period_comparison=True,
                ),
                AnalysisToolDefinition(
                    method=TaskMethod.CANDIDATE_VALIDATION,
                    display_name="候选因素验证",
                    capability_methods=(
                        AnalysisMethod.TRAFFIC_VALIDATION,
                        AnalysisMethod.PROMOTION_VALIDATION,
                        AnalysisMethod.INVENTORY_VALIDATION,
                    ),
                    requires_period_comparison=True,
                ),
            ),
        )
        _validate_registry_references(registry, catalog)
        return registry


def _validate_registry_references(
    registry: AnalysisSemanticRegistry,
    catalog: MetadataCatalog,
) -> None:
    catalog_metrics = {item.metric_id: item for item in catalog.metrics}
    catalog_columns = catalog.column_ids
    for metric in registry.metrics:
        physical_metric = catalog_metrics.get(metric.metric_id)
        if physical_metric is None:
            raise ValueError(f"unknown metric semantic reference: {metric.metric_id}")
        referenced_metrics = set(metric.decomposition_metrics)
        if not referenced_metrics.issubset(catalog_metrics):
            raise ValueError("unknown decomposition metric semantic reference")
        if not {item.value for item in metric.dimensions}.issubset(
            physical_metric.allowed_dimensions
        ):
            raise ValueError("analysis dimension is not allowed by the metric registry")

    for dimension in registry.dimensions:
        if not set(dimension.retrieval_column_ids).issubset(catalog_columns):
            raise ValueError(f"unknown retrieval columns for {dimension.dimension.value}")

    for factor in registry.factors:
        metric_ids = {factor.primary_metric_id, *factor.supporting_metric_ids}
        if not metric_ids.issubset(catalog_metrics):
            raise ValueError(f"unknown factor metric reference: {factor.factor.value}")
        if factor.claim_type is not ClaimType.ASSOCIATION:
            raise ValueError("V1 candidate factors must remain association claims")


class MetricSemanticContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str
    display_name: str
    analysis_identity: str
    decomposition_metrics: tuple[str, ...]
    metric_version: str


class DimensionSemanticContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: AnalysisDimension
    display_name: str
    business_role: str
    mutually_exclusive: bool
    complete_for_contribution: bool


class FactorSemanticContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    factor: CandidateFactor
    display_name: str
    primary_metric_id: str
    supporting_metric_ids: tuple[str, ...]
    minimum_evidence: tuple[str, ...]
    claim_type: ClaimType


class ToolSemanticContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: TaskMethod
    display_name: str
    requires_period_comparison: bool


class PlannerConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tasks: int = Field(default=4, ge=1, le=4)
    sql_allowed: bool = False
    physical_schema_allowed: bool = False
    deterministic_math_required: bool = True
    validated_evidence_required: bool = True
    causal_claims_allowed: bool = False


class PlannerSemanticContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    context_version: str = "planner-semantic-context-v1"
    parsed_question: ParsedAnalysisQuestion
    metric: MetricSemanticContext
    available_dimensions: tuple[DimensionSemanticContext, ...]
    available_factors: tuple[FactorSemanticContext, ...]
    available_tools: tuple[ToolSemanticContext, ...]
    limitations: tuple[str, ...]
    data_quality_status: DataQualityStatus
    constraints: PlannerConstraints = PlannerConstraints()


class PlannerSemanticContextBuilder:
    def __init__(self, registry: AnalysisSemanticRegistry) -> None:
        self._registry = registry

    def build(
        self,
        question: ParsedAnalysisQuestion,
        capability: CapabilityAssessment,
    ) -> PlannerSemanticContext:
        metric = self._registry.metric_map.get(question.target_metric)
        if metric is None:
            raise ValueError("parsed metric is not registered for analysis")

        supported = set(capability.supported_methods)
        available_dimension_ids = set(capability.available_dimensions)
        dimensions = tuple(
            self._dimension_context(self._registry.dimension_map[dimension])
            for dimension in metric.dimensions
            if dimension in question.requested_dimensions
            and dimension in available_dimension_ids
            and AnalysisMethod.DIMENSION_CONTRIBUTION in supported
        )
        factors = tuple(
            self._factor_context(self._registry.factor_map[factor])
            for factor in metric.candidate_factors
            if factor in question.requested_factors
            and self._registry.factor_map[factor].capability_method in supported
        )

        tools: list[ToolSemanticContext] = []
        for definition in self._registry.tools:
            if (
                definition.requires_period_comparison
                and AnalysisMethod.PERIOD_COMPARISON not in supported
            ):
                continue
            if definition.method is TaskMethod.DIMENSION_CONTRIBUTION and not dimensions:
                continue
            if definition.method is TaskMethod.CANDIDATE_VALIDATION and not factors:
                continue
            if definition.method is not TaskMethod.CANDIDATE_VALIDATION and not set(
                definition.capability_methods
            ).issubset(supported):
                continue
            tools.append(
                ToolSemanticContext(
                    method=definition.method,
                    display_name=definition.display_name,
                    requires_period_comparison=definition.requires_period_comparison,
                )
            )

        return PlannerSemanticContext(
            parsed_question=question,
            metric=MetricSemanticContext(
                metric_id=metric.metric_id,
                display_name=metric.display_name,
                analysis_identity=metric.analysis_identity,
                decomposition_metrics=metric.decomposition_metrics,
                metric_version=metric.metric_version,
            ),
            available_dimensions=dimensions,
            available_factors=factors,
            available_tools=tuple(tools),
            limitations=_logical_limitations(question, capability, self._registry),
            data_quality_status=capability.data_quality_status,
        )

    @staticmethod
    def _dimension_context(
        definition: DimensionDefinition,
    ) -> DimensionSemanticContext:
        return DimensionSemanticContext(
            dimension=definition.dimension,
            display_name=definition.display_name,
            business_role=definition.business_role,
            mutually_exclusive=definition.mutually_exclusive,
            complete_for_contribution=definition.complete_for_contribution,
        )

    @staticmethod
    def _factor_context(definition: CandidateFactorDefinition) -> FactorSemanticContext:
        return FactorSemanticContext(
            factor=definition.factor,
            display_name=definition.display_name,
            primary_metric_id=definition.primary_metric_id,
            supporting_metric_ids=definition.supporting_metric_ids,
            minimum_evidence=definition.minimum_evidence,
            claim_type=definition.claim_type,
        )


def _logical_limitations(
    question: ParsedAnalysisQuestion,
    capability: CapabilityAssessment,
    registry: AnalysisSemanticRegistry,
) -> tuple[str, ...]:
    supported = set(capability.supported_methods)
    available_dimensions = set(capability.available_dimensions)
    limitations: list[str] = []
    if capability.data_quality_status is DataQualityStatus.FAIL:
        limitations.append("data_quality_failed")
    if AnalysisMethod.PERIOD_COMPARISON not in supported:
        limitations.append("period_comparison_unavailable")
    if AnalysisMethod.METRIC_DECOMPOSITION not in supported:
        limitations.append("metric_decomposition_unavailable")
    for dimension in question.requested_dimensions:
        if (
            dimension not in available_dimensions
            or AnalysisMethod.DIMENSION_CONTRIBUTION not in supported
        ):
            limitations.append(f"{dimension.value}_dimension_unavailable")
    for factor in question.requested_factors:
        definition = registry.factor_map[factor]
        if definition.capability_method not in supported:
            limitations.append(f"{factor.value}_evidence_unavailable")
    if capability.missing_evidence and not limitations:
        limitations.append("additional_evidence_unavailable")
    limitations.append("association_not_causation")
    return tuple(dict.fromkeys(limitations))
