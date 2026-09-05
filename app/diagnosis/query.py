from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.diagnosis.planner import AnalysisPlan, AnalysisTask, TaskMethod
from app.diagnosis.question import AnalysisDimension, CandidateFactor
from app.metadata.catalog import MetadataCatalog
from app.nl2sql.validator import SQLValidator, ValidatedSQL

MAX_ANALYSIS_QUERIES = 5


class QueryDataSource(StrEnum):
    WAREHOUSE = "warehouse"
    SYNTHETIC_CASE = "synthetic_case"


class AnalysisQueryContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: QueryDataSource
    case_id: str | None = Field(default=None, pattern=r"^D(?:0[1-9]|10)$")

    @model_validator(mode="after")
    def validate_source_scope(self) -> AnalysisQueryContext:
        if self.source is QueryDataSource.SYNTHETIC_CASE and self.case_id is None:
            raise ValueError("synthetic query context requires a case ID")
        if self.source is QueryDataSource.WAREHOUSE and self.case_id is not None:
            raise ValueError("warehouse query context forbids a case ID")
        return self


class MetricLineage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(min_length=1)


class QueryValidationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tables: tuple[str, ...]
    columns: tuple[str, ...]
    join_relations: tuple[str, ...]
    grain_warnings: tuple[str, ...]
    policy_version: str
    max_rows: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)


class AnalysisQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str = Field(pattern=r"^Q\d{3}$")
    task_id: str = Field(pattern=r"^T[1-4]$")
    method: TaskMethod
    query_role: str = Field(
        pattern=(
            r"^(?:period_comparison|metric_decomposition|candidate_validation|"
            r"dimension_contribution:(?:region|category))$"
        )
    )
    sql_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_version: str = Field(min_length=1)
    metric_versions: tuple[MetricLineage, ...]
    validation: QueryValidationTrace
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ControlledQuery:
    task_id: str
    method: TaskMethod
    query_role: str
    sql: str
    parameters: dict[str, object]
    output_columns: tuple[str, ...]
    validation_metric_ids: tuple[str, ...]
    metric_versions: tuple[MetricLineage, ...]


@dataclass(frozen=True)
class _SourceLayout:
    table: str
    date: str
    gmv: str
    order_count: str
    visitors: str
    promoted: str
    active: str
    available: str
    required: str
    case_id: str | None = None
    category: str | None = None

    @property
    def column_ids(self) -> frozenset[str]:
        names = {
            self.date,
            self.gmv,
            self.order_count,
            self.visitors,
            self.promoted,
            self.active,
            self.available,
            self.required,
            "region_id",
        }
        if self.case_id is not None:
            names.add(self.case_id)
        if self.category is not None:
            names.add(self.category)
        return frozenset(f"{self.table}.{name}" for name in names)


_LAYOUTS = {
    (QueryDataSource.WAREHOUSE, False): _SourceLayout(
        table="dws_sales_region_daily",
        date="date_id",
        gmv="gmv",
        order_count="order_count",
        visitors="visitors",
        promoted="promoted_sku_count",
        active="active_sku_count",
        available="available_sku_count",
        required="required_sku_count",
    ),
    (QueryDataSource.WAREHOUSE, True): _SourceLayout(
        table="dws_sales_category_daily",
        date="date_id",
        gmv="gmv",
        order_count="category_order_count",
        visitors="category_visitors",
        promoted="promoted_sku_count",
        active="active_sku_count",
        available="available_sku_count",
        required="required_sku_count",
        category="category_id",
    ),
    (QueryDataSource.SYNTHETIC_CASE, False): _SourceLayout(
        table="analysis_sales_region_daily",
        date="date_id",
        gmv="analysis_gmv",
        order_count="analysis_order_count",
        visitors="visitors",
        promoted="promoted_sku_count",
        active="active_sku_count",
        available="available_sku_count",
        required="required_sku_count",
        case_id="case_id",
    ),
    (QueryDataSource.SYNTHETIC_CASE, True): _SourceLayout(
        table="analysis_sales_category_daily",
        date="date_id",
        gmv="analysis_gmv",
        order_count="analysis_order_count",
        visitors="visitors",
        promoted="promoted_sku_count",
        active="active_sku_count",
        available="available_sku_count",
        required="required_sku_count",
        case_id="case_id",
        category="category_id",
    ),
}

_REQUIRED_METRICS = (
    "gmv",
    "order_count",
    "aov",
    "category_order_count",
    "visitors",
    "conversion_rate",
    "promotion_coverage",
    "inventory_fill_rate",
)


class AnalysisQueryBuildError(ValueError):
    """Raised when a task cannot be mapped to the frozen Registry contract."""


class AnalysisQueryExecutionError(RuntimeError):
    """Raised when an executed query does not satisfy its fixed result contract."""


class AnalysisQueryRepository(Protocol):
    async def validate_sql(
        self,
        validated_sql: ValidatedSQL,
        parameters: Mapping[str, object] | None = None,
    ) -> None: ...

    async def execute_sql(
        self,
        validated_sql: ValidatedSQL,
        parameters: Mapping[str, object] | None = None,
    ) -> list[dict[str, Any]]: ...


class AnalysisQueryBuilder:
    """Builds only the frozen parameterized aggregate queries for V1 diagnosis."""

    def __init__(
        self,
        catalog: MetadataCatalog,
        context: AnalysisQueryContext,
    ) -> None:
        self._catalog = catalog
        self._context = context
        self._metric_map = {metric.metric_id: metric for metric in catalog.metrics}
        self._validate_registry()

    def build(self, task: AnalysisTask) -> tuple[ControlledQuery, ...]:
        if task.method is TaskMethod.PERIOD_COMPARISON:
            return (self._period_query(task),)
        if task.method is TaskMethod.METRIC_DECOMPOSITION:
            return (self._decomposition_query(task),)
        if task.method is TaskMethod.DIMENSION_CONTRIBUTION:
            return tuple(self._dimension_query(task, dimension) for dimension in task.dimensions)
        if task.method is TaskMethod.CANDIDATE_VALIDATION:
            return (self._candidate_query(task),)
        raise AnalysisQueryBuildError(f"unsupported task method: {task.method}")

    @property
    def catalog_version(self) -> str:
        return self._catalog.version

    def _period_query(self, task: AnalysisTask) -> ControlledQuery:
        layout = self._scope_layout(task)
        return self._build_period_union(
            task=task,
            layout=layout,
            query_role="period_comparison",
            aggregates=((layout.gmv, "gmv"),),
            metric_ids=("gmv",),
            validation_metric_ids=self._gmv_validation_metric_ids(),
        )

    def _decomposition_query(self, task: AnalysisTask) -> ControlledQuery:
        layout = self._scope_layout(task)
        metric_ids = (
            ("gmv", "category_order_count")
            if task.scope.category is not None
            else ("gmv", "order_count", "aov")
        )
        return self._build_period_union(
            task=task,
            layout=layout,
            query_role="metric_decomposition",
            aggregates=((layout.gmv, "gmv"), (layout.order_count, "order_count")),
            metric_ids=metric_ids,
            validation_metric_ids=self._gmv_validation_metric_ids(),
        )

    def _dimension_query(
        self,
        task: AnalysisTask,
        dimension: AnalysisDimension,
    ) -> ControlledQuery:
        layout = self._dimension_layout(task, dimension)
        dimension_column = (
            "region_id" if dimension is AnalysisDimension.REGION else layout.category
        )
        if dimension_column is None:
            raise AnalysisQueryBuildError("category dimension requires a category layout")
        return self._build_period_union(
            task=task,
            layout=layout,
            query_role=f"dimension_contribution:{dimension.value}",
            aggregates=((layout.gmv, "gmv"),),
            metric_ids=("gmv",),
            validation_metric_ids=self._gmv_validation_metric_ids(),
            dimension_column=dimension_column,
        )

    def _candidate_query(self, task: AnalysisTask) -> ControlledQuery:
        layout = self._scope_layout(task)
        aggregate_map = {
            "order_count": layout.order_count,
            "visitors": layout.visitors,
        }
        metric_ids: list[str] = [
            "category_order_count" if task.scope.category is not None else "order_count",
            "visitors",
            "conversion_rate",
        ]
        if CandidateFactor.PROMOTION in task.factors:
            aggregate_map["promoted_sku_count"] = layout.promoted
            aggregate_map["active_sku_count"] = layout.active
            metric_ids.append("promotion_coverage")
        if CandidateFactor.INVENTORY in task.factors:
            aggregate_map["available_sku_count"] = layout.available
            aggregate_map["required_sku_count"] = layout.required
            metric_ids.append("inventory_fill_rate")
        return self._build_period_union(
            task=task,
            layout=layout,
            query_role="candidate_validation",
            aggregates=tuple((column, alias) for alias, column in aggregate_map.items()),
            metric_ids=tuple(metric_ids),
            validation_metric_ids=(),
        )

    def _build_period_union(
        self,
        *,
        task: AnalysisTask,
        layout: _SourceLayout,
        query_role: str,
        aggregates: tuple[tuple[str, str], ...],
        metric_ids: tuple[str, ...],
        validation_metric_ids: tuple[str, ...],
        dimension_column: str | None = None,
    ) -> ControlledQuery:
        parameters = self._parameters(task)
        baseline = self._period_select(
            role="baseline",
            start_parameter="baseline_start",
            end_parameter="baseline_end",
            task=task,
            layout=layout,
            aggregates=aggregates,
            dimension_column=dimension_column,
        )
        current = self._period_select(
            role="current",
            start_parameter="current_start",
            end_parameter="current_end",
            task=task,
            layout=layout,
            aggregates=aggregates,
            dimension_column=dimension_column,
        )
        order_columns = "period_role, dimension_value" if dimension_column else "period_role"
        output_columns = (
            ("period_role", "dimension_value")
            if dimension_column
            else ("period_role",)
        ) + tuple(alias for _, alias in aggregates)
        return ControlledQuery(
            task_id=task.task_id,
            method=task.method,
            query_role=query_role,
            sql=f"{baseline} UNION ALL {current} ORDER BY {order_columns}",
            parameters=parameters,
            output_columns=output_columns,
            validation_metric_ids=validation_metric_ids,
            metric_versions=self._metric_lineage(metric_ids),
        )

    def _period_select(
        self,
        *,
        role: str,
        start_parameter: str,
        end_parameter: str,
        task: AnalysisTask,
        layout: _SourceLayout,
        aggregates: tuple[tuple[str, str], ...],
        dimension_column: str | None,
    ) -> str:
        projections = [f"'{role}' AS period_role"]
        if dimension_column:
            projections.append(f"s.{dimension_column} AS dimension_value")
        projections.extend(f"SUM(s.{column}) AS {alias}" for column, alias in aggregates)
        predicates = [
            f"s.{layout.date} BETWEEN :{start_parameter} AND :{end_parameter}"
        ]
        if task.scope.region is not None:
            predicates.append("s.region_id = :region")
        if task.scope.category is not None:
            if layout.category is None:
                raise AnalysisQueryBuildError("category scope requires a category layout")
            predicates.append(f"s.{layout.category} = :category")
        if layout.case_id is not None:
            predicates.append(f"s.{layout.case_id} = :case_id")
        group_by = f" GROUP BY s.{dimension_column}" if dimension_column else ""
        return (
            f"SELECT {', '.join(projections)} FROM {layout.table} AS s "
            f"WHERE {' AND '.join(predicates)}{group_by}"
        )

    def _parameters(self, task: AnalysisTask) -> dict[str, object]:
        parameters: dict[str, object] = {
            "baseline_start": _date_id(task.baseline_period.start),
            "baseline_end": _date_id(task.baseline_period.end),
            "current_start": _date_id(task.current_period.start),
            "current_end": _date_id(task.current_period.end),
        }
        if task.scope.region is not None:
            parameters["region"] = task.scope.region
        if task.scope.category is not None:
            parameters["category"] = task.scope.category
        if self._context.case_id is not None:
            parameters["case_id"] = self._context.case_id
        return parameters

    def _scope_layout(self, task: AnalysisTask) -> _SourceLayout:
        return _LAYOUTS[(self._context.source, task.scope.category is not None)]

    def _gmv_validation_metric_ids(self) -> tuple[str, ...]:
        if self._context.source is QueryDataSource.WAREHOUSE:
            return ("gmv",)
        return ()

    def _dimension_layout(
        self,
        task: AnalysisTask,
        dimension: AnalysisDimension,
    ) -> _SourceLayout:
        category_table = (
            dimension is AnalysisDimension.CATEGORY or task.scope.category is not None
        )
        return _LAYOUTS[(self._context.source, category_table)]

    def _metric_lineage(self, metric_ids: tuple[str, ...]) -> tuple[MetricLineage, ...]:
        return tuple(
            MetricLineage(metric_id=metric_id, version=self._metric_map[metric_id].version)
            for metric_id in dict.fromkeys(metric_ids)
        )

    def _validate_registry(self) -> None:
        layouts = (
            _LAYOUTS[(self._context.source, False)],
            _LAYOUTS[(self._context.source, True)],
        )
        missing_columns = set().union(
            *(layout.column_ids - self._catalog.column_ids for layout in layouts)
        )
        if missing_columns:
            raise AnalysisQueryBuildError(
                f"Catalog is missing controlled query columns: {sorted(missing_columns)}"
            )
        missing_metrics = set(_REQUIRED_METRICS) - set(self._metric_map)
        if missing_metrics:
            raise AnalysisQueryBuildError(
                f"Catalog is missing controlled query metrics: {sorted(missing_metrics)}"
            )
        missing_versions = [
            metric_id
            for metric_id in _REQUIRED_METRICS
            if not self._metric_map[metric_id].version
        ]
        if missing_versions:
            raise AnalysisQueryBuildError(
                f"Catalog metrics are missing versions: {sorted(missing_versions)}"
            )


class AnalysisTaskExecutor:
    """Validates, explains, and executes a bounded AnalysisPlan in order."""

    def __init__(
        self,
        builder: AnalysisQueryBuilder,
        validator: SQLValidator,
        repository: AnalysisQueryRepository,
    ) -> None:
        self._builder = builder
        self._validator = validator
        self._repository = repository

    async def execute(self, plan: AnalysisPlan) -> tuple[AnalysisQueryResult, ...]:
        queries = tuple(query for task in plan.tasks for query in self._builder.build(task))
        if len(queries) > MAX_ANALYSIS_QUERIES:
            raise AnalysisQueryBuildError(
                f"analysis plan exceeds {MAX_ANALYSIS_QUERIES} physical queries"
            )

        results: list[AnalysisQueryResult] = []
        for index, query in enumerate(queries, start=1):
            validated = self._validator.validate(
                query.sql,
                query.validation_metric_ids,
            )
            await self._repository.validate_sql(validated, query.parameters)
            rows = await self._repository.execute_sql(validated, query.parameters)
            self._validate_result_shape(query, rows)
            results.append(
                AnalysisQueryResult(
                    query_id=f"Q{index:03d}",
                    task_id=query.task_id,
                    method=query.method,
                    query_role=query.query_role,
                    sql_fingerprint=hashlib.sha256(
                        validated.sql.encode("utf-8")
                    ).hexdigest(),
                    catalog_version=self._builder.catalog_version,
                    metric_versions=query.metric_versions,
                    validation=QueryValidationTrace.model_validate(validated.as_trace()),
                    rows=tuple(rows),
                )
            )
        return tuple(results)

    @staticmethod
    def _validate_result_shape(
        query: ControlledQuery,
        rows: list[dict[str, Any]],
    ) -> None:
        expected = set(query.output_columns)
        for row in rows:
            if set(row) != expected:
                raise AnalysisQueryExecutionError(
                    f"unexpected result columns for {query.query_role}"
                )


class AnalysisTaskExecutorNode:
    """Emits serialized Query Results while keeping runtime dependencies injected."""

    def __init__(self, executor: AnalysisTaskExecutor) -> None:
        self._executor = executor

    async def __call__(self, state: Mapping[str, Any]) -> dict[str, Any]:
        plan = AnalysisPlan.model_validate(state.get("analysis_plan"))
        results = await self._executor.execute(plan)
        return {
            "query_results": [result.model_dump(mode="json") for result in results]
        }


def _date_id(value: date) -> int:
    return int(value.strftime("%Y%m%d"))
